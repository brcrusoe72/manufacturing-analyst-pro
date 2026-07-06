"""Evaluation runner for Shift Intelligence Agent scenarios."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..engine import AnalysisResult
from .shift_intelligence import ShiftIntelligenceAgent


@dataclass(slots=True)
class EvalResult:
    scenario_id: str
    passed: bool
    score: int
    checks: list[dict[str, Any]]
    report: dict[str, Any]


def load_scenarios(path: str | Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text())
    if isinstance(data, dict):
        return data.get("scenarios", [])
    return data


def evaluate_report(report: dict[str, Any], scenario: dict[str, Any]) -> EvalResult:
    checks: list[dict[str, Any]] = []

    expected_tools = scenario.get("expected_tools", [])
    actual_tools = [call["name"] for call in report.get("trace", {}).get("tool_calls", [])]
    for tool_name in expected_tools:
        ok = tool_name in actual_tools
        checks.append({"name": f"uses_{tool_name}", "passed": ok, "detail": actual_tools})

    expected_constraint = scenario.get("expected_constraint_contains")
    if expected_constraint:
        actual = report.get("constraint", {}).get("constraint", "").lower()
        ok = expected_constraint.lower() in actual
        checks.append({"name": "expected_constraint", "passed": ok, "detail": actual})

    if scenario.get("requires_grounding", True):
        evidence = report.get("constraint", {}).get("evidence", [])
        ok = bool(evidence) and any(any(ch.isdigit() for ch in item) for item in evidence)
        checks.append({"name": "grounded_numeric_evidence", "passed": ok, "detail": evidence})

    expected_approval = scenario.get("expected_approval_required")
    if expected_approval is not None:
        actual = bool(report.get("approval_gate", {}).get("required"))
        checks.append({"name": "approval_gate", "passed": actual == expected_approval, "detail": actual})

    expected_intent = scenario.get("expected_intent")
    if expected_intent:
        intents = report.get("intent", {}).get("intents", [])
        checks.append({"name": "expected_intent", "passed": expected_intent in intents, "detail": intents})

    if scenario.get("requires_action_plan", True):
        actions = report.get("action_plan", {}).get("actions", [])
        ok = bool(actions) and all(item.get("owner") and item.get("due") and item.get("action") for item in actions[:3])
        checks.append({"name": "action_plan_complete", "passed": ok, "detail": actions[:3]})

    if scenario.get("requires_watchlist", True):
        watch = report.get("recurrence_watchlist", {}).get("items", [])
        checks.append({"name": "recurrence_watchlist", "passed": bool(watch), "detail": watch[:3]})

    if scenario.get("requires_verification", True):
        cadence = report.get("verification_followups", {}).get("cadence", [])
        labels = {item.get("when") for item in cadence}
        ok = {"7 days", "30 days", "90 days"} <= labels
        checks.append({"name": "verification_cadence", "passed": ok, "detail": cadence})

    if scenario.get("requires_final_answer", True):
        answer = report.get("final_answer", {})
        ok = bool(answer.get("decision")) and bool(answer.get("supervisor_actions")) and bool(answer.get("guardrails"))
        checks.append({"name": "final_answer_shape", "passed": ok, "detail": answer})

    passed_count = sum(1 for check in checks if check["passed"])
    score = round((passed_count / max(len(checks), 1)) * 100)
    return EvalResult(
        scenario_id=scenario.get("id", "unknown"),
        passed=all(check["passed"] for check in checks),
        score=score,
        checks=checks,
        report=report,
    )


def run_evals(result: AnalysisResult, scenarios: list[dict[str, Any]], *, kb: dict[str, Any] | None = None) -> dict[str, Any]:
    agent = ShiftIntelligenceAgent(kb=kb)
    eval_results: list[EvalResult] = []
    for scenario in scenarios:
        report = agent.run(result, scenario.get("input", scenario.get("id", ""))).to_dict()
        eval_results.append(evaluate_report(report, scenario))

    return {
        "total": len(eval_results),
        "passed": sum(1 for item in eval_results if item.passed),
        "avg_score": round(sum(item.score for item in eval_results) / max(len(eval_results), 1), 1),
        "results": [
            {
                "scenario_id": item.scenario_id,
                "passed": item.passed,
                "score": item.score,
                "checks": item.checks,
            }
            for item in eval_results
        ],
    }