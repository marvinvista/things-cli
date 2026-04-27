from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from .audit import append_audit_event, audit_summary, find_audit_event, read_audit_events
from .client import ThingsClient, ThingsError
from .schemas import SCHEMAS
from .snapshots import diff_snapshots
from .workflows import (
    APPLICATION_WORDS,
    FOLLOWUP_WORDS,
    attention,
    day_review,
    default_stale_before,
    filter_stale,
    has_any,
)


def normalize_tag_names(value: str | None) -> str | None:
    if value is None:
        return None
    parts = [part.strip() for part in value.split(",") if part.strip()]
    return ", ".join(dict.fromkeys(parts))


def print_json(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def parse_date_arg(value: str | None, label: str) -> date:
    if not value:
        return date.today()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ThingsError(f"{label} must be YYYY-MM-DD: {value}") from exc


def compact_todo(todo: dict[str, Any]) -> str:
    timing = []
    if todo.get("when"):
        timing.append(f"when {todo['when']}")
    if todo.get("due"):
        timing.append(f"due {todo['due']}")
    if todo.get("attention_score") is not None:
        timing.append(f"score {todo['attention_score']}")
    meta = f" ({', '.join(timing)})" if timing else ""
    return f"- {todo.get('name', '(untitled)')}{meta}\n  id: {todo.get('id')}"


def print_todos(todos: list[dict[str, Any]]) -> None:
    if not todos:
        print("No matching Things todos.")
        return
    for todo in todos:
        print(compact_todo(todo))
        if todo.get("project") or todo.get("area") or todo.get("list"):
            location = " / ".join(part for part in [todo.get("list"), todo.get("area"), todo.get("project")] if part)
            print(f"  location: {location}")
        if todo.get("tag_names"):
            print(f"  tags: {todo['tag_names']}")


def print_review(review: dict[str, Any]) -> None:
    print(f"Things review for {review['today']}")
    if review.get("scope"):
        print(f"Scope: {review['scope']}")
    print(f"Open: {review['open_count']} | Overdue: {review['overdue_count']} | Due today: {review['due_today_count']} | Inbox: {review['inbox_count']}")
    print()
    print("Attention")
    print_todos(review["attention"])
    for name, todos in review["buckets"].items():
        print()
        print(name.replace("_", " ").title())
        print_todos(todos)


def print_diff(diff: dict[str, Any]) -> None:
    print(f"Before: {diff['before']} ({diff['before_count']} todos)")
    print(f"After: {diff['after']} ({diff['after_count']} todos)")
    print(f"Added: {diff['added_count']} | Removed: {diff['removed_count']} | Changed: {diff['changed_count']}")
    if diff["added"]:
        print()
        print("Added")
        print_todos(diff["added"])
    if diff["removed"]:
        print()
        print("Removed")
        print_todos(diff["removed"])
    if diff["changed"]:
        print()
        print("Changed")
        for item in diff["changed"]:
            print(f"- {item['after_name'] or item['before_name']} ({item['id']})")
            for field, change in item["changes"].items():
                print(f"  {field}: {change['before']} -> {change['after']}")


def dry_run(action: str, payload: dict[str, Any]) -> None:
    print_json({"dry_run": True, "action": action, "payload": payload})


def mutation_allowed(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "yes", False)) and not bool(getattr(args, "dry_run", False))


def read_ids_file(path: str) -> list[str]:
    ids = []
    for line in Path(path).expanduser().read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            ids.append(stripped)
    return list(dict.fromkeys(ids))


def resolve_bulk_matches(client: ThingsClient, args: argparse.Namespace) -> list[dict[str, Any]]:
    ids_from = getattr(args, "ids_from", None)
    query = getattr(args, "query", None)
    if ids_from:
        ids = read_ids_file(ids_from)
        if not ids:
            raise ThingsError(f"No todo ids found in {ids_from}")
        return [client.get(todo_id) for todo_id in ids]
    if not query:
        raise ThingsError("Bulk commands require --query or --ids-from.")
    return client.search(query, limit=args.limit)


def enforce_bulk_guardrails(args: argparse.Namespace, matches: list[dict[str, Any]]) -> None:
    max_count = getattr(args, "max_count", None)
    ids_from = getattr(args, "ids_from", None)
    if max_count is not None and len(matches) > max_count:
        raise ThingsError(f"Bulk command matched {len(matches)} todos, above --max {max_count}.")
    if mutation_allowed(args) and not ids_from and max_count is None:
        raise ThingsError("Bulk --yes requires --max or --ids-from.")


def undo_event_preview(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": event.get("event_id"),
        "original_action": event.get("action"),
        "undo_plan": build_undo_plan(event),
        "apply_with": "--yes",
    }


def build_undo_plan(event: dict[str, Any]) -> list[dict[str, Any]]:
    action = str(event.get("action") or "")
    if action.startswith("bulk "):
        plan = []
        for item in event.get("after") or []:
            before = item.get("before")
            after = item.get("after")
            if before:
                plan.append({"operation": "restore", "id": before.get("id"), "before": before})
            elif after:
                plan.append({"operation": "cancel-created", "id": after.get("id"), "after": after})
        return plan
    before = event.get("before")
    after = event.get("after")
    if before:
        return [{"operation": "restore", "id": before.get("id"), "before": before}]
    if after:
        return [{"operation": "cancel-created", "id": after.get("id"), "after": after}]
    return []


def apply_undo_plan(client: ThingsClient, plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for item in plan:
        operation = item.get("operation")
        if operation == "restore":
            restored = client.restore_todo(item["before"])
            results.append({"operation": operation, "id": item.get("id"), "after": restored, "verified": restored.get("id") == item.get("id")})
        elif operation == "cancel-created":
            canceled = client.cancel(item["id"])
            results.append({"operation": operation, "id": item.get("id"), "after": canceled, "verified": canceled.get("status") == "canceled"})
        else:
            raise ThingsError(f"Unsupported undo operation: {operation}")
    return results


def workflow_todos(client: ThingsClient, args: argparse.Namespace) -> list[dict[str, Any]]:
    scope = getattr(args, "scope", "today")
    list_name = getattr(args, "list_name", None)
    if list_name:
        return client.list_todos_fast(list_name)
    if scope == "today":
        return client.list_todos_fast("Today")
    return client.export(False)["todos"]


def mutate_existing(
    client: ThingsClient,
    args: argparse.Namespace,
    action: str,
    payload: dict[str, Any],
    apply: Callable[[], dict[str, Any]],
) -> int:
    before = client.get(args.id)
    if not mutation_allowed(args):
        dry_run(action, {"before": before, "change": payload, "apply_with": "--yes"})
        return 0
    after = apply()
    verified = after.get("id") == args.id
    audit = append_audit_event(action, path=args.audit_log, before=before, change=payload, after=after, verified=verified)
    print_json({"action": action, "before": before, "after": after, "verified": verified, **audit})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="things", description="Read and update Things todos through Apple Events.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--audit-log", help="Path for mutation JSONL audit events. Defaults to ~/.things-cli/mutations.jsonl.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("diagnose", help="Check Things Apple Events access and list counts.")
    sub.add_parser("schema", help="Print JSON output schemas for agents.")
    sub.add_parser("lists", help="List Things lists and todo counts.")
    sub.add_parser("projects", help="List Things projects.")
    sub.add_parser("tags", help="List Things tags.")

    list_parser = sub.add_parser("list", help="List todos.")
    list_parser.add_argument("--list", dest="list_name", help="Things list name, e.g. Inbox, Today, Anytime.")
    list_parser.add_argument("--limit", type=int, default=25)
    list_parser.add_argument("--include-closed", action="store_true")

    search = sub.add_parser("search", help="Search todos by title, notes, tags, project, area, or list.")
    search.add_argument("query")
    search.add_argument("--list", dest="list_name")
    search.add_argument("--limit", type=int, default=25)
    search.add_argument("--include-closed", action="store_true")

    get = sub.add_parser("get", help="Get a todo by Things id.")
    get.add_argument("id")

    export = sub.add_parser("export", help="Export a Things snapshot.")
    export.add_argument("--output", "-o", help="Write JSON snapshot to this path.")
    export.add_argument("--include-closed", action="store_true", help="Include Logbook and Trash.")

    diff = sub.add_parser("diff", help="Compare two things-cli export snapshots.")
    diff.add_argument("before")
    diff.add_argument("after")

    audit = sub.add_parser("audit", help="Inspect mutation audit logs.")
    audit_sub = audit.add_subparsers(dest="audit_command", required=True)
    audit_summary_parser = audit_sub.add_parser("summary", help="Summarize audit log events.")
    audit_summary_parser.add_argument("--path", help="Audit log path. Defaults to --audit-log, env, or ~/.things-cli/mutations.jsonl.")
    audit_list_parser = audit_sub.add_parser("list", help="List recent audit log events.")
    audit_list_parser.add_argument("--path", help="Audit log path. Defaults to --audit-log, env, or ~/.things-cli/mutations.jsonl.")
    audit_list_parser.add_argument("--limit", type=int, default=20)

    undo = sub.add_parser("undo", help="Undo a mutation from the audit log. Dry-run unless --yes is passed.")
    undo.add_argument("event_id", nargs="?")
    undo.add_argument("--last", action="store_true", help="Undo the most recent audit event.")
    undo.add_argument("--path", help="Audit log path. Defaults to --audit-log, env, or ~/.things-cli/mutations.jsonl.")
    undo.add_argument("--dry-run", action="store_true")
    undo.add_argument("--yes", action="store_true", help="Actually mutate Things.")

    add = sub.add_parser("add", help="Create a new todo. Dry-run unless --yes is passed.")
    add.add_argument("name")
    add.add_argument("--notes")
    add.add_argument("--due", help="Due date as YYYY-MM-DD.")
    add.add_argument("--when", help="Scheduled/When date as YYYY-MM-DD.")
    add.add_argument("--tags", help="Comma-separated Things tag names.")
    add.add_argument("--list", dest="list_name", default="Inbox")
    add.add_argument("--dry-run", action="store_true")
    add.add_argument("--yes", action="store_true", help="Actually mutate Things.")

    update = sub.add_parser("update", help="Update a todo by Things id. Dry-run unless --yes is passed.")
    update.add_argument("id")
    update.add_argument("--name")
    update.add_argument("--notes")
    update.add_argument("--due", help="Due date as YYYY-MM-DD.")
    update.add_argument("--clear-due", action="store_true")
    update.add_argument("--when", help="Scheduled/When date as YYYY-MM-DD.")
    update.add_argument("--clear-when", action="store_true")
    update.add_argument("--tags", help="Comma-separated Things tag names.")
    update.add_argument("--dry-run", action="store_true")
    update.add_argument("--yes", action="store_true", help="Actually mutate Things.")

    move = sub.add_parser("move", help="Move a todo to a list or project. Dry-run unless --yes is passed.")
    move.add_argument("id")
    target = move.add_mutually_exclusive_group(required=True)
    target.add_argument("--list", dest="list_name")
    target.add_argument("--project", dest="project_name")
    move.add_argument("--dry-run", action="store_true")
    move.add_argument("--yes", action="store_true", help="Actually mutate Things.")

    complete = sub.add_parser("complete", help="Mark a todo completed. Dry-run unless --yes is passed.")
    complete.add_argument("id")
    complete.add_argument("--dry-run", action="store_true")
    complete.add_argument("--yes", action="store_true", help="Actually mutate Things.")

    cancel = sub.add_parser("cancel", help="Mark a todo canceled. Dry-run unless --yes is passed.")
    cancel.add_argument("id")
    cancel.add_argument("--dry-run", action="store_true")
    cancel.add_argument("--yes", action="store_true", help="Actually mutate Things.")

    project = sub.add_parser("create-project", help="Create a Things project. Dry-run unless --yes is passed.")
    project.add_argument("name")
    project.add_argument("--notes")
    project.add_argument("--due")
    project.add_argument("--when")
    project.add_argument("--tags")
    project.add_argument("--dry-run", action="store_true")
    project.add_argument("--yes", action="store_true", help="Actually mutate Things.")

    show = sub.add_parser("show", help="Reveal a todo in Things.")
    show.add_argument("id")

    bulk = sub.add_parser("bulk", help="Bulk operations over search results. Dry-run unless --yes is passed.")
    bulk_sub = bulk.add_subparsers(dest="bulk_command", required=True)
    bulk_tag = bulk_sub.add_parser("tag", help="Replace tags on matching todos.")
    bulk_tag.add_argument("--query")
    bulk_tag.add_argument("--ids-from", dest="ids_from", help="Path containing one Things todo id per line.")
    bulk_tag.add_argument("--tags", required=True)
    bulk_tag.add_argument("--limit", type=int, default=25)
    bulk_tag.add_argument("--max", dest="max_count", type=int, help="Abort if matched todo count exceeds this number.")
    bulk_tag.add_argument("--dry-run", action="store_true")
    bulk_tag.add_argument("--yes", action="store_true", help="Actually mutate Things.")

    bulk_move = bulk_sub.add_parser("move", help="Move matching todos to a list or project.")
    bulk_move.add_argument("--query")
    bulk_move.add_argument("--ids-from", dest="ids_from", help="Path containing one Things todo id per line.")
    bulk_move.add_argument("--limit", type=int, default=25)
    bulk_move.add_argument("--max", dest="max_count", type=int, help="Abort if matched todo count exceeds this number.")
    target = bulk_move.add_mutually_exclusive_group(required=True)
    target.add_argument("--list", dest="list_name")
    target.add_argument("--project", dest="project_name")
    bulk_move.add_argument("--dry-run", action="store_true")
    bulk_move.add_argument("--yes", action="store_true", help="Actually mutate Things.")

    for name in ("review", "triage", "attention"):
        workflow = sub.add_parser(name, help=f"Show {name} workflow report.")
        workflow.add_argument("--today", help="Today date as YYYY-MM-DD.")
        workflow.add_argument("--limit", type=int, default=12)
        workflow.add_argument("--scope", choices=["today", "all"], default="today", help="Default today uses a fast Things list read; all walks the full library.")
        workflow.add_argument("--list", dest="list_name", help="Review a named Things list using the fast path.")

    applications = sub.add_parser("applications", help="Show application/opportunity todos.")
    applications.add_argument("--limit", type=int, default=25)
    applications.add_argument("--scope", choices=["today", "all"], default="today")
    applications.add_argument("--list", dest="list_name")

    followups = sub.add_parser("followups", help="Show human follow-up todos.")
    followups.add_argument("--limit", type=int, default=25)
    followups.add_argument("--scope", choices=["today", "all"], default="today")
    followups.add_argument("--list", dest="list_name")

    stale = sub.add_parser("stale", help="Show open todos not modified since a date.")
    stale.add_argument("--before", help="YYYY-MM-DD. Defaults to 30 days ago.")
    stale.add_argument("--days", type=int, default=30)
    stale.add_argument("--limit", type=int, default=50)
    stale.add_argument("--scope", choices=["today", "all"], default="today")
    stale.add_argument("--list", dest="list_name")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    client = ThingsClient()

    try:
        if args.command == "diagnose":
            print_json(client.diagnose())
            return 0

        if args.command == "schema":
            print_json(SCHEMAS)
            return 0

        if args.command == "lists":
            result = client.lists()
            if args.json:
                print_json(result)
            else:
                for item in result:
                    print(f"{item['name']}: {item['count']} ({item['id']})")
            return 0

        if args.command == "projects":
            result = client.projects()
            print_json(result) if args.json else print_todos(result)
            return 0

        if args.command == "tags":
            result = client.tags()
            print_json(result) if args.json else print_json(result)
            return 0

        if args.command == "list":
            result = client.list_todos(args.list_name, args.limit, args.include_closed)
            print_json(result) if args.json else print_todos(result)
            return 0

        if args.command == "search":
            result = client.search(args.query, args.list_name, args.limit, args.include_closed)
            print_json(result) if args.json else print_todos(result)
            return 0

        if args.command == "get":
            print_json(client.get(args.id))
            return 0

        if args.command == "export":
            result = client.export(args.include_closed)
            if args.output:
                path = Path(args.output)
                path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
                print(f"Wrote {len(result['todos'])} todos to {path}")
            else:
                print_json(result)
            return 0

        if args.command == "diff":
            result = diff_snapshots(args.before, args.after)
            print_json(result) if args.json else print_diff(result)
            return 0

        if args.command == "audit":
            path = args.path or args.audit_log
            if args.audit_command == "summary":
                print_json(audit_summary(path))
                return 0
            if args.audit_command == "list":
                print_json(read_audit_events(path, args.limit))
                return 0

        if args.command == "undo":
            path = args.path or args.audit_log
            event = find_audit_event(args.event_id, path=path, last=args.last)
            plan = build_undo_plan(event)
            if not plan:
                raise ThingsError(f"Audit event has no undoable payload: {event.get('event_id')}")
            if not mutation_allowed(args):
                dry_run("undo", undo_event_preview(event))
            else:
                results = apply_undo_plan(client, plan)
                verified = all(result.get("verified") for result in results)
                audit = append_audit_event(
                    "undo",
                    path=path,
                    before=event,
                    change={"undo_event_id": event.get("event_id"), "plan": plan},
                    after=results,
                    verified=verified,
                )
                print_json({"action": "undo", "undone_event_id": event.get("event_id"), "results": results, "verified": verified, **audit})
            return 0

        if args.command == "add":
            payload = {
                "name": args.name,
                "notes": args.notes,
                "due": args.due,
                "when": args.when,
                "tags": normalize_tag_names(args.tags),
                "list": args.list_name,
            }
            if not mutation_allowed(args):
                dry_run("add", {**payload, "apply_with": "--yes"})
            else:
                after = client.add(args.name, args.notes, args.due, normalize_tag_names(args.tags), args.when, args.list_name)
                verified = bool(after.get("id"))
                audit = append_audit_event("add", path=args.audit_log, change=payload, after=after, verified=verified)
                print_json({"action": "add", "after": after, "verified": verified, **audit})
            return 0

        if args.command == "update":
            payload = {
                "name": args.name,
                "notes": args.notes,
                "due": args.due,
                "clear_due": args.clear_due,
                "when": args.when,
                "clear_when": args.clear_when,
                "tags": normalize_tag_names(args.tags),
            }
            return mutate_existing(
                client,
                args,
                "update",
                payload,
                lambda: client.update(args.id, args.name, args.notes, args.due, args.clear_due, args.when, args.clear_when, normalize_tag_names(args.tags)),
            )

        if args.command == "move":
            payload = {"list": args.list_name, "project": args.project_name}
            return mutate_existing(
                client,
                args,
                "move",
                payload,
                lambda: client.move(args.id, args.list_name, args.project_name),
            )

        if args.command == "complete":
            return mutate_existing(client, args, "complete", {}, lambda: client.complete(args.id))

        if args.command == "cancel":
            return mutate_existing(client, args, "cancel", {}, lambda: client.cancel(args.id))

        if args.command == "create-project":
            payload = {"name": args.name, "notes": args.notes, "due": args.due, "when": args.when, "tags": normalize_tag_names(args.tags)}
            if not mutation_allowed(args):
                dry_run("create-project", {**payload, "apply_with": "--yes"})
            else:
                after = client.create_project(args.name, args.notes, args.due, args.when, normalize_tag_names(args.tags))
                verified = bool(after.get("id"))
                audit = append_audit_event("create-project", path=args.audit_log, change=payload, after=after, verified=verified)
                print_json({"action": "create-project", "after": after, "verified": verified, **audit})
            return 0

        if args.command == "show":
            print_json(client.show(args.id))
            return 0

        if args.command == "bulk":
            matches = resolve_bulk_matches(client, args)
            enforce_bulk_guardrails(args, matches)
            payload = {"matches": matches, "count": len(matches), "apply_with": "--yes"}
            if args.bulk_command == "tag":
                normalized_tags = normalize_tag_names(args.tags)
                payload["tags"] = normalized_tags
                if not mutation_allowed(args):
                    dry_run("bulk tag", payload)
                else:
                    results = []
                    for todo in matches:
                        after = client.update(todo["id"], tags=normalized_tags)
                        results.append({"before": todo, "after": after, "verified": after.get("id") == todo.get("id")})
                    audit = append_audit_event("bulk tag", path=args.audit_log, change={"query": args.query, "tags": normalized_tags}, before=matches, after=results, verified=all(item["verified"] for item in results))
                    print_json({"action": "bulk tag", "count": len(results), "results": results, **audit})
                return 0
            if args.bulk_command == "move":
                payload["target"] = {"list": args.list_name, "project": args.project_name}
                if not mutation_allowed(args):
                    dry_run("bulk move", payload)
                else:
                    results = []
                    for todo in matches:
                        after = client.move(todo["id"], args.list_name, args.project_name)
                        results.append({"before": todo, "after": after, "verified": after.get("id") == todo.get("id")})
                    audit = append_audit_event("bulk move", path=args.audit_log, change={"query": args.query, "list": args.list_name, "project": args.project_name}, before=matches, after=results, verified=all(item["verified"] for item in results))
                    print_json({"action": "bulk move", "count": len(results), "results": results, **audit})
                return 0

        if args.command in {"review", "triage", "attention"}:
            today = parse_date_arg(args.today, "--today")
            todos = workflow_todos(client, args)
            if args.command == "attention":
                result = attention(todos, today, args.limit)
                print_json(result) if args.json else print_todos(result)
            else:
                result = day_review(todos, today, args.limit)
                result["scope"] = args.list_name or args.scope
                print_json(result) if args.json else print_review(result)
            return 0

        if args.command == "applications":
            todos = workflow_todos(client, args)
            result = [todo for todo in todos if todo.get("status") == "open" and has_any(todo, APPLICATION_WORDS)][: args.limit]
            print_json(result) if args.json else print_todos(result)
            return 0

        if args.command == "followups":
            todos = workflow_todos(client, args)
            result = [todo for todo in todos if todo.get("status") == "open" and has_any(todo, FOLLOWUP_WORDS)][: args.limit]
            print_json(result) if args.json else print_todos(result)
            return 0

        if args.command == "stale":
            today = date.today()
            before = parse_date_arg(args.before, "--before") if args.before else default_stale_before(today, args.days)
            todos = workflow_todos(client, args)
            result = filter_stale([todo for todo in todos if todo.get("status") == "open"], before)[: args.limit]
            print_json(result) if args.json else print_todos(result)
            return 0

    except ThingsError as exc:
        print(f"things: {exc}", file=sys.stderr)
        return 2

    parser.error(f"Unhandled command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
