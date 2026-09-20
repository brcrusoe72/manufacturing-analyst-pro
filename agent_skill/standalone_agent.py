"""Standalone Manufacturing Intelligence Agent.

This is a focused agentic highlighter: it watches plant-data inputs, runs the
Shift Intelligence workflow, persists state, and writes alerts when something
deserves human attention.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from analyst.path_policy import resolve_optional_read_path, resolve_read_path, resolve_workspace_path, safe_filename
try:
    from .harness import ManufacturingAgentHarness
except ImportError:  # pragma: no cover - direct script execution fallback
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from harness import ManufacturingAgentHarness


DATA_EXTENSIONS = {".xlsx", ".xlsm", ".xls", ".csv"}


@dataclass(slots=True)
class Highlight:
    priority: str
    title: str
    summary: str
    reasons: list[str]
    workflow_path: str | None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "priority": self.priority,
            "title": self.title,
            "summary": self.summary,
            "reasons": self.reasons,
            "workflow_path": self.workflow_path,
            "created_at": self.created_at,
        }


class ManufacturingStandaloneAgent:
    """A small persistent agent for plant-data highlighting."""

    def __init__(
        self,
        *,
        inbox: str | Path,
        state_dir: str | Path,
        scenario: str | None = None,
        kb_file: str | Path | None = None,
        evals_file: str | Path | None = None,
    ) -> None:
        self.inbox = resolve_read_path(inbox, purpose="inbox")
        self.state_dir = resolve_workspace_path(state_dir, purpose="state_dir")
        self.runs_dir = self.state_dir / "runs"
        self.alerts_dir = self.state_dir / "alerts"
        self.state_file = self.state_dir / "state.json"
        self.scenario = scenario or (
            "Highlight important production risks, create supervisor passdown, "
            "escalation guidance, recurrence watchlist, and 7/30/90 verification."
        )
        resolved_kb = resolve_optional_read_path(kb_file, purpose="kb_file", require_exists=True)
        resolved_evals = resolve_optional_read_path(evals_file, purpose="evals_file", require_exists=True)
        self.kb_file = str(resolved_kb) if resolved_kb else None
        self.evals_file = str(resolved_evals) if resolved_evals else None
        self.harness = ManufacturingAgentHarness()

    def run_once(self) -> dict[str, Any]:
        """Process new datasets once and return an agent-cycle summary."""
        self._ensure_dirs()
        state = self._load_state()
        processed = state.setdefault("processed", {})
        cycle = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "inbox": str(self.inbox),
            "processed": [],
            "skipped": [],
            "highlights": [],
        }

        for dataset in self._discover_datasets():
            fingerprint = _fingerprint(dataset)
            key = str(dataset)
            if processed.get(key) == fingerprint:
                cycle["skipped"].append({"path": key, "reason": "unchanged"})
                continue

            response = self.harness.handle({
                "message": self.scenario,
                "data_file": str(dataset),
                "kb_file": self.kb_file,
                "evals_file": self.evals_file,
                "output": str(self.runs_dir),
            })
            payload = response.to_dict()
            if response.status != "success":
                cycle["processed"].append({"path": key, "status": response.status, "message": response.message})
                continue

            highlight = self._make_highlight(payload)
            alert_path = None
            if highlight.priority in {"high", "medium"}:
                alert_path = self._save_alert(highlight)

            processed[key] = fingerprint
            cycle["processed"].append({
                "path": key,
                "status": "success",
                "message": response.message,
                "alert_path": str(alert_path) if alert_path else None,
            })
            cycle["highlights"].append(highlight.to_dict())

        state["last_run_at"] = datetime.now(timezone.utc).isoformat()
        self._save_state(state)
        return cycle

    def watch(self, *, interval_seconds: int = 300, max_cycles: int | None = None) -> None:
        """Run continuously, polling the inbox."""
        cycles = 0
        while True:
            print(json.dumps(self.run_once(), indent=2, default=str))
            cycles += 1
            if max_cycles is not None and cycles >= max_cycles:
                return
            time.sleep(interval_seconds)

    def _discover_datasets(self) -> list[Path]:
        if not self.inbox.exists():
            return []
        if self.inbox.is_file():
            return [self.inbox] if self.inbox.suffix.lower() in DATA_EXTENSIONS else []

        datasets: list[Path] = []
        if any(path.suffix.lower() in DATA_EXTENSIONS for path in self.inbox.iterdir() if path.is_file()):
            datasets.append(self.inbox)
        for child in sorted(self.inbox.iterdir()):
            if child.is_dir() and any(path.suffix.lower() in DATA_EXTENSIONS for path in child.iterdir() if path.is_file()):
                datasets.append(child)
            elif child.is_file() and child.suffix.lower() in DATA_EXTENSIONS:
                datasets.append(child)
        return datasets

    def _make_highlight(self, response: dict[str, Any]) -> Highlight:
        workflow = response["payload"]["workflow"]
        answer = response["payload"]["answer"]
        decision = answer.get("decision", {})
        risk_level = decision.get("risk_level", "low")
        risk_score = int(decision.get("risk_score") or 0)
        constraint = decision.get("constraint") or "unknown constraint"
        evals = workflow.get("evals") or {}
        output_path = workflow.get("output_path")

        reasons = list(answer.get("evidence", [])[:4])
        if decision.get("approval_required"):
            reasons.append(f"Human approval required from: {', '.join(decision.get('approvers', []))}")
        if evals:
            reasons.append(f"Agent evals: {evals.get('passed')}/{evals.get('total')} passed, avg score {evals.get('avg_score')}")

        priority = "high" if risk_score >= 70 else "medium" if risk_score >= 40 else "low"
        return Highlight(
            priority=priority,
            title=f"{constraint}: {risk_level} risk ({risk_score}/100)",
            summary=response["message"],
            reasons=reasons,
            workflow_path=output_path,
        )

    def _save_alert(self, highlight: Highlight) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        safe_title = safe_filename("".join(ch.lower() if ch.isalnum() else "-" for ch in highlight.title)[:80], default="alert")
        path = self.alerts_dir / f"{stamp}-{safe_title}.json"
        path.write_text(json.dumps(highlight.to_dict(), indent=2, default=str))
        return path

    def _ensure_dirs(self) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.alerts_dir.mkdir(parents=True, exist_ok=True)

    def _load_state(self) -> dict[str, Any]:
        if self.state_file.is_file():
            return json.loads(self.state_file.read_text())
        return {"processed": {}, "created_at": datetime.now(timezone.utc).isoformat()}

    def _save_state(self, state: dict[str, Any]) -> None:
        self.state_file.write_text(json.dumps(state, indent=2, default=str))


def _fingerprint(path: Path) -> str:
    h = hashlib.sha256()
    if path.is_file():
        _hash_file(h, path)
    else:
        for item in sorted(path.rglob("*")):
            if item.is_file() and item.suffix.lower() in DATA_EXTENSIONS:
                h.update(str(item.relative_to(path)).encode())
                _hash_file(h, item)
    return h.hexdigest()


def _hash_file(h: Any, path: Path) -> None:
    stat = path.stat()
    h.update(path.name.encode())
    h.update(str(stat.st_size).encode())
    h.update(str(int(stat.st_mtime)).encode())


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Standalone Manufacturing Intelligence Agent")
    parser.add_argument("inbox", help="File, folder, or inbox folder to scan")
    parser.add_argument("--state-dir", default="agent-state", help="State/output directory")
    parser.add_argument("--scenario", default=None, help="Default agent mission/scenario")
    parser.add_argument("--kb-file", default=None)
    parser.add_argument("--evals-file", default=None)
    parser.add_argument("--watch", action="store_true", help="Keep polling the inbox")
    parser.add_argument("--interval", type=int, default=300, help="Watch polling interval in seconds")
    parser.add_argument("--max-cycles", type=int, default=None, help="Stop after N cycles")
    args = parser.parse_args()

    agent = ManufacturingStandaloneAgent(
        inbox=args.inbox,
        state_dir=args.state_dir,
        scenario=args.scenario,
        kb_file=args.kb_file,
        evals_file=args.evals_file,
    )
    if args.watch:
        agent.watch(interval_seconds=args.interval, max_cycles=args.max_cycles)
    else:
        print(json.dumps(agent.run_once(), indent=2, default=str))


if __name__ == "__main__":
    main()