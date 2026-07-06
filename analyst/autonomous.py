"""Autonomous operating loop for the manufacturing agent harness.

The harness already knows how to inspect data, choose tools, and build
artifacts. This module adds the missing operating loop: decision capture,
verification scheduling, outcome capture, and an operating board.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .agentic_harness import ManufacturingAgenticHarness


DEFAULT_OBJECTIVE = (
    "Autonomous daily constraint cycle. Run a line review for visibility, "
    "then build passdown, RCA, recurrence watchlist, escalation guardrails, "
    "and 7/30/90 verification. Act only by writing local artifacts and logging "
    "decisions; do not make plant changes or send anything externally."
)

QUALITY_VALUES = {"good", "mixed", "bad"}


@dataclass(slots=True)
class AutonomousCycleResult:
    cycle_id: str
    harness_run_id: str
    decision_id: str
    workspace: str
    decision_path: str
    verification_path: str
    board_path: str
    cycle_path: str
    artifacts: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "harness_run_id": self.harness_run_id,
            "decision_id": self.decision_id,
            "workspace": self.workspace,
            "decision_path": self.decision_path,
            "verification_path": self.verification_path,
            "board_path": self.board_path,
            "cycle_path": self.cycle_path,
            "artifacts": self.artifacts,
        }


def run_autonomous_cycle(
    *,
    data_path: str | Path,
    workspace: str | Path = "agent-workspace",
    line: str | None = None,
    objective: str | None = None,
    use_llm: bool = False,
    model: str = "gpt-5-mini",
) -> AutonomousCycleResult:
    """Run one bounded autonomous manufacturing cycle.

    This is autonomous in the local-artifact sense: it observes data, decides
    what the operating constraint is, writes artifacts, schedules verification,
    and records the decision. It does not contact people or change plant state.
    """
    harness = ManufacturingAgenticHarness(workspace=workspace, use_llm=use_llm, model=model)
    message = objective or DEFAULT_OBJECTIVE
    run = harness.run(message, data_path=data_path, line=line)
    workspace_path = Path(run.workspace)
    store = _paths(workspace_path)
    _ensure_store(store)

    run_payload = run.to_dict()
    now = datetime.now(timezone.utc)
    cycle_id = _cycle_id(now)
    decision = _decision_from_run(cycle_id, run_payload, now=now, line=line)
    queue_items = _verification_items_from_decision(decision, run_payload, now=now)

    decisions = _read_jsonl(store["decisions"])
    decisions.append(decision)
    _write_jsonl(store["decisions"], decisions)

    queue = _read_json(store["queue"], default=[])
    queue.extend(queue_items)
    _write_json(store["queue"], queue)

    cycle_payload = {
        "cycle_id": cycle_id,
        "created_at": now.isoformat(),
        "objective": message,
        "harness_run": run_payload,
        "decision": decision,
        "verification_items": queue_items,
    }
    cycle_path = store["cycles"] / f"{cycle_id}.json"
    _write_json(cycle_path, cycle_payload)
    board_path = render_operating_board(workspace_path)

    return AutonomousCycleResult(
        cycle_id=cycle_id,
        harness_run_id=run.run_id,
        decision_id=decision["decision_id"],
        workspace=str(workspace_path),
        decision_path=str(store["decisions"]),
        verification_path=str(store["queue"]),
        board_path=str(board_path),
        cycle_path=str(cycle_path),
        artifacts=list(run.artifacts),
    )


def record_outcome(
    *,
    workspace: str | Path = "agent-workspace",
    decision_id: str,
    outcome: str,
    quality: str,
    helped: str = "",
    misled: str = "",
    verification_id: str | None = None,
) -> dict[str, Any]:
    """Record an observed outcome and fold it into decision/verification state."""
    quality = quality.lower().strip()
    if quality not in QUALITY_VALUES:
        raise ValueError(f"quality must be one of: {', '.join(sorted(QUALITY_VALUES))}")

    workspace_path = Path(workspace).expanduser().resolve()
    store = _paths(workspace_path)
    _ensure_store(store)
    decisions = _read_jsonl(store["decisions"])
    if not any(item.get("decision_id") == decision_id for item in decisions):
        raise ValueError(f"decision_id not found: {decision_id}")

    now = datetime.now(timezone.utc)
    outcome_id = "out_" + now.strftime("%Y%m%d-%H%M%S-%f")
    payload = {
        "outcome_id": outcome_id,
        "decision_id": decision_id,
        "verification_id": verification_id,
        "recorded_at": now.isoformat(),
        "quality": quality,
        "outcome": outcome,
        "helped": helped,
        "misled": misled,
    }

    outcomes = _read_jsonl(store["outcomes"])
    outcomes.append(payload)
    _write_jsonl(store["outcomes"], outcomes)

    for item in decisions:
        if item.get("decision_id") == decision_id:
            item["status"] = "outcome_recorded"
            item["outcome_id"] = outcome_id
            item["outcome_quality"] = quality
            item["observed_outcome"] = outcome
            item["observed_at"] = now.isoformat()
    _write_jsonl(store["decisions"], decisions)

    queue = _read_json(store["queue"], default=[])
    for item in queue:
        same_decision = item.get("decision_id") == decision_id
        same_verification = verification_id and item.get("verification_id") == verification_id
        if same_verification or (same_decision and verification_id is None):
            item["status"] = "observed"
            item["outcome_id"] = outcome_id
            item["closed_at"] = now.isoformat()
    _write_json(store["queue"], queue)
    board_path = render_operating_board(workspace_path)

    payload["board_path"] = str(board_path)
    return payload


def autonomy_status(*, workspace: str | Path = "agent-workspace") -> dict[str, Any]:
    """Return current autonomous operating state for CLI/API use."""
    workspace_path = Path(workspace).expanduser().resolve()
    store = _paths(workspace_path)
    _ensure_store(store)
    decisions = _read_jsonl(store["decisions"])
    queue = _read_json(store["queue"], default=[])
    outcomes = _read_jsonl(store["outcomes"])
    today = date.today()
    open_items = [item for item in queue if item.get("status") == "pending"]
    due_items = [
        item for item in open_items
        if _date_or_none(item.get("due_date")) and _date_or_none(item.get("due_date")) <= today
    ]
    return {
        "workspace": str(workspace_path),
        "decisions": len(decisions),
        "open_decisions": len([item for item in decisions if item.get("status") != "outcome_recorded"]),
        "outcomes": len(outcomes),
        "pending_verifications": len(open_items),
        "due_verifications": len(due_items),
        "latest_decision": decisions[-1] if decisions else None,
        "due_items": due_items,
        "board_path": str(store["board"]),
    }


def render_operating_board(workspace: str | Path = "agent-workspace") -> Path:
    """Render a markdown board humans can scan between cycles."""
    workspace_path = Path(workspace).expanduser().resolve()
    store = _paths(workspace_path)
    _ensure_store(store)
    decisions = _read_jsonl(store["decisions"])
    queue = _read_json(store["queue"], default=[])
    outcomes = _read_jsonl(store["outcomes"])

    today = date.today()
    open_queue = [item for item in queue if item.get("status") == "pending"]
    due = [
        item for item in open_queue
        if _date_or_none(item.get("due_date")) and _date_or_none(item.get("due_date")) <= today
    ]
    upcoming = [
        item for item in open_queue
        if _date_or_none(item.get("due_date")) and _date_or_none(item.get("due_date")) > today
    ]
    upcoming.sort(key=lambda item: item.get("due_date", ""))

    lines = [
        "# Autonomous Manufacturing Operating Board",
        "",
        f"Updated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Counts",
        "",
        f"- Decisions logged: {len(decisions)}",
        f"- Outcomes recorded: {len(outcomes)}",
        f"- Pending verifications: {len(open_queue)}",
        f"- Due now: {len(due)}",
        "",
        "## Latest Decision",
        "",
    ]
    if decisions:
        latest = decisions[-1]
        lines.extend([
            f"- Decision: {latest.get('decision_id')}",
            f"- Constraint: {latest.get('constraint')}",
            f"- Risk: {latest.get('risk_level')} ({latest.get('risk_score')}/100)",
            f"- Autonomy: {latest.get('autonomy_level')}",
            f"- Status: {latest.get('status')}",
            f"- Approval required: {latest.get('approval_required')}",
            f"- Expected outcome: {latest.get('expected_outcome')}",
            "",
            "Evidence:",
        ])
        for item in latest.get("evidence", [])[:6]:
            lines.append(f"- {item}")
    else:
        lines.append("No decisions logged yet.")

    lines.extend(["", "## Due Verification", ""])
    if due:
        for item in due:
            lines.extend(_verification_lines(item))
    else:
        lines.append("No verification items are due.")

    lines.extend(["", "## Upcoming Verification", ""])
    if upcoming:
        for item in upcoming[:12]:
            lines.extend(_verification_lines(item))
    else:
        lines.append("No upcoming verification items.")

    lines.extend(["", "## Recent Outcomes", ""])
    if outcomes:
        for item in outcomes[-8:]:
            lines.append(
                f"- {item.get('recorded_at')}: {item.get('decision_id')} -> "
                f"{item.get('quality')} - {item.get('outcome')}"
            )
    else:
        lines.append("No outcomes recorded yet.")

    _atomic_write_text(store["board"], "\n".join(lines).strip() + "\n")
    return store["board"]


def _decision_from_run(
    cycle_id: str,
    run_payload: dict[str, Any],
    *,
    now: datetime,
    line: str | None,
) -> dict[str, Any]:
    workflow = _tool_output(run_payload, "run_shift_workflow")
    review = _tool_output(run_payload, "run_line_review")
    report = workflow.get("agent_report", {})
    final = report.get("final_answer", {})
    decision = final.get("decision", {})
    risk = report.get("risk", {})
    approval = report.get("approval_gate", {})
    constraint = (
        decision.get("constraint")
        or report.get("constraint", {}).get("constraint")
        or review.get("decision_cockpit", {}).get("suspected_constraint")
        or review.get("operating_model", {}).get("recorded_signal")
        or "unknown"
    )
    risk_level = decision.get("risk_level") or risk.get("risk_level") or "unknown"
    risk_score = decision.get("risk_score") if decision.get("risk_score") is not None else risk.get("risk_score")
    approval_required = bool(decision.get("approval_required") or approval.get("required"))
    evidence = list(final.get("evidence") or [])
    evidence.extend(str(item) for item in risk.get("reasons", []))
    if not evidence and review:
        for key in ("management_signal", "masking_summary"):
            if review.get(key):
                evidence.append(str(review[key]))

    if approval_required:
        autonomy_level = "L2_gated_local_artifacts"
        status = "pending_approval"
        action_type = "human_gated_escalation"
    else:
        autonomy_level = "L3_local_artifacts"
        status = "active"
        action_type = "supervisor_followup"

    due_dates = _due_dates_from_report(report, now)
    first_check = due_dates[0]["due_date"] if due_dates else (now.date() + timedelta(days=7)).isoformat()
    return {
        "decision_id": "dec_" + now.strftime("%Y%m%d-%H%M%S-%f"),
        "cycle_id": cycle_id,
        "created_at": now.isoformat(),
        "line_id": line or review.get("line_id") or workflow.get("analysis", {}).get("line_id"),
        "constraint": constraint,
        "risk_level": risk_level,
        "risk_score": risk_score if risk_score is not None else 0,
        "approval_required": approval_required,
        "approvers": approval.get("approvers", decision.get("approvers", [])),
        "autonomy_level": autonomy_level,
        "status": status,
        "action_type": action_type,
        "reversibility": "reversible_local_artifacts",
        "expected_outcome": (
            f"By {first_check}, {constraint} should show lower event count, downtime, "
            "or repeat rate versus baseline; otherwise capture why the recommendation failed."
        ),
        "check_dates": due_dates,
        "evidence": evidence[:10],
        "source_harness_run_id": run_payload.get("run_id"),
        "source_artifacts": run_payload.get("artifacts", []),
    }


def _verification_items_from_decision(
    decision: dict[str, Any],
    run_payload: dict[str, Any],
    *,
    now: datetime,
) -> list[dict[str, Any]]:
    workflow = _tool_output(run_payload, "run_shift_workflow")
    report = workflow.get("agent_report", {})
    followups = report.get("verification_followups", {}).get("cadence", [])
    if not followups:
        followups = [
            {"when": "7 days", "owner": "supervisor", "check": "Did event count and repeat rate fall versus baseline?"},
            {"when": "30 days", "owner": "maintenance_lead", "check": "Did the countermeasure hold without recurrence?"},
            {"when": "90 days", "owner": "production_manager", "check": "Can the watchlist item close based on sustained improvement?"},
        ]

    items = []
    for raw in followups:
        due_date = _due_date_from_when(str(raw.get("when", "")), now)
        cadence = str(raw.get("when") or "verification")
        items.append({
            "verification_id": "ver_" + now.strftime("%Y%m%d-%H%M%S-%f") + "_" + _slug(cadence),
            "decision_id": decision["decision_id"],
            "cycle_id": decision["cycle_id"],
            "created_at": now.isoformat(),
            "due_date": due_date.isoformat(),
            "cadence": cadence,
            "owner": raw.get("owner") or "supervisor",
            "constraint": decision.get("constraint"),
            "check": raw.get("check") or decision.get("expected_outcome"),
            "status": "pending",
        })
    return items


def _due_dates_from_report(report: dict[str, Any], now: datetime) -> list[dict[str, str]]:
    cadence = report.get("verification_followups", {}).get("cadence", [])
    return [
        {
            "cadence": str(item.get("when") or "verification"),
            "due_date": _due_date_from_when(str(item.get("when", "")), now).isoformat(),
            "owner": str(item.get("owner") or "supervisor"),
            "check": str(item.get("check") or ""),
        }
        for item in cadence
    ]


def _tool_output(run_payload: dict[str, Any], tool_name: str) -> dict[str, Any]:
    for call in run_payload.get("tool_calls", []):
        if call.get("name") == tool_name and isinstance(call.get("output"), dict):
            return call["output"]
    return {}


def _paths(workspace: Path) -> dict[str, Path]:
    base = workspace / "autonomy"
    return {
        "base": base,
        "cycles": base / "cycles",
        "decisions": base / "decisions.jsonl",
        "queue": base / "verification_queue.json",
        "outcomes": base / "outcomes.jsonl",
        "board": base / "operating-board.md",
    }


def _ensure_store(paths: dict[str, Path]) -> None:
    paths["cycles"].mkdir(parents=True, exist_ok=True)
    if not paths["decisions"].exists():
        _atomic_write_text(paths["decisions"], "")
    if not paths["outcomes"].exists():
        _atomic_write_text(paths["outcomes"], "")
    if not paths["queue"].exists():
        _write_json(paths["queue"], [])


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    items = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        items.append(json.loads(line))
    return items


def _write_jsonl(path: Path, items: list[dict[str, Any]]) -> None:
    text = "".join(json.dumps(item, sort_keys=True) + "\n" for item in items)
    _atomic_write_text(path, text)


def _read_json(path: Path, *, default: Any) -> Any:
    if not path.exists():
        return default
    text = path.read_text().strip()
    if not text:
        return default
    return json.loads(text)


def _write_json(path: Path, payload: Any) -> None:
    _atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(text)
        tmp_name = handle.name
    os.replace(tmp_name, path)


def _cycle_id(now: datetime) -> str:
    return "cycle_" + now.strftime("%Y%m%d-%H%M%S-%f")


def _due_date_from_when(value: str, now: datetime) -> date:
    lowered = value.lower()
    if "90" in lowered:
        return now.date() + timedelta(days=90)
    if "30" in lowered:
        return now.date() + timedelta(days=30)
    if "7" in lowered:
        return now.date() + timedelta(days=7)
    return now.date() + timedelta(days=7)


def _date_or_none(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _verification_lines(item: dict[str, Any]) -> list[str]:
    return [
        f"- {item.get('due_date')} [{item.get('cadence')}] {item.get('constraint')}",
        f"  Owner: {item.get('owner')}",
        f"  Check: {item.get('check')}",
        f"  ID: {item.get('verification_id')}",
    ]


def _slug(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
    return slug or "check"