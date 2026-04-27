import os
import unittest

from things_cli.client import ThingsClient


@unittest.skipUnless(os.environ.get("THINGS_LIVE_TESTS") == "1", "set THINGS_LIVE_TESTS=1 to run live Things tests")
class LiveThingsTests(unittest.TestCase):
    def setUp(self):
        self.client = ThingsClient()

    def test_diagnose_and_read_inbox(self):
        diag = self.client.diagnose()
        self.assertEqual(diag["app"], "Things")
        self.assertTrue(diag["automation_access_ok"])
        todos = self.client.list_todos("Inbox", limit=3)
        self.assertIsInstance(todos, list)

    def test_create_update_complete_smoke(self):
        todo = self.client.add(
            "things-cli live test",
            notes="Created by THINGS_LIVE_TESTS; may be left in Logbook.",
            tags="things-cli-test, Live Test",
            list_name="Inbox",
        )
        self.assertTrue(todo["id"])

        updated = self.client.update(todo["id"], name="things-cli live test updated", due="2026-04-27")
        self.assertEqual(updated["due"], "2026-04-27")

        completed = self.client.complete(todo["id"])
        self.assertEqual(completed["status"], "completed")


if __name__ == "__main__":
    unittest.main()
