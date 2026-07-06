"""Agent wrapper — makes the manufacturing analyst engine callable as an agent task.

Accepts jobs in Agent Café format, runs analysis, returns structured results + narrative.
"""
from __future__ import annotations

import base64
import ipaddress
import json
import os
import shutil
import socket
import sys
import tempfile
import urllib.parse
import urllib.request
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

# Add parent to path so we can import the analyst package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analyst.engine import analyze, AnalysisResult
from analyst.loader import SUPPORTED_SUFFIXES, load_data
from analyst.narrative import generate_narrative, Narrative
from analyst.parsers import parse_event_file, parse_oee_file
from analyst.agents.workflow import run_shift_workflow, save_workflow_run
from analyst.path_policy import resolve_read_path, resolve_workspace_path, safe_filename
from analyst.security import external_error_payload


MAX_INPUT_BYTES_ENV = "MFG_AGENT_MAX_INPUT_BYTES"
DEFAULT_MAX_INPUT_BYTES = 25 * 1024 * 1024
DOWNLOAD_TIMEOUT_SECONDS = 15


def _serialize_result(result: AnalysisResult) -> dict[str, Any]:
    """Convert AnalysisResult to JSON-safe dict."""
    d = {
        "line_id": result.line_id,
        "date_range": [result.date_range[0].isoformat(), result.date_range[1].isoformat()],
        "total_events": result.total_events,
        "total_downtime_hours": round(result.total_downtime_hours, 2),
        "avg_oee": round(result.avg_oee, 4) if result.avg_oee else None,
        "top_loss_driver": result.top_loss_driver,
        "machine_signal_score": result.machine_signal_score,
        "crew_signal_score": result.crew_signal_score,
        "oversight_signal_score": result.oversight_signal_score,
        "equipment_profiles": [
            {
                "equipment_id": ep.equipment_id,
                "equipment_raw_name": ep.equipment_raw_name,
                "event_count": ep.event_count,
                "total_downtime_hours": round(ep.total_downtime_hours, 2),
                "avg_duration_minutes": round(ep.avg_duration_minutes, 1),
                "mtbf_minutes": round(ep.mtbf_minutes, 1) if ep.mtbf_minutes else None,
                "repeat_failure_rate": round(ep.repeat_failure_rate, 3),
                "by_shift": {s: {"count": d["count"], "hours": round(d["hours"], 2)} for s, d in ep.by_shift.items()},
            }
            for ep in result.equipment_profiles[:15]
        ],
        "shift_profiles": [
            {
                "shift": sp.shift,
                "avg_oee": round(sp.avg_oee, 4) if sp.avg_oee else None,
                "event_count": sp.event_count,
                "total_downtime_hours": round(sp.total_downtime_hours, 2),
                "unassigned_rate": round(sp.unassigned_rate, 3),
                "startup_penalty_points": round(sp.startup_penalty_points, 4) if sp.startup_penalty_points else None,
                "avg_recovery_minutes": round(sp.avg_recovery_minutes, 1),
                "notable_patterns": sp.notable_patterns[:5],
            }
            for sp in result.shift_profiles
        ],
        "trends": [
            {
                "metric_name": t.metric_name,
                "monthly_values": t.monthly_values,
                "direction": t.direction,
                "magnitude": round(t.magnitude, 3),
            }
            for t in result.trends
        ],
    }
    return d


def _serialize_narrative(narrative: Narrative) -> dict[str, Any]:
    """Convert Narrative to JSON-safe dict."""
    return {
        "verdict": narrative.verdict,
        "evidence_paragraphs": narrative.evidence_paragraphs,
        "recommendation": narrative.recommendation,
        "caveat": narrative.caveat,
        "full_text": "\n\n".join([narrative.verdict] + narrative.evidence_paragraphs),
    }


def _safe_filename(name: str) -> str:
    return safe_filename(name, default="data.xlsx")


def _validate_download_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("data_url must use http or https")
    if not parsed.hostname:
        raise ValueError("data_url must include a hostname")
    host = parsed.hostname.lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("data_url cannot target localhost")
    for info in socket.getaddrinfo(host, None):
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast:
            raise ValueError("data_url cannot target private or local network addresses")
    return url


class _ValidatingRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        _validate_download_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _max_input_bytes() -> int:
    raw = os.environ.get(MAX_INPUT_BYTES_ENV)
    if not raw:
        return DEFAULT_MAX_INPUT_BYTES
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{MAX_INPUT_BYTES_ENV} must be an integer byte limit") from exc


def _validate_data_filename(filename: str) -> str:
    safe = _safe_filename(filename)
    suffix = Path(safe).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported data file extension: {suffix or '(none)'}")
    return safe


def _write_bounded_bytes(data: bytes, destination: Path) -> None:
    max_bytes = _max_input_bytes()
    if len(data) > max_bytes:
        raise ValueError(f"Input file too large: {len(data)} bytes exceeds {max_bytes}")
    destination.write_bytes(data)


def _download_url_to_file(url: str, destination: Path) -> None:
    max_bytes = _max_input_bytes()
    opener = urllib.request.build_opener(_ValidatingRedirectHandler)
    request = urllib.request.Request(url, headers={"User-Agent": "manufacturing-management-agent/0.1"})
    total = 0
    try:
        with opener.open(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
            final_url = response.geturl()
            _validate_download_url(final_url)
            content_type = response.headers.get_content_type()
            if content_type in {"text/html", "application/json"}:
                raise ValueError(f"Unsupported data_url content type: {content_type}")
            length_header = response.headers.get("Content-Length")
            if length_header:
                try:
                    if int(length_header) > max_bytes:
                        raise ValueError(f"Input file too large: {length_header} bytes exceeds {max_bytes}")
                except ValueError as exc:
                    if "exceeds" in str(exc):
                        raise
                    raise ValueError("Invalid Content-Length from data_url") from exc
            with destination.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError(f"Input file too large: exceeds {max_bytes} bytes")
                    handle.write(chunk)
    except Exception:
        try:
            destination.unlink()
        except FileNotFoundError:
            pass
        raise


def _resolve_data(job: dict) -> Path:
    """Resolve data from job payload to a local temp directory with files.
    
    Supports:
    - data_file: local path to file or directory
    - data_url: URL to download
    - data_base64: base64-encoded file content (with filename)
    """
    if "data_file" in job:
        p = resolve_read_path(job["data_file"], purpose="data_file", require_exists=True)
        if p.is_dir():
            return p
        if p.is_file():
            # Create temp dir with the file
            tmp = Path(tempfile.mkdtemp(prefix="mfg_analyst_"))
            shutil.copy2(p, tmp / _validate_data_filename(p.name))
            return tmp

    if "data_base64" in job:
        tmp = Path(tempfile.mkdtemp(prefix="mfg_analyst_"))
        try:
            filename = _validate_data_filename(job.get("filename", "data.xlsx"))
            data = base64.b64decode(job["data_base64"], validate=True)
            _write_bounded_bytes(data, tmp / filename)
            return tmp
        except Exception:
            shutil.rmtree(tmp, ignore_errors=True)
            raise

    if "data_url" in job:
        tmp = Path(tempfile.mkdtemp(prefix="mfg_analyst_"))
        try:
            url = _validate_download_url(job["data_url"])
            parsed = urllib.parse.urlparse(url)
            filename = _validate_data_filename(job.get("filename", Path(parsed.path).name or "data.xlsx"))
            _download_url_to_file(url, tmp / filename)
            return tmp
        except Exception:
            shutil.rmtree(tmp, ignore_errors=True)
            raise

    raise ValueError("Job must include data_file, data_url, or data_base64")


def run_analysis(job: dict) -> dict[str, Any]:
    """Run manufacturing analysis from an Agent Café job payload.
    
    Args:
        job: Dict with keys:
            - data_file: path to file/directory
            - data_url: URL to fetch data from
            - data_base64: base64-encoded file + filename
            - analysis_type: "full" | "shift-report" | "equipment-health" (default: full)
            - question: specific question (optional)
            - shift: shift filter for shift-report (optional)
            - generate_narrative: bool (default: True)
    
    Returns:
        Dict with analysis results, narrative, and metadata.
    """
    try:
        data_dir = _resolve_data(job)
        events, oee = load_data(str(data_dir))
        result = analyze(events, oee)

        response: dict[str, Any] = {
            "status": "success",
            "analysis": _serialize_result(result),
            "metadata": {
                "line_id": result.line_id,
                "date_range": [result.date_range[0].isoformat(), result.date_range[1].isoformat()],
                "total_events": result.total_events,
                "total_downtime_hours": round(result.total_downtime_hours, 2),
                "avg_oee": round(result.avg_oee, 4) if result.avg_oee else None,
            },
        }

        # Filter by analysis type
        analysis_type = job.get("analysis_type", "full")
        if analysis_type == "shift-report":
            shift = job.get("shift")
            if shift:
                response["analysis"]["shift_profiles"] = [
                    sp for sp in response["analysis"]["shift_profiles"] if sp["shift"] == shift
                ]

        elif analysis_type == "equipment-health":
            # Focus on equipment profiles only
            response["analysis"] = {
                "equipment_profiles": response["analysis"]["equipment_profiles"],
                "top_loss_driver": response["analysis"]["top_loss_driver"],
            }

        # Generate narrative if requested
        if job.get("generate_narrative", True):
            question = job.get("question")
            narrative = generate_narrative(result, question=question)
            response["narrative"] = _serialize_narrative(narrative)

        return response

    except Exception as exc:
        return external_error_payload(exc)


def _load_kb(path: str | None = None) -> dict[str, Any] | None:
    """Load equipment/passdown KB for the agent workflow."""
    candidates = []
    if path:
        candidates.append(resolve_read_path(path, purpose="kb_file", require_exists=True))
    candidates.append(Path(__file__).resolve().parent.parent / "memory" / "equipment_kb.json")
    for candidate in candidates:
        if candidate.is_file():
            return json.loads(candidate.read_text())
    return None


def run_shift_intelligence_workflow(job: dict) -> dict[str, Any]:
    """Run the full tool-using Shift Intelligence Agent workflow.

    This is the harness-facing entry point. It accepts the same data payload
    shapes as ``run_analysis`` and returns a complete workflow artifact:
    deterministic analysis, tool trace, final answer, watchlist, verification
    follow-ups, and optional eval results.
    """
    try:
        data_dir = _resolve_data(job)
        kb = _load_kb(job.get("kb_file"))
        evals_path = job.get("evals_file")
        if evals_path:
            evals_path = str(resolve_read_path(evals_path, purpose="evals_file", require_exists=True))
        output = job.get("output")
        safe_output = resolve_workspace_path(output, purpose="output") if output else None
        run = run_shift_workflow(
            data_dir,
            scenario=job.get("scenario") or job.get("question") or "General shift intelligence",
            kb=kb,
            evals_path=evals_path,
        )

        output_path = None
        if safe_output:
            output_path = str(save_workflow_run(run, safe_output))

        payload = run.to_dict()
        payload["output_path"] = output_path
        return {
            "status": "success",
            "workflow": payload,
            "answer": payload["agent_report"]["final_answer"],
        }
    except Exception as exc:
        return external_error_payload(exc)


def main() -> None:
    """CLI entry point for local wrapper testing."""
    if len(sys.argv) < 2:
        print("Usage: python agent_wrapper.py <path_to_data_dir_or_file> [question]")
        sys.exit(1)

    job = {"data_file": sys.argv[1]}
    if len(sys.argv) > 2:
        job["question"] = sys.argv[2]

    result = run_analysis(job)
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()