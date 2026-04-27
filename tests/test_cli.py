import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from things_cli import cli


class FakeClient:
    def diagnose(self):
        return {"app": "Things", "lists": [{"name": "Inbox", "count": 1}]}

    def lists(self):
        return [{"id": "inbox", "name": "Inbox", "count": 1}]

    def projects(self):
        return [{"id": "project", "name": "Networking", "count": 1}]

    def tags(self):
        return [{"id": "tag", "name": "Follow Up", "count": 1}]

    def list_todos(self, list_name=None, limit=None, include_closed=False):
        return [
            {
                "id": "abc",
                "name": "Follow up",
                "when": "2026-04-26",
                "due": None,
                "project": "Networking",
                "area": None,
                "tag_names": "Follow Up",
                "status": "open",
                "created": "2026-01-01",
                "modified": "2026-01-15",
            }
        ]

    def list_todos_fast(self, list_name="Today", limit=None, include_closed=False):
        todos = self.list_todos(list_name, limit, include_closed)
        for todo in todos:
            todo["list"] = list_name
        return todos

    def search(self, query, list_name=None, limit=None, include_closed=False):
        return self.list_todos(list_name, limit)

    def export(self, include_closed=False):
        return {
            "todos": self.list_todos(),
            "lists": self.lists(),
            "projects": self.projects(),
            "tags": self.tags(),
        }

    def get(self, todo_id):
        return {"id": todo_id, "name": "Follow up", "status": "open"}

    def add(self, name, notes=None, due=None, tags=None, when=None, list_name="Inbox"):
        return {
            "id": "new",
            "name": name,
            "notes": notes,
            "due": due,
            "when": when,
            "tag_names": tags,
            "list": list_name,
            "status": "open",
        }

    def update(self, todo_id, name=None, notes=None, due=None, clear_due=False, when=None, clear_when=False, tags=None):
        return {"id": todo_id, "name": name or "Follow up", "status": "open", "tag_names": tags}

    def complete(self, todo_id):
        return {"id": todo_id, "name": "Follow up", "status": "completed"}

    def cancel(self, todo_id):
        return {"id": todo_id, "name": "Follow up", "status": "canceled"}

    def restore_todo(self, todo):
        restored = dict(todo)
        restored["restored"] = True
        return restored

    def move(self, todo_id, list_name=None, project_name=None):
        return {"id": todo_id, "name": "Follow up", "status": "open", "list": list_name, "project": project_name}

    def create_project(self, name, notes=None, due=None, when=None, tags=None):
        return {"id": "project-new", "name": name, "notes": notes, "due": due, "when": when, "tag_names": tags, "status": "open"}

    def show(self, todo_id):
        return {"id": todo_id, "shown": True}


class CliTests(unittest.TestCase):
    def run_cli(self, argv):
        output = io.StringIO()
        error = io.StringIO()
        audit_file = tempfile.NamedTemporaryFile(delete=False)
        audit_file.close()
        with patch("things_cli.cli.ThingsClient", return_value=FakeClient()):
            with patch.dict(os.environ, {"THINGS_CLI_AUDIT_LOG": audit_file.name}):
                with redirect_stdout(output), redirect_stderr(error):
                    code = cli.main(argv)
        try:
            with open(audit_file.name, encoding="utf-8") as handle:
                audit_lines = handle.read().splitlines()
        finally:
            os.unlink(audit_file.name)
        return code, output.getvalue(), audit_lines

    def test_lists_human_output(self):
        code, output, _audit_lines = self.run_cli(["lists"])
        self.assertEqual(code, 0)
        self.assertIn("Inbox: 1 (inbox)", output)

    def test_diagnose_outputs_json(self):
        code, output, _audit_lines = self.run_cli(["diagnose"])
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertEqual(payload["app"], "Things")
        self.assertEqual(payload["lists"][0]["name"], "Inbox")

    def test_projects_tags_search_and_get(self):
        code, output, _audit_lines = self.run_cli(["--json", "projects"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)[0]["name"], "Networking")

        code, output, _audit_lines = self.run_cli(["tags"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)[0]["name"], "Follow Up")

        code, output, _audit_lines = self.run_cli(["--json", "search", "follow", "--limit", "1"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)[0]["id"], "abc")

        code, output, _audit_lines = self.run_cli(["get", "abc"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["id"], "abc")

    def test_list_json_output(self):
        code, output, _audit_lines = self.run_cli(["--json", "list", "--limit", "1"])
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertEqual(payload[0]["id"], "abc")

    def test_export_stdout_and_file_output(self):
        code, output, _audit_lines = self.run_cli(["export"])
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertEqual(payload["todos"][0]["id"], "abc")

        with tempfile.TemporaryDirectory() as tmpdir:
            export_path = Path(tmpdir) / "things.json"
            code, output, _audit_lines = self.run_cli(["export", "--output", str(export_path)])
            self.assertEqual(code, 0)
            self.assertIn("Wrote 1 todos", output)
            payload = json.loads(export_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["todos"][0]["id"], "abc")

    def test_add_dry_run_does_not_call_client_add(self):
        code, output, audit_lines = self.run_cli(["add", "New todo", "--notes", "Body", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertEqual(audit_lines, [])
        payload = json.loads(output)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["action"], "add")
        self.assertEqual(payload["payload"]["name"], "New todo")

    def test_add_with_yes_returns_after_and_audits(self):
        code, output, audit_lines = self.run_cli(["add", "New todo", "--notes", "Body", "--tags", "X, Y", "--yes"])
        self.assertEqual(code, 0)
        self.assertEqual(len(audit_lines), 1)
        payload = json.loads(output)
        event = json.loads(audit_lines[0])
        self.assertEqual(payload["action"], "add")
        self.assertEqual(payload["after"]["id"], "new")
        self.assertEqual(payload["after"]["tag_names"], "X, Y")
        self.assertTrue(event["verified"])

    def test_mutation_defaults_to_dry_run_without_yes(self):
        code, output, audit_lines = self.run_cli(["complete", "abc"])
        self.assertEqual(code, 0)
        self.assertEqual(audit_lines, [])
        payload = json.loads(output)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["payload"]["before"]["id"], "abc")

    def test_mutation_with_yes_returns_before_after(self):
        code, output, audit_lines = self.run_cli(["complete", "abc", "--yes"])
        self.assertEqual(code, 0)
        self.assertEqual(len(audit_lines), 1)
        payload = json.loads(output)
        event = json.loads(audit_lines[0])
        self.assertEqual(event["action"], "complete")
        self.assertEqual(payload["event_id"], event["event_id"])
        self.assertEqual(payload["before"]["status"], "open")
        self.assertEqual(payload["after"]["status"], "completed")
        self.assertTrue(payload["verified"])

    def test_update_move_and_cancel_with_yes_audit(self):
        code, output, audit_lines = self.run_cli(["update", "abc", "--name", "Renamed", "--tags", "One, Two", "--yes"])
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertEqual(payload["action"], "update")
        self.assertEqual(payload["after"]["name"], "Renamed")
        self.assertEqual(json.loads(audit_lines[0])["change"]["tags"], "One, Two")

        code, output, audit_lines = self.run_cli(["move", "abc", "--list", "Today", "--yes"])
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertEqual(payload["after"]["list"], "Today")
        self.assertEqual(json.loads(audit_lines[0])["action"], "move")

        code, output, audit_lines = self.run_cli(["cancel", "abc", "--yes"])
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertEqual(payload["after"]["status"], "canceled")
        self.assertEqual(json.loads(audit_lines[0])["action"], "cancel")

    def test_create_project_dry_run_and_yes(self):
        code, output, audit_lines = self.run_cli(["create-project", "Launch", "--tags", "Work"])
        self.assertEqual(code, 0)
        self.assertEqual(audit_lines, [])
        payload = json.loads(output)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["payload"]["name"], "Launch")

        code, output, audit_lines = self.run_cli(["create-project", "Launch", "--tags", "Work", "--yes"])
        self.assertEqual(code, 0)
        self.assertEqual(len(audit_lines), 1)
        payload = json.loads(output)
        self.assertEqual(payload["after"]["id"], "project-new")
        self.assertEqual(json.loads(audit_lines[0])["action"], "create-project")

    def test_show_outputs_result(self):
        code, output, _audit_lines = self.run_cli(["show", "abc"])
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertTrue(payload["shown"])

    def test_review_json_uses_export_snapshot(self):
        code, output, _audit_lines = self.run_cli(["--json", "review", "--today", "2026-04-26", "--limit", "1"])
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertEqual(payload["today"], "2026-04-26")
        self.assertEqual(payload["scope"], "today")

    def test_workflow_commands_return_json(self):
        commands = [
            ["--json", "triage", "--today", "2026-04-26", "--limit", "1"],
            ["--json", "attention", "--today", "2026-04-26", "--limit", "1"],
            ["--json", "applications", "--limit", "1"],
            ["--json", "followups", "--limit", "1"],
            ["--json", "stale", "--before", "2026-04-01", "--limit", "1"],
        ]
        for argv in commands:
            with self.subTest(argv=argv):
                code, output, _audit_lines = self.run_cli(argv)
                self.assertEqual(code, 0)
                json.loads(output)

    def test_review_supports_scope_all_and_named_list(self):
        code, output, _audit_lines = self.run_cli(["--json", "review", "--scope", "all", "--today", "2026-04-26"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["scope"], "all")

        code, output, _audit_lines = self.run_cli(["--json", "review", "--list", "Anytime", "--today", "2026-04-26"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)["scope"], "Anytime")

    def test_schema_outputs_contracts(self):
        code, output, _audit_lines = self.run_cli(["schema"])
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertIn("todo", payload)
        self.assertIn("audit-event", payload)

    def test_audit_summary_and_list(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as handle:
            handle.write(json.dumps({"event_id": "one", "timestamp": "2026-04-26T00:00:00+00:00", "action": "update"}) + "\n")
            handle.write(json.dumps({"event_id": "two", "timestamp": "2026-04-26T00:01:00+00:00", "action": "complete"}) + "\n")
            path = handle.name
        try:
            code, output, _audit_lines = self.run_cli(["audit", "summary", "--path", path])
            self.assertEqual(code, 0)
            summary = json.loads(output)
            self.assertEqual(summary["count"], 2)
            self.assertEqual(summary["by_action"]["update"], 1)

            code, output, _audit_lines = self.run_cli(["audit", "list", "--path", path, "--limit", "1"])
            self.assertEqual(code, 0)
            events = json.loads(output)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_id"], "two")
        finally:
            os.unlink(path)

    def test_diff_snapshots(self):
        before = {
            "todos": [
                {"id": "a", "name": "A", "status": "open", "tag_names": "One"},
                {"id": "b", "name": "B", "status": "open"},
            ]
        }
        after = {
            "todos": [
                {"id": "a", "name": "A changed", "status": "open", "tag_names": "Two"},
                {"id": "c", "name": "C", "status": "open"},
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            before_path = Path(tmpdir) / "before.json"
            after_path = Path(tmpdir) / "after.json"
            before_path.write_text(json.dumps(before), encoding="utf-8")
            after_path.write_text(json.dumps(after), encoding="utf-8")
            code, output, _audit_lines = self.run_cli(["--json", "diff", str(before_path), str(after_path)])
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertEqual(payload["added_count"], 1)
        self.assertEqual(payload["removed_count"], 1)
        self.assertEqual(payload["changed_count"], 1)

    def test_undo_defaults_to_dry_run(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as handle:
            handle.write(
                json.dumps(
                    {
                        "event_id": "evt-1",
                        "timestamp": "2026-04-26T00:00:00+00:00",
                        "action": "update",
                        "before": {"id": "abc", "name": "Old", "status": "open"},
                        "after": {"id": "abc", "name": "New", "status": "open"},
                    }
                )
                + "\n"
            )
            path = handle.name
        try:
            code, output, audit_lines = self.run_cli(["undo", "evt-1", "--path", path])
            self.assertEqual(code, 0)
            self.assertEqual(audit_lines, [])
            payload = json.loads(output)
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["payload"]["undo_plan"][0]["operation"], "restore")
        finally:
            os.unlink(path)

    def test_undo_with_yes_restores_and_audits(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as handle:
            handle.write(
                json.dumps(
                    {
                        "event_id": "evt-1",
                        "timestamp": "2026-04-26T00:00:00+00:00",
                        "action": "update",
                        "before": {"id": "abc", "name": "Old", "status": "open"},
                        "after": {"id": "abc", "name": "New", "status": "open"},
                    }
                )
                + "\n"
            )
            path = handle.name
        try:
            code, output, _audit_lines = self.run_cli(["undo", "evt-1", "--path", path, "--yes"])
            self.assertEqual(code, 0)
            payload = json.loads(output)
            self.assertEqual(payload["action"], "undo")
            self.assertTrue(payload["verified"])
            events = Path(path).read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(events), 2)
            self.assertEqual(json.loads(events[-1])["action"], "undo")
        finally:
            os.unlink(path)

    def test_undo_last_uses_recent_event(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as handle:
            handle.write(
                json.dumps(
                    {
                        "event_id": "older",
                        "timestamp": "2026-04-26T00:00:00+00:00",
                        "action": "complete",
                        "before": {"id": "old", "name": "Old", "status": "open"},
                        "after": {"id": "old", "name": "Old", "status": "completed"},
                    }
                )
                + "\n"
            )
            handle.write(
                json.dumps(
                    {
                        "event_id": "newer",
                        "timestamp": "2026-04-26T00:01:00+00:00",
                        "action": "update",
                        "before": {"id": "abc", "name": "Before", "status": "open"},
                        "after": {"id": "abc", "name": "After", "status": "open"},
                    }
                )
                + "\n"
            )
            path = handle.name
        try:
            code, output, _audit_lines = self.run_cli(["undo", "--last", "--path", path])
            self.assertEqual(code, 0)
            payload = json.loads(output)
            self.assertEqual(payload["payload"]["event_id"], "newer")
        finally:
            os.unlink(path)

    def test_bulk_yes_requires_guardrail(self):
        code, output, _audit_lines = self.run_cli(["bulk", "tag", "--query", "follow", "--tags", "X", "--yes"])
        self.assertEqual(code, 2)

    def test_bulk_max_allows_yes(self):
        code, output, audit_lines = self.run_cli(["bulk", "tag", "--query", "follow", "--tags", "X", "--max", "1", "--yes"])
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertEqual(payload["action"], "bulk tag")
        self.assertEqual(payload["count"], 1)
        self.assertEqual(len(audit_lines), 1)

    def test_bulk_ids_from_uses_exact_ids(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as handle:
            handle.write("abc\nabc\n")
            path = handle.name
        try:
            code, output, _audit_lines = self.run_cli(["bulk", "tag", "--ids-from", path, "--tags", "X"])
            self.assertEqual(code, 0)
            payload = json.loads(output)
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["payload"]["count"], 1)
            self.assertEqual(payload["payload"]["matches"][0]["id"], "abc")
        finally:
            os.unlink(path)

    def test_bulk_move_dry_run_and_yes(self):
        code, output, audit_lines = self.run_cli(["bulk", "move", "--query", "follow", "--list", "Today"])
        self.assertEqual(code, 0)
        self.assertEqual(audit_lines, [])
        payload = json.loads(output)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["payload"]["target"]["list"], "Today")

        code, output, audit_lines = self.run_cli(["bulk", "move", "--query", "follow", "--list", "Today", "--max", "1", "--yes"])
        self.assertEqual(code, 0)
        self.assertEqual(len(audit_lines), 1)
        payload = json.loads(output)
        self.assertEqual(payload["action"], "bulk move")
        self.assertEqual(payload["results"][0]["after"]["list"], "Today")


if __name__ == "__main__":
    unittest.main()
