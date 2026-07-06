from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from analyst.agentic_harness import ManufacturingAgenticHarness


class AgenticHarnessTest(unittest.TestCase):
    def test_harness_loads_markdown_runs_tools_and_writes_artifacts(self) -> None:
        sample = Path("samples/line_review_short_stops.csv").resolve()
        with tempfile.TemporaryDirectory() as tmp:
            harness = ManufacturingAgenticHarness(workspace=tmp, use_llm=False)
            run = harness.run(
                "Review 10 months of Line 1 data. Short Stops and Unassigned are suspected to be the highest codes.",
                data_path=sample,
                line="Line 1",
                photo_name="board.jpg",
            )

            self.assertEqual(run.plan["planner"], "fallback")
            self.assertIn("AGENT.md", run.behavior_files)
            self.assertIn("TOOLS.md", run.behavior_files)
            self.assertTrue(any(call.name == "inspect_data" for call in run.tool_calls))
            self.assertTrue(any(call.name == "run_line_review" for call in run.tool_calls))
            self.assertTrue(any(call.name == "build_operating_model" for call in run.tool_calls))
            self.assertTrue(any(call.name == "build_decision_cockpit" for call in run.tool_calls))
            self.assertTrue(any(call.name == "build_management_brief" for call in run.tool_calls))
            self.assertTrue(any(call.name == "build_event_fidelity_sprint" for call in run.tool_calls))
            self.assertTrue(run.artifacts)
            for artifact in run.artifacts:
                self.assertTrue(Path(artifact).is_file())
            self.assertTrue(any(Path(artifact).name == "operating-model.md" for artifact in run.artifacts))
            self.assertTrue(any(Path(artifact).name == "decision-cockpit.md" for artifact in run.artifacts))
            self.assertTrue(any(Path(artifact).name == "management-brief.md" for artifact in run.artifacts))
            self.assertTrue(any(Path(artifact).name == "event-fidelity-sprint.md" for artifact in run.artifacts))
            self.assertIn("visibility", run.final_answer.lower())
            self.assertTrue((Path(tmp) / "MEMORY.md").is_file())
            self.assertTrue(any(Path(tmp, "runs").glob("*.json")))

    def test_harness_rejects_data_outside_allowed_roots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            harness = ManufacturingAgenticHarness(workspace=tmp, use_llm=False)
            with self.assertRaisesRegex(ValueError, "allowed read root"):
                harness.run("Audit should not read arbitrary host files.", data_path="/etc/hosts")
            self.assertFalse((Path(tmp) / "inbox" / "hosts").exists())

    def test_harness_rejects_workspace_outside_allowed_roots(self) -> None:
        with self.assertRaisesRegex(ValueError, "allowed workspace root"):
            ManufacturingAgenticHarness(workspace="/etc/mfg-agent-test", use_llm=False)

    def test_planner_validation_drops_unknown_tools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            harness = ManufacturingAgenticHarness(workspace=tmp, use_llm=False)
            plan = harness._validate_plan({
                "role_focus": "CI Manager",
                "objective": "Build the next useful thing",
                "workflow": {"name": "Bad tool filter", "rationale": "Keep only safe tools"},
                "steps": [
                    {"tool": "write_artifact", "reason": "not allowed"},
                    {"tool": "run_line_review", "reason": "allowed"},
                    {"tool": "run_line_review", "reason": "duplicate"},
                ],
                "artifacts": [
                    {
                        "filename": "../../workflow",
                        "title": "Workflow",
                        "purpose": "Build bounded output",
                        "sections": ["Operating Judgment"],
                    }
                ],
            }, planner="unit")

            self.assertEqual(plan["steps"], [{"tool": "run_line_review", "reason": "allowed"}])
            self.assertNotIn("write_artifact", plan["allowed_tools"])
            self.assertEqual(plan["workflow"]["name"], "Bad tool filter")
            self.assertEqual(plan["artifacts"][0]["filename"], "workflow.md")

    def test_harness_builds_plan_authored_workflow_artifact(self) -> None:
        sample = Path("samples/line_review_short_stops.csv").resolve()
        with tempfile.TemporaryDirectory() as tmp:
            harness = ManufacturingAgenticHarness(workspace=tmp, use_llm=False)
            run = harness.run(
                "Build the supervisor, production manager, and CI workflow from this 10 month line review.",
                data_path=sample,
                line="Line 1",
            )

            self.assertTrue(any(call.name == "build_plan_artifact" for call in run.tool_calls))
            authored = [Path(path) for path in run.artifacts if Path(path).name == "agent-authored-workflow.md"]
            self.assertEqual(len(authored), 1)
            text = authored[0].read_text()
            self.assertIn("Supervisor Routine", text)
            self.assertIn("CI Experiment", text)


if __name__ == "__main__":
    unittest.main()