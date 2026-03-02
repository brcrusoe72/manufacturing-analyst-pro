"""Analyst memory — reads prior findings, writes new ones after each report.

Memory structure:
  memory/findings/
    └── {line_id}_{date}.json    # one file per analysis run

Each finding captures:
  - What was analyzed (line, date range, question)
  - What was found (verdict, top issues, recommendations)
  - Key metrics at time of analysis (OEE, top equipment, shift spread)
  - What was recommended (so next run can check if it's working)

On the next run, the analyst loads prior findings for the same line
and injects them as context: "Last time we looked at this line on X,
we found Y and recommended Z."
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MEMORY_DIR = Path(__file__).resolve().parent.parent / "memory" / "findings"


@dataclass(slots=True)
class Finding:
    line_id: str
    analysis_date: str          # when the report was generated
    data_start: str             # data window start
    data_end: str               # data window end
    question: str
    verdict: str                # 1-2 sentence verdict
    avg_oee: float | None
    top_equipment: list[dict]   # [{name, events, hours, repeat_rate}] top 5
    shift_spread: dict          # {shift: oee}
    recommendation: str         # what we told them to do
    key_metrics: dict           # snapshot of important numbers


def save_finding(
    line_id: str,
    analysis_date: str,
    data_start: str,
    data_end: str,
    question: str,
    verdict: str,
    avg_oee: float | None,
    top_equipment: list[dict],
    shift_spread: dict,
    recommendation: str,
    key_metrics: dict | None = None,
) -> Path:
    """Save a finding after report generation."""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    finding = {
        "line_id": line_id,
        "analysis_date": analysis_date,
        "data_start": data_start,
        "data_end": data_end,
        "question": question,
        "verdict": verdict[:500],
        "avg_oee": avg_oee,
        "top_equipment": top_equipment[:5],
        "shift_spread": shift_spread,
        "recommendation": recommendation[:500],
        "key_metrics": key_metrics or {},
        "written_at": datetime.now(timezone.utc).isoformat(),
    }

    # Filename: line_date.json (overwrite if same line+date)
    safe_line = line_id.replace("/", "_").replace("\\", "_").replace(" ", "_")
    path = MEMORY_DIR / f"{safe_line}_{analysis_date}.json"
    path.write_text(json.dumps(finding, indent=2, ensure_ascii=False))
    return path


def load_prior_findings(line_id: str, limit: int = 5) -> list[dict]:
    """Load prior findings for a line, most recent first."""
    if not MEMORY_DIR.is_dir():
        return []

    safe_line = line_id.replace("/", "_").replace("\\", "_").replace(" ", "_")
    findings = []

    for path in sorted(MEMORY_DIR.glob(f"{safe_line}_*.json"), reverse=True):
        try:
            data = json.loads(path.read_text())
            findings.append(data)
        except (json.JSONDecodeError, OSError):
            continue
        if len(findings) >= limit:
            break

    return findings


def format_prior_findings_for_prompt(findings: list[dict]) -> str:
    """Format prior findings as context for the LLM prompt."""
    if not findings:
        return ""

    lines = ["", "=== PRIOR ANALYSIS HISTORY (what we found and recommended before) ==="]

    for f in findings:
        lines.append(
            f"\n--- Analysis from {f['analysis_date']} "
            f"(data: {f['data_start']} to {f['data_end']}) ---"
        )
        lines.append(f"  Question: {f['question']}")
        lines.append(f"  Verdict: {f['verdict']}")

        if f.get("avg_oee") is not None:
            lines.append(f"  OEE at that time: {f['avg_oee']:.1%}")

        if f.get("shift_spread"):
            spread_parts = [f"{s}: {v:.1%}" for s, v in f["shift_spread"].items() if v is not None]
            if spread_parts:
                lines.append(f"  Shift OEE: {', '.join(spread_parts)}")

        if f.get("top_equipment"):
            top_names = [f"{eq['name']} ({eq['events']} events, {eq['hours']:.0f}h)"
                         for eq in f["top_equipment"][:3]]
            lines.append(f"  Top losses: {'; '.join(top_names)}")

        lines.append(f"  RECOMMENDATION GIVEN: {f['recommendation']}")

        # Key metrics for comparison
        if f.get("key_metrics"):
            km = f["key_metrics"]
            if km.get("total_downtime_hours"):
                lines.append(f"  Total downtime: {km['total_downtime_hours']:.0f}h")
            if km.get("unassigned_hours"):
                lines.append(f"  Unassigned time: {km['unassigned_hours']:.0f}h")

    lines.append("")
    lines.append("INSTRUCTION: If prior findings exist, compare current state to prior state. "
                 "Has OEE improved or worsened? Are the same equipment still the top losses? "
                 "Was the prior recommendation acted on (based on whether the pattern changed)? "
                 "Be specific: 'Last analysis on [date] recommended [X]. "
                 "Since then, [metric] has [improved/worsened/stayed flat].'")

    return "\n".join(lines)
