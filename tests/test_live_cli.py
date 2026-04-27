import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
THINGS = ROOT / ".venv" / "bin" / "things"


@unittest.skipUnless(os.environ.get("THINGS_LIVE_TESTS") == "1", "set THINGS_LIVE_TESTS=1 to run live Things CLI tests")
class LiveThingsCliTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.tmpdir.name)
        self.audit_log = self.tmp / "mutations.jsonl"

    def tearDown(self):
        self.tmpdir.cleanup()

    def run_things(self, *args, check=True):
        env = {
            **os.environ,
            "THINGS_CLI_AUDIT_LOG": str(self.audit_log),
        }
        proc = subprocess.run(
            [str(THINGS), *args],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if check and proc.returncode != 0:
            self.fail(f"things {' '.join(args)} failed with {proc.returncode}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")
        return proc

    def json_command(self, *args):
        proc = self.run_things("--json", *args)
        return json.loads(proc.stdout)

    def test_read_commands_and_workflows(self):
        diag = self.json_command("diagnose")
        self.assertEqual(diag["app"], "Things")
        self.assertTrue(diag["automation_access_ok"])

        lists = self.json_command("lists")
        self.assertTrue(any(item["name"] == "Inbox" for item in lists))

        self.assertIsInstance(self.json_command("projects"), list)
        self.assertIsInstance(self.json_command("tags"), list)
        self.assertIsInstance(self.json_command("list", "--list", "Today", "--limit", "2"), list)
        self.assertIsInstance(self.json_command("search", "things-cli-live-test", "--limit", "2"), list)

        snapshot_path = self.tmp / "snapshot.json"
        proc = self.run_things("export", "--output", str(snapshot_path))
        self.assertIn("Wrote", proc.stdout)
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        self.assertIn("todos", snapshot)

        diff = self.json_command("diff", str(snapshot_path), str(snapshot_path))
        self.assertEqual(diff["changed_count"], 0)

        self.assertIn("todo", self.json_command("schema"))
        self.assertEqual(self.json_command("audit", "summary")["count"], 0)
        self.assertEqual(self.json_command("audit", "list"), [])

        for command in ("review", "triage", "attention", "applications", "followups", "stale"):
            with self.subTest(command=command):
                self.json_command(command, "--limit", "2")

    def test_live_mutation_commands_with_previews_audit_and_undo(self):
        before_path = self.tmp / "before-mutations.json"
        self.run_things("export", "--output", str(before_path))
        self.assertTrue(before_path.exists())

        marker = f"things-cli-live-test-{os.getpid()}"
        preview = self.run_things("add", marker, "--notes", "Created by live CLI test; may be left canceled.", "--tags", "things-cli-test")
        self.assertTrue(json.loads(preview.stdout)["dry_run"])

        created = json.loads(
            self.run_things(
                "add",
                marker,
                "--notes",
                "Created by live CLI test; may be left canceled.",
                "--tags",
                "things-cli-test",
                "--yes",
            ).stdout
        )
        todo_id = created["after"]["id"]
        self.assertTrue(todo_id)

        try:
            self.assertEqual(self.json_command("get", todo_id)["id"], todo_id)
            self.assertTrue(self.json_command("show", todo_id)["shown"])

            update_preview = json.loads(self.run_things("update", todo_id, "--name", f"{marker}-updated").stdout)
            self.assertTrue(update_preview["dry_run"])
            updated = json.loads(self.run_things("update", todo_id, "--name", f"{marker}-updated", "--due", "2026-04-27", "--yes").stdout)
            self.assertEqual(updated["after"]["name"], f"{marker}-updated")
            self.assertEqual(updated["after"]["due"], "2026-04-27")

            move_preview = json.loads(self.run_things("move", todo_id, "--list", "Today").stdout)
            self.assertTrue(move_preview["dry_run"])
            moved = json.loads(self.run_things("move", todo_id, "--list", "Today", "--yes").stdout)
            self.assertEqual(moved["after"]["id"], todo_id)

            ids_path = self.tmp / "ids.txt"
            ids_path.write_text(todo_id + "\n", encoding="utf-8")

            bulk_tag_preview = json.loads(self.run_things("bulk", "tag", "--ids-from", str(ids_path), "--tags", "things-cli-test, bulk-live").stdout)
            self.assertTrue(bulk_tag_preview["dry_run"])
            bulk_tag = json.loads(self.run_things("bulk", "tag", "--ids-from", str(ids_path), "--tags", "things-cli-test, bulk-live", "--yes").stdout)
            self.assertEqual(bulk_tag["count"], 1)

            bulk_move_preview = json.loads(self.run_things("bulk", "move", "--ids-from", str(ids_path), "--list", "Tomorrow").stdout)
            self.assertTrue(bulk_move_preview["dry_run"])
            bulk_move = json.loads(self.run_things("bulk", "move", "--ids-from", str(ids_path), "--list", "Tomorrow", "--yes").stdout)
            self.assertEqual(bulk_move["count"], 1)

            complete_preview = json.loads(self.run_things("complete", todo_id).stdout)
            self.assertTrue(complete_preview["dry_run"])
            completed = json.loads(self.run_things("complete", todo_id, "--yes").stdout)
            self.assertEqual(completed["after"]["status"], "completed")

            undo_preview = json.loads(self.run_things("undo", "--last").stdout)
            self.assertTrue(undo_preview["dry_run"])
            undone = json.loads(self.run_things("undo", "--last", "--yes").stdout)
            self.assertTrue(undone["verified"])

            cancel_preview = json.loads(self.run_things("cancel", todo_id).stdout)
            self.assertTrue(cancel_preview["dry_run"])
            canceled = json.loads(self.run_things("cancel", todo_id, "--yes").stdout)
            self.assertEqual(canceled["after"]["status"], "canceled")
        finally:
            current = self.json_command("get", todo_id)
            if current.get("status") == "open":
                self.run_things("cancel", todo_id, "--yes", check=False)

        events = [json.loads(line) for line in self.audit_log.read_text(encoding="utf-8").splitlines()]
        self.assertGreaterEqual(len(events), 7)
        self.assertTrue(all(event.get("verified") for event in events))

    def test_create_project_preview_and_live_cancel_cleanup(self):
        before_path = self.tmp / "before-project.json"
        self.run_things("export", "--output", str(before_path))
        self.assertTrue(before_path.exists())

        marker = f"things-cli-live-project-{os.getpid()}"
        preview = json.loads(self.run_things("create-project", marker, "--tags", "things-cli-test").stdout)
        self.assertTrue(preview["dry_run"])

        created = json.loads(self.run_things("create-project", marker, "--tags", "things-cli-test", "--yes").stdout)
        project_id = created["after"]["id"]
        self.assertTrue(project_id)

        cancel_preview = json.loads(self.run_things("cancel", project_id).stdout)
        self.assertTrue(cancel_preview["dry_run"])
        canceled = json.loads(self.run_things("cancel", project_id, "--yes").stdout)
        self.assertEqual(canceled["after"]["status"], "canceled")

    def test_live_error_paths_return_nonzero(self):
        missing_todo = self.run_things("get", "things-cli-missing-id", check=False)
        self.assertEqual(missing_todo.returncode, 2)
        self.assertIn("Things Apple Events call failed", missing_todo.stderr)

        missing_list = self.run_things("list", "--list", "things-cli-missing-list", check=False)
        self.assertEqual(missing_list.returncode, 2)
        self.assertIn("Things Apple Events call failed", missing_list.stderr)

        bad_date = self.run_things("add", "things-cli bad date", "--due", "tomorrow", "--yes", check=False)
        self.assertEqual(bad_date.returncode, 2)
        self.assertIn("Things Apple Events call failed", bad_date.stderr)


if __name__ == "__main__":
    unittest.main()
