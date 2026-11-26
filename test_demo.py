import unittest
from unittest.mock import Mock

from demo import CASES, lookup_refund, replay, unsupported


class ReplayTests(unittest.TestCase):
    def test_baseline_exposes_false_confirmations(self):
        self.assertEqual([unsupported(replay(t, "baseline")) for t in CASES], [1, 0, 1, 0, None])

    def test_candidate_matches_frozen_evidence(self):
        expected = ["Your refund is pending.", "Your refund is complete.", "The refund failed.",
                    "I couldn't verify your refund status.", "I couldn't verify your refund status."]
        for turn, reply in zip(CASES, expected, strict=True):
            with self.subTest(turn=turn):
                lookup = Mock(wraps=lookup_refund)
                result = replay(turn, "candidate", lookup)
                lookup.assert_called_once_with(turn["refund_id"], turn["snapshot"])
                self.assertEqual(result["reply"], reply)
                self.assertEqual(unsupported(result), None if turn["snapshot"] is None else 0)

    def test_followup_is_same_refund_and_thread(self):
        first, second = CASES[:2]
        for key in ("thread_id", "refund_id"):
            self.assertEqual(first[key], second[key])
        self.assertLess(first["at"], second["at"])
