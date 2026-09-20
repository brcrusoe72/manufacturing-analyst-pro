"""Conversational harness for the Shift Intelligence Agent tool layer.

This is intentionally small. The LLM or outer agent owns conversation and
judgment; this harness owns routing, required inputs, tool execution, and output
packaging.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from analyst.path_policy import resolve_optional_read_path, resolve_read_path, resolve_workspace_path
try:
    from .agent_wrapper import run_shift_intelligence_workflow
except ImportError:  # pragma: no cover - direct script execution fallback
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from agent_wrapper import run_shift_intelligence_workflow


@dataclass(slots=True)
class HarnessResponse:
    status: str
    message: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "payload": self.payload,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


class ManufacturingAgentHarness:
    """Route user requests into the manufacturing workflow tool."""

    def handle(self, request: dict[str, Any]) -> HarnessResponse:
        """Handle one agent request.

        Expected request keys:
        - message: natural-language request/scenario
        - data_file: local data file or directory
        - kb_file: optional equipment KB path
        - evals_file: optional eval JSON path
        - output: optional output directory/JSON path
        """
        message = str(request.get("message") or request.get("scenario") or "").strip()
        data_file = request.get("data_file")

        if not data_file:
            return HarnessResponse(
                status="needs_input",
                message="I need a local MES/OEE data file or folder before I can run the plant workflow.",
                payload={
                    "required": ["data_file"],
                    "optional": ["message", "kb_file", "evals_file", "output"],
                    "example": {
                        "message": "Repeated tray packer jams need passdown, escalation, and 7/30/90 verification.",
                        "data_file": "/path/to/line-1-data/",
                    },
                },
            )

        try:
            path = resolve_read_path(str(data_file), purpose="data_file", require_exists=True)
            kb_file = resolve_optional_read_path(request.get("kb_file"), purpose="kb_file", require_exists=True)
            evals_file = resolve_optional_read_path(request.get("evals_file"), purpose="evals_file", require_exists=True)
            output = request.get("output")
            output_path = resolve_workspace_path(output, purpose="output") if output else None
        except (FileNotFoundError, ValueError) as exc:
            return HarnessResponse(
                status="needs_input",
                message=str(exc),
                payload={"data_file": str(data_file)},
            )

        job = {
            "data_file": str(path),
            "scenario": message or "General shift intelligence",
            "kb_file": str(kb_file) if kb_file else None,
            "evals_file": str(evals_file) if evals_file else None,
            "output": str(output_path) if output_path else None,
        }
        result = run_shift_intelligence_workflow(job)
        if result.get("status") != "success":
            return HarnessResponse(
                status="error",
                message=f"Workflow failed: {result.get('error', 'unknown error')}",
                payload=result,
            )

        answer = result["answer"]
        decision = answer.get("decision", {})
        return HarnessResponse(
            status="success",
            message=(
                f"{decision.get('constraint')} is the current constraint; "
                f"risk is {decision.get('risk_level')} "
                f"({decision.get('risk_score')}/100)."
            ),
            payload=result,
        )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run the Manufacturing Agent harness")
    parser.add_argument("data_file", help="MES/OEE file or folder")
    parser.add_argument("--message", "-m", default="General shift intelligence")
    parser.add_argument("--kb-file", default=None)
    parser.add_argument("--evals-file", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    response = ManufacturingAgentHarness().handle({
        "message": args.message,
        "data_file": args.data_file,
        "kb_file": args.kb_file,
        "evals_file": args.evals_file,
        "output": args.output,
    })
    print(response.to_json())


if __name__ == "__main__":
    main()