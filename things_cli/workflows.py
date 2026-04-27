from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any


FOLLOWUP_WORDS = (
    "follow up",
    "reply",
    "respond",
    "email",
    "dm ",
    "message",
    "intro",
    "introduce",
    "ask ",
    "reach out",
)

APPLICATION_WORDS = (
    "apply",
    "application",
    "accelerator",
    "job",
    "role",
    "hiring",
    "recruit",
)

STRATEGIC_WORDS = (
    "strategy",
    "pricing",
    "investor",
    "grant",
    "customer",
    "sales",
    "launch",
    "ship",
    "build",
    "prototype",
)

CLEANUP_WORDS = (
    "read",
    "watch",
    "listen",
    "archive",
    "cleanup",
    "clean up",
)


def parse_day(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def todo_text(todo: dict[str, Any]) -> str:
    return "\n".join(
        str(todo.get(key) or "")
        for key in ("name", "notes", "tag_names", "project", "area", "list")
    ).lower()


def has_any(todo: dict[str, Any], words: tuple[str, ...]) -> bool:
    text = todo_text(todo)
    return any(word in text for word in words)


def active_date(todo: dict[str, Any]) -> date | None:
    return parse_day(todo.get("when")) or parse_day(todo.get("due"))


def is_overdue(todo: dict[str, Any], today: date) -> bool:
    candidates = [parse_day(todo.get("due")), parse_day(todo.get("when"))]
    return any(day is not None and day < today for day in candidates)


def is_due_today(todo: dict[str, Any], today: date) -> bool:
    return parse_day(todo.get("due")) == today or parse_day(todo.get("when")) == today


def score_attention(todo: dict[str, Any], today: date) -> int:
    score = 0
    if is_overdue(todo, today):
        score += 50
    if is_due_today(todo, today):
        score += 35
    if has_any(todo, FOLLOWUP_WORDS):
        score += 25
    if has_any(todo, APPLICATION_WORDS):
        score += 20
    if has_any(todo, STRATEGIC_WORDS):
        score += 15
    if has_any(todo, CLEANUP_WORDS):
        score -= 8
    if todo.get("list") == "Inbox":
        score += 10
    return score


def filter_stale(todos: list[dict[str, Any]], before: date) -> list[dict[str, Any]]:
    result = []
    for todo in todos:
        modified = parse_day(todo.get("modified"))
        created = parse_day(todo.get("created"))
        anchor = modified or created
        if anchor and anchor < before:
            result.append(todo)
    return sorted(result, key=lambda item: item.get("modified") or item.get("created") or "")


def attention(todos: list[dict[str, Any]], today: date, limit: int = 25) -> list[dict[str, Any]]:
    ranked = []
    for todo in todos:
        if todo.get("status") != "open":
            continue
        score = score_attention(todo, today)
        if score > 0:
            enriched = dict(todo)
            enriched["attention_score"] = score
            ranked.append(enriched)
    ranked.sort(key=lambda item: (-item["attention_score"], item.get("when") or item.get("due") or "9999-99-99"))
    return ranked[:limit]


def buckets(todos: list[dict[str, Any]], today: date, limit: int = 12) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for todo in todos:
        if todo.get("status") != "open":
            continue
        if is_overdue(todo, today):
            grouped["overdue"].append(todo)
        if is_due_today(todo, today) or todo.get("list") == "Today":
            grouped["today"].append(todo)
        if has_any(todo, FOLLOWUP_WORDS):
            grouped["followups"].append(todo)
        if has_any(todo, APPLICATION_WORDS):
            grouped["applications"].append(todo)
        if has_any(todo, STRATEGIC_WORDS):
            grouped["strategic"].append(todo)
        if todo.get("list") == "Inbox":
            grouped["inbox"].append(todo)

    ordered = {}
    for name, items in grouped.items():
        ordered[name] = attention(items, today, limit=limit) or items[:limit]
    return ordered


def day_review(todos: list[dict[str, Any]], today: date, limit: int = 12) -> dict[str, Any]:
    open_todos = [todo for todo in todos if todo.get("status") == "open"]
    return {
        "today": today.isoformat(),
        "open_count": len(open_todos),
        "overdue_count": sum(1 for todo in open_todos if is_overdue(todo, today)),
        "due_today_count": sum(1 for todo in open_todos if is_due_today(todo, today)),
        "inbox_count": sum(1 for todo in open_todos if todo.get("list") == "Inbox"),
        "attention": attention(open_todos, today, limit=limit),
        "buckets": buckets(open_todos, today, limit=limit),
    }


def default_stale_before(today: date, days: int = 30) -> date:
    return today - timedelta(days=days)
