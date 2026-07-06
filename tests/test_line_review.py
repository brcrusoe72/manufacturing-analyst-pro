from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from analyst.line_review import render_markdown_report, run_line_review
from analyst.parsers import DowntimeEvent, OEEInterval


def _event(event_id: int, start: datetime, minutes: int, code: str) -> DowntimeEvent:
    return DowntimeEvent(
        event_id=event_id,
        start_time=start,
        end_time=start + timedelta(minutes=minutes),
        duration_seconds=minutes * 60,
        line_id="line-7",
        line_raw_name="Line 7",
        equipment_id=code.lower().replace(" ", "_"),
        equipment_raw_name=code,
        event_type="downtime",
        loss_type="availability",
        is_equipment_fault=code not in {"Short Stop", "Unassigned"},
        notes=None,
    )


class LineReviewTest(unittest.TestCase):
    def test_short_stops_and_unassigned_drive_visibility_verdict(self) -> None:
        events = []
        event_id = 1
        for month in range(1, 11):
            base = datetime(2026, month, 5, 7, 0)
            for i in range(12):
                events.append(_event(event_id, base + timedelta(hours=i), 4, "Short Stop"))
                event_id += 1
            for i in range(8):
                events.append(_event(event_id, base + timedelta(hours=20 + i), 9, "Unassigned"))
                event_id += 1
            for i in range(4):
                events.append(_event(event_id, base + timedelta(days=1, hours=i), 30, "Tray Packer"))
                event_id += 1

        oee = [
            OEEInterval(
                timestamp=datetime(2026, month, 5, 8),
                line_id="line-7",
                line_raw_name="Line 7",
                availability=0.72,
                performance=0.8,
                quality=0.99,
                oee=0.57,
                mtbf_minutes=None,
                mttr_minutes=None,
                total_units=100,
                good_units=99,
                bad_units=1,
                downtime_seconds=900,
                interval_seconds=3600,
                cases_per_hour=100,
            )
            for month in range(1, 11)
        ]

        review = run_line_review(
            events,
            oee,
            line_hint="Line 7",
            context="One line, ten months, chronic uncoded downtime.",
            photo_name="line-board.jpg",
        )

        self.assertEqual(review.months_covered, 10)
        self.assertLess(review.visibility_score, 55)
        self.assertIn("visibility problem", review.visibility_verdict)
        self.assertEqual({brief.role for brief in review.role_briefs}, {
            "Production Supervisor",
            "Production Manager",
            "CI Manager",
        })
        self.assertTrue(any("event-fidelity" in action for brief in review.role_briefs for action in brief.actions))
        self.assertEqual(review.photo_summary, "Photo/context artifact attached: line-board.jpg")

        rendered = render_markdown_report(review)
        self.assertIn("Line Intelligence Review", rendered)
        self.assertIn("Production Manager", rendered)
        self.assertIn("Short Stops", rendered)

    def test_actionable_constraints_roll_up_caser_under_short_stop_mask(self) -> None:
        events = []
        event_id = 1
        base = datetime(2026, 1, 5, 7, 0)
        for i in range(40):
            events.append(_event(event_id, base + timedelta(minutes=i * 8), 2, "Short Stop"))
            event_id += 1
        for i in range(12):
            events.append(_event(event_id, base + timedelta(hours=8, minutes=i * 12), 6, "Caser - General Fault"))
            event_id += 1
        for i in range(10):
            events.append(_event(event_id, base + timedelta(hours=12, minutes=i * 12), 5, "Caser - Carton MisPick"))
            event_id += 1
        for i in range(6):
            events.append(_event(event_id, base + timedelta(hours=18, minutes=i * 20), 4, "Tray Packer"))
            event_id += 1

        review = run_line_review(
            events,
            [],
            line_hint="Line 7",
            context=(
                "Short Stop masking check. Sometimes product flow outruns the palletizer; "
                "a palletizer operator can clear the issue before the code explains the cause."
            ),
        )

        self.assertEqual(review.actionable_constraints[0].name, "Caser family")
        self.assertEqual(review.decision_cockpit.suspected_constraint, "Caser family")
        self.assertIn("Verify Caser family", review.decision_cockpit.decision)
        self.assertIn("best recorded signal", review.decision_cockpit.decision)
        self.assertNotEqual(review.actionable_constraints[0].name, "Short Stop")
        self.assertIn("Short Stop/Unassigned are symptom buckets", review.masking_summary)
        self.assertTrue(any("maintenance" in question.lower() for question in review.maintenance_questions))
        self.assertEqual(review.operating_model.recorded_signal, "Caser family")
        self.assertTrue(any(item["class"] == "Flow/Handoff" and item["active"] for item in review.operating_model.cause_classes))
        self.assertTrue(any(item["class"] == "Person/Process" and item["active"] for item in review.operating_model.cause_classes))
        self.assertTrue(any("not a proven root cause" in risk for risk in review.operating_model.attribution_risks))

        rendered = render_markdown_report(review)
        self.assertIn("Actionable Constraint Candidates", rendered)
        self.assertIn("Decision Cockpit", rendered)
        self.assertIn("Operating Model", rendered)
        self.assertIn("Caser family", rendered)
        self.assertIn("Maintenance Questions", rendered)

    def test_decision_cockpit_carries_job_and_target_context(self) -> None:
        base = datetime(2026, 1, 5, 7, 0)
        events = [
            _event(1, base, 10, "Short Stop"),
            _event(2, base + timedelta(minutes=20), 15, "Caser - Low Prime"),
            _event(3, base + timedelta(minutes=50), 15, "Caser - Carton MisPick"),
        ]
        oee = [
            OEEInterval(
                timestamp=base,
                line_id="line-7",
                line_raw_name="Line 7",
                availability=0.7,
                performance=0.82,
                quality=0.99,
                oee=0.57,
                mtbf_minutes=None,
                mttr_minutes=None,
                total_units=100,
                good_units=99,
                bad_units=1,
                downtime_seconds=600,
                interval_seconds=3600,
                cases_per_hour=100,
                job_id="12345",
                job_label="01/05/2026 55112 (2000376) 1/8-15.25OZ_DM WK GOLD CORN",
                actual_calculation_units=820,
                target_units=1000,
                theoretical_units=1000,
                rate_loss_seconds=120,
                net_operation_seconds=3600,
            )
        ]

        review = run_line_review(events, oee, line_hint="Line 7", context="Target context check.")

        self.assertEqual(review.decision_cockpit.target_attainment["below_target_rate"], 1.0)
        self.assertEqual(review.decision_cockpit.job_signals[0]["sku"], "2000376")
        self.assertEqual(review.decision_cockpit.sku_signals[0]["sku"], "2000376")
        self.assertIn("SKU rollups", review.decision_cockpit.sku_status)


if __name__ == "__main__":
    unittest.main()