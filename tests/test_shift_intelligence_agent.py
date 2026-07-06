from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from analyst.agents.eval_runner import evaluate_report
from analyst.agents.workflow import run_shift_workflow_from_result
from analyst.agents.shift_intelligence import ShiftIntelligenceAgent
from analyst.engine import analyze
from analyst.parsers import DowntimeEvent, OEEInterval


def _event(event_id: int, start: datetime, minutes: int, equipment: str) -> DowntimeEvent:
    return DowntimeEvent(
        event_id=event_id,
        start_time=start,
        end_time=start + timedelta(minutes=minutes),
        duration_seconds=minutes * 60,
        line_id="line-1",
        line_raw_name="Line 1",
        equipment_id=equipment.lower().replace(" ", "_"),
        equipment_raw_name=equipment,
        event_type="downtime",
        loss_type="availability",
        is_equipment_fault=True,
        notes=None,
    )


class ShiftIntelligenceAgentTest(unittest.TestCase):
    def _chronic_result(self):
        base = datetime(2026, 1, 5, 23, 0)
        events = [
            _event(i, base + timedelta(minutes=i * 50), 45, "Tray Packer")
            for i in range(1, 18)
        ]
        events.extend([
            _event(100 + i, datetime(2026, 1, 6, 8, 0) + timedelta(hours=i), 5, "Labeler")
            for i in range(3)
        ])
        oee = [
            OEEInterval(
                timestamp=datetime(2026, 1, 5, hour, 0),
                line_id="line-1",
                line_raw_name="Line 1",
                availability=0.4,
                performance=0.8,
                quality=0.98,
                oee=0.31,
                mtbf_minutes=None,
                mttr_minutes=None,
                total_units=100,
                good_units=98,
                bad_units=2,
                downtime_seconds=1800,
                interval_seconds=3600,
                cases_per_hour=100,
            )
            for hour in (23, 0, 1, 2, 3, 4)
        ]
        return analyze(events, oee)

    def _kb(self):
        return {
            "equipment": [
                {
                    "area": "Tray Packer",
                    "event_count": 25,
                    "total_minutes": 1200,
                    "resolution_rate": 0.35,
                    "recurring_issues": [{"issue": "open flaps and jams", "count": 8}],
                    "known_fixes": [{"fix": "clean guides and verify timing"}],
                    "by_shift": {"3rd": 20},
                    "by_line": {"1": 25},
                }
            ]
        }

    def test_agent_uses_tools_and_escalates_chronic_constraint(self) -> None:
        result = self._chronic_result()
        kb = self._kb()

        report = ShiftIntelligenceAgent(kb=kb).run(
            result,
            "Repeated tray packer jams need recurrence and escalation review",
        ).to_dict()

        tool_names = [call["name"] for call in report["trace"]["tool_calls"]]
        self.assertIn("classify_agent_intent", tool_names)
        self.assertIn("query_oee_data", tool_names)
        self.assertIn("find_prior_rcas", tool_names)
        self.assertIn("draft_shift_passdown", tool_names)
        self.assertIn("build_recurrence_watchlist", tool_names)
        self.assertIn("schedule_verification_followups", tool_names)
        self.assertEqual(report["constraint"]["constraint"], "Tray Packer")
        self.assertEqual(report["risk"]["risk_level"], "high")
        self.assertTrue(report["approval_gate"]["required"])
        self.assertTrue(report["prior_rcas"]["has_prior_context"])
        self.assertTrue(report["recurrence_watchlist"]["items"])
        self.assertEqual(
            {item["when"] for item in report["verification_followups"]["cadence"]},
            {"7 days", "30 days", "90 days"},
        )
        self.assertTrue(report["final_answer"]["supervisor_actions"])

        eval_result = evaluate_report(report, {
            "id": "unit",
            "expected_tools": ["query_oee_data", "find_constraint_area", "find_prior_rcas"],
            "expected_constraint_contains": "tray",
            "expected_approval_required": True,
            "expected_intent": "recurrence",
        })
        self.assertTrue(eval_result.passed)

    def test_workflow_packages_analysis_agent_and_evals(self) -> None:
        result = self._chronic_result()
        kb = {
            "equipment": self._kb()["equipment"],
        }
        run = run_shift_workflow_from_result(
            result,
            scenario="Draft passdown, escalation, and verification workflow",
            kb=kb,
        ).to_dict()
        self.assertEqual(run["status"], "success")
        self.assertEqual(run["analysis"]["top_loss_driver"], "Tray Packer")
        self.assertEqual(run["agent_report"]["constraint"]["constraint"], "Tray Packer")
        self.assertIn("final_answer", run["agent_report"])
        self.assertTrue(run["run_id"].startswith("shift-intel-line-1-"))

    def test_short_stop_is_not_selected_over_caser_family(self) -> None:
        base = datetime(2026, 1, 5, 7, 0)
        events = []
        event_id = 1
        for i in range(40):
            events.append(_event(event_id, base + timedelta(minutes=i * 5), 2, "Short Stop"))
            event_id += 1
        for i in range(16):
            events.append(_event(event_id, base + timedelta(hours=8, minutes=i * 10), 8, "Caser - General Fault"))
            event_id += 1
        for i in range(14):
            events.append(_event(event_id, base + timedelta(hours=13, minutes=i * 10), 7, "Caser - Low Prime"))
            event_id += 1
        for i in range(4):
            events.append(_event(event_id, base + timedelta(hours=20, minutes=i * 20), 5, "Labeler"))
            event_id += 1

        result = analyze(events, [])
        report = ShiftIntelligenceAgent().run(
            result,
            "Build passdown, RCA, recurrence, and verification for the real constraint.",
        ).to_dict()

        self.assertEqual(report["constraint"]["constraint"], "Caser family")
        self.assertNotEqual(report["constraint"]["constraint"], "Short Stop")
        self.assertIn("Rolled-up codes", " ".join(report["constraint"]["evidence"]))
        self.assertEqual(report["recurrence_watchlist"]["items"][0]["equipment"], "Caser family")


if __name__ == "__main__":
    unittest.main()