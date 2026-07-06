"""Root-to-tip workflow for the manufacturing Shift Intelligence Agent."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..engine import AnalysisResult, analyze
from ..loader import load_data
from .eval_runner import load_scenarios, run_evals
from .shift_intelligence import ShiftIntelligenceAgent


@dataclass(slots=True)
class WorkflowRun:
    run_id: str
    scenario: str
    status: str
    started_at: str
    completed_at: str
    elapsed_seconds: float
    data: dict[str, Any]
    analysis: dict[str, Any]
    agent_report: dict[str, Any]
    evals: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "scenario": self.scenario,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "elapsed_seconds": self.elapsed_seconds,
            "data": self.data,
            "analysis": self.analysis,
            "agent_report": self.agent_report,
            "evals": self.evals,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


def run_shift_workflow(
    data_dir: str | Path,
    *,
    scenario: str = "General shift intelligence",
    kb: dict[str, Any] | None = None,
    evals_path: str | Path | None = None,
) -> WorkflowRun:
    """Load plant data, analyze it, run the agent, and optionally evaluate it."""
    started = datetime.now(timezone.utc)
    t0 = time.time()
    events, oee = load_data(data_dir)
    result = analyze(events, oee)
    return run_shift_workflow_from_result(
        result,
        scenario=scenario,
        kb=kb,
        evals_path=evals_path,
        started_at=started,
        elapsed_start=t0,
        data={"data_dir": str(data_dir), "event_count": len(events), "oee_interval_count": len(oee)},
    )


def run_shift_workflow_from_result(
    result: AnalysisResult,
    *,
    scenario: str = "General shift intelligence",
    kb: dict[str, Any] | None = None,
    evals_path: str | Path | None = None,
    started_at: datetime | None = None,
    elapsed_start: float | None = None,
    data: dict[str, Any] | None = None,
) -> WorkflowRun:
    """Run the agent workflow from an already-built AnalysisResult."""
    started = started_at or datetime.now(timezone.utc)
    t0 = elapsed_start if elapsed_start is not None else time.time()
    agent = ShiftIntelligenceAgent(kb=kb)
    report = agent.run(result, scenario).to_dict()
    eval_payload = None
    if evals_path:
        eval_payload = run_evals(result, load_scenarios(evals_path), kb=kb)

    completed = datetime.now(timezone.utc)
    return WorkflowRun(
        run_id=_run_id(started, result.line_id),
        scenario=scenario,
        status="success",
        started_at=started.isoformat(),
        completed_at=completed.isoformat(),
        elapsed_seconds=round(time.time() - t0, 3),
        data=data or {},
        analysis=_analysis_snapshot(result),
        agent_report=report,
        evals=eval_payload,
    )


def save_workflow_run(run: WorkflowRun, output: str | Path) -> Path:
    """Persist a workflow run JSON artifact."""
    path = Path(output)
    if path.suffix.lower() != ".json":
        path.mkdir(parents=True, exist_ok=True)
        path = path / f"{run.run_id}.json"
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(run.to_json())
    return path


def _analysis_snapshot(result: AnalysisResult) -> dict[str, Any]:
    return {
        "line_id": result.line_id,
        "date_range": [result.date_range[0].isoformat(), result.date_range[1].isoformat()],
        "total_events": result.total_events,
        "total_downtime_hours": round(result.total_downtime_hours, 2),
        "avg_oee": round(result.avg_oee, 4) if result.avg_oee is not None else None,
        "top_loss_driver": result.top_loss_driver,
        "signal_scores": {
            "machine": round(result.machine_signal_score, 3),
            "crew": round(result.crew_signal_score, 3),
            "oversight": round(result.oversight_signal_score, 3),
        },
        "top_equipment": [
            {
                "equipment": ep.equipment_raw_name,
                "events": ep.event_count,
                "downtime_hours": round(ep.total_downtime_hours, 2),
                "repeat_failure_rate": round(ep.repeat_failure_rate, 3),
                "mtbf_minutes": round(ep.mtbf_minutes, 1) if ep.mtbf_minutes is not None else None,
            }
            for ep in result.equipment_profiles[:5]
        ],
    }


def _run_id(started: datetime, line_id: str) -> str:
    safe_line = "".join(ch.lower() if ch.isalnum() else "-" for ch in line_id).strip("-") or "line"
    return f"shift-intel-{safe_line}-{started.strftime('%Y%m%d-%H%M%S')}"