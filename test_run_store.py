import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from types import SimpleNamespace
from run_store import RunStore
from ui_server import run_query


class RunHistoryTests(unittest.TestCase):
    def test_failure_after_lookup_survives_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "history.sqlite3"
            store = RunStore(path)
            run_id = store.start("Refund?", "pending")
            call = SimpleNamespace(id="1", function=SimpleNamespace(
                name="lookup_refund", arguments='{"refund_id":"demo-refund-7"}'))
            choice = SimpleNamespace(finish_reason="tool_calls", message=Mock(tool_calls=[call]))
            complete = Mock(side_effect=[SimpleNamespace(choices=[choice]), RuntimeError("model unavailable")])
            with self.assertRaisesRegex(RuntimeError, "model unavailable"):
                run_query("pending", "Refund?", False, complete, "demo",
                          lambda turn, event: store.append(run_id, turn, event))
            store.finish(run_id, "Failed")
            interrupted = store.start("Another question", "timeout")
            reopened = RunStore(path)
            self.assertEqual(reopened.read(interrupted)["status"], "Interrupted")
            saved = reopened.read(run_id)
            self.assertEqual(saved["status"], "Failed")
            self.assertEqual([e["stage"] for e in saved["events"]],
                             ["Prepared fixture", "Customer question", "Model requested a tool", "Payment lookup"])
            self.assertEqual(saved["events"][-1]["data"]["state"], "pending")
