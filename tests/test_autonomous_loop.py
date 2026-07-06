from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from analyst.autonomous import autonomy_status, record_outcome, run_autonomous_cycle


class AutonomousLoopTest(unittest.TestCase):
    def test_autonomous_cycle_logs_decision_verification_and_board(self) -> None:
        sample = Path("samples/line_review_short_stops.csv").resolve()
        with tempfile.TemporaryDirectory() as tmp:
            result = run_autonomous_cycle(
                data_path=sample,
                workspace=tmp,
                line="Line 1",
                use_llm=False,
            )

            self.assertTrue(Path(result.cycle_path).is_file())
            self.assertTrue(Path(result.decision_path).is_file())
            self.assertTrue(Path(result.verification_path).is_file())
            self.assertTrue(Path(result.board_path).is_file())
            self.assertTrue(result.artifacts)

            decisions = [
                json.loads(line)
                for line in Path(result.decision_path).read_text().splitlines()
                if line.strip()
            ]
            self.assertEqual(len(decisions), 1)
            decision = decisions[0]
            self.assertEqual(decision["decision_id"], result.decision_id)
            self.assertEqual(decision["cycle_id"], result.cycle_id)
            self.assertEqual(decision["line_id"], "Line 1")
            self.assertNotEqual(decision["constraint"], "unknown")
            self.assertIn(decision["autonomy_level"], {"L2_gated_local_artifacts", "L3_local_artifacts"})
            self.assertTrue(decision["expected_outcome"])
            self.assertTrue(decision["source_artifacts"])

            queue = json.loads(Path(result.verification_path).read_text())
            self.assertEqual({item["cadence"] for item in queue}, {"7 days", "30 days", "90 days"})
            self.assertTrue(all(item["status"] == "pending" for item in queue))

            board = Path(result.board_path).read_text()
            self.assertIn("Latest Decision", board)
            self.assertIn(result.decision_id, board)
            self.assertIn("Upcoming Verification", board)

            status = autonomy_status(workspace=tmp)
            self.assertEqual(status["decisions"], 1)
            self.assertEqual(status["pending_verifications"], 3)

    def test_record_outcome_updates_decision_queue_and_board(self) -> None:
        sample = Path("samples/line_review_short_stops.csv").resolve()
        with tempfile.TemporaryDirectory() as tmp:
            result = run_autonomous_cycle(
                data_path=sample,
                workspace=tmp,
                line="Line 1",
                use_llm=False,
            )

            outcome = record_outcome(
                workspace=tmp,
                decision_id=result.decision_id,
                quality="mixed",
                outcome="Constraint improved, but event coding stayed too vague to prove cause class.",
                helped="The watchlist forced the supervisor to check recurrence.",
                misled="Short Stop volume masked the actual equipment family.",
            )

            self.assertEqual(outcome["decision_id"], result.decision_id)
            self.assertEqual(outcome["quality"], "mixed")
            self.assertTrue(Path(outcome["board_path"]).is_file())

            decisions = [
                json.loads(line)
                for line in Path(result.decision_path).read_text().splitlines()
                if line.strip()
            ]
            self.assertEqual(decisions[0]["status"], "outcome_recorded")
            self.assertEqual(decisions[0]["outcome_quality"], "mixed")

            queue = json.loads(Path(result.verification_path).read_text())
            self.assertTrue(all(item["status"] == "observed" for item in queue))

            status = autonomy_status(workspace=tmp)
            self.assertEqual(status["outcomes"], 1)
            self.assertEqual(status["pending_verifications"], 0)


if __name__ == "__main__":
    unittest.main()