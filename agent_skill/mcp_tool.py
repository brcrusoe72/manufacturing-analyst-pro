"""MCP tool server — exposes manufacturing analysis as MCP tools.

Run with: python mcp_tool.py
Serves over stdio (standard MCP transport).
"""
from __future__ import annotations

import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any

try:
    from .agent_wrapper import run_analysis, run_shift_intelligence_workflow
except ImportError:  # pragma: no cover - direct script execution fallback
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from agent_wrapper import run_analysis, run_shift_intelligence_workflow
from analyst.agentic_harness import ManufacturingAgenticHarness
from analyst.security import external_error, require_args


# ---------- MCP Protocol Implementation (stdio) ----------

def _mcp_response(id: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": id, "result": result}


def _mcp_error(id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


AUTH_TOKEN_PROPERTY = {
    "type": "string",
    "description": "Required only when MFG_AGENT_AUTH_TOKEN is configured on the MCP server.",
}


TOOLS = [
    {
        "name": "analyze_production_data",
        "description": "Analyze MES/SCADA production data for OEE losses, equipment reliability, shift performance, and trends. Returns structured analysis with equipment profiles, shift comparisons, and an executive narrative.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "data_file": {
                    "type": "string",
                    "description": "Path to CSV/XLSX file or directory containing production data files"
                },
                "question": {
                    "type": "string",
                    "description": "Specific question to answer about the data (default: top loss driver)"
                },
                "generate_narrative": {
                    "type": "boolean",
                    "description": "Whether to generate an LLM narrative report (default: true, costs ~$0.005)",
                    "default": True,
                },
                "auth_token": AUTH_TOKEN_PROPERTY,
            },
            "required": ["data_file"],
        },
    },
    {
        "name": "generate_shift_report",
        "description": "Generate a shift-specific analysis report from production data. Compares shift OEE, downtime patterns, startup penalties, and equipment behavior across shifts.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "data_file": {
                    "type": "string",
                    "description": "Path to CSV/XLSX file or directory"
                },
                "shift": {
                    "type": "string",
                    "enum": ["1st", "2nd", "3rd"],
                    "description": "Specific shift to focus on (optional — all shifts if omitted)"
                },
                "auth_token": AUTH_TOKEN_PROPERTY,
            },
            "required": ["data_file"],
        },
    },
    {
        "name": "equipment_health_check",
        "description": "Profile equipment reliability from downtime data. Returns MTBF, repeat failure rates, event counts, and shift-by-shift breakdown for each piece of equipment.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "data_file": {
                    "type": "string",
                    "description": "Path to CSV/XLSX file or directory"
                },
                "auth_token": AUTH_TOKEN_PROPERTY,
            },
            "required": ["data_file"],
        },
    },
    {
        "name": "run_shift_intelligence_workflow",
        "description": "Run the full tool-using Shift Intelligence Agent workflow: load data, analyze OEE/downtime, classify intent, find constraint, search prior RCA/passdown memory, score risk, apply approval gates, create supervisor actions, draft passdown, build recurrence watchlist, schedule 7/30/90-day verification, and return a tool trace plus optional eval results.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "data_file": {
                    "type": "string",
                    "description": "Path to CSV/XLSX file or directory containing production data files"
                },
                "scenario": {
                    "type": "string",
                    "description": "Supervisor question or operational scenario for the agent to handle"
                },
                "kb_file": {
                    "type": "string",
                    "description": "Optional path to equipment_kb.json; defaults to the built-in memory/equipment_kb.json"
                },
                "evals_file": {
                    "type": "string",
                    "description": "Optional path to eval scenario JSON"
                },
                "output": {
                    "type": "string",
                    "description": "Optional output directory or JSON path for the workflow artifact"
                },
                "auth_token": AUTH_TOKEN_PROPERTY,
            },
            "required": ["data_file"],
        },
    },
    {
        "name": "run_manufacturing_agent_harness",
        "description": "Run the markdown-driven Manufacturing Management Agent harness. This is the OpenClaw/Codex-facing tool: it loads AGENT.md/TOOLS.md/role behavior files, optionally uses an LLM planner, stages plant data into a workspace, chooses manufacturing tools, writes run traces and markdown artifacts, and returns the harness result.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Natural-language request for the manufacturing agent"
                },
                "data_file": {
                    "type": "string",
                    "description": "Optional local CSV/XLSX file or directory containing plant data. Must be under MFG_AGENT_DATA_ROOTS or legacy MFG_AGENT_ALLOWED_ROOTS."
                },
                "line": {
                    "type": "string",
                    "description": "Optional line name/id filter, e.g. 'Line 1'"
                },
                "photo_name": {
                    "type": "string",
                    "description": "Optional photo/screenshot artifact name for context tracking"
                },
                "workspace": {
                    "type": "string",
                    "description": "Harness workspace directory where inbox, runs, artifacts, and MEMORY.md are written. Must be under MFG_AGENT_WORKSPACE_ROOTS.",
                    "default": "agent-workspace"
                },
                "behavior_dir": {
                    "type": "string",
                    "description": "Optional override path for AGENT.md/TOOLS.md/roles behavior files. Must be under MFG_AGENT_BEHAVIOR_ROOTS."
                },
                "use_llm": {
                    "type": "boolean",
                    "description": "Whether to use the LLM planner when MFG_AGENT_ALLOW_LLM_PLANNER=1 and OPENAI_API_KEY are configured. Defaults true, but deterministic fallback always exists.",
                    "default": True
                },
                "model": {
                    "type": "string",
                    "description": "Planner model to use when use_llm=true, MFG_AGENT_ALLOW_LLM_PLANNER=1, and OPENAI_API_KEY is available",
                    "default": "gpt-5-mini"
                },
                "auth_token": AUTH_TOKEN_PROPERTY,
            },
            "required": ["message"],
        },
    },
]


def handle_request(request: dict) -> dict:
    """Handle a single MCP JSON-RPC request."""
    method = request.get("method", "")
    id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return _mcp_response(id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {
                "name": "manufacturing-analyst",
                "version": "1.0.0",
            },
        })

    if method == "notifications/initialized":
        return None  # No response needed for notifications

    if method == "tools/list":
        return _mcp_response(id, {"tools": TOOLS})

    if method == "tools/call":
        if not isinstance(params, dict):
            return _mcp_error(id, -32602, "Invalid params")
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            return _mcp_error(id, -32602, "Invalid arguments")
        return _handle_tool_call(id, tool_name, arguments)

    return _mcp_error(id, -32601, f"Unknown method: {method}")


def _handle_tool_call(id: Any, tool_name: str, args: dict) -> dict:
    """Dispatch tool calls to the analysis engine."""
    try:
        auth_error = _auth_error(id, args)
        if auth_error:
            return auth_error

        if tool_name == "analyze_production_data":
            require_args(args, "data_file")
            job = {
                "data_file": args["data_file"],
                "analysis_type": "full",
                "question": args.get("question"),
                "generate_narrative": args.get("generate_narrative", True),
            }

        elif tool_name == "generate_shift_report":
            require_args(args, "data_file")
            job = {
                "data_file": args["data_file"],
                "analysis_type": "shift-report",
                "shift": args.get("shift"),
                "generate_narrative": True,
            }

        elif tool_name == "equipment_health_check":
            require_args(args, "data_file")
            job = {
                "data_file": args["data_file"],
                "analysis_type": "equipment-health",
                "generate_narrative": False,
            }

        elif tool_name == "run_shift_intelligence_workflow":
            require_args(args, "data_file")
            job = {
                "data_file": args["data_file"],
                "scenario": args.get("scenario"),
                "kb_file": args.get("kb_file"),
                "evals_file": args.get("evals_file"),
                "output": args.get("output"),
            }
            result = run_shift_intelligence_workflow(job)
            if result["status"] == "success":
                return _mcp_response(id, {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}],
                    "isError": False,
                })
            return _mcp_response(id, {
                "content": [{"type": "text", "text": _result_error_text(result, "workflow_failed")}],
                "isError": True,
            })

        elif tool_name == "run_manufacturing_agent_harness":
            require_args(args, "message")
            harness = ManufacturingAgenticHarness(
                workspace=args.get("workspace") or "agent-workspace",
                behavior_dir=args.get("behavior_dir"),
                use_llm=args.get("use_llm", True),
                model=args.get("model") or "gpt-5-mini",
            )
            run = harness.run(
                args["message"],
                data_path=args.get("data_file"),
                line=args.get("line"),
                photo_name=args.get("photo_name"),
            )
            return _mcp_response(id, {
                "content": [{"type": "text", "text": json.dumps(run.to_dict(), indent=2, default=str)}],
                "isError": False,
            })

        else:
            return _mcp_error(id, -32602, f"Unknown tool: {tool_name}")

        result = run_analysis(job)

        # Format output
        if result["status"] == "success":
            text = json.dumps(result, indent=2, default=str)
            return _mcp_response(id, {
                "content": [{"type": "text", "text": text}],
                "isError": False,
            })
        else:
            return _mcp_response(id, {
                "content": [{"type": "text", "text": _result_error_text(result, "analysis_failed")}],
                "isError": True,
            })

    except Exception as exc:
        err = external_error(exc)
        return _mcp_response(id, {
            "content": [{"type": "text", "text": err.to_text()}],
            "isError": True,
        })


def _auth_error(id: Any, args: dict) -> dict | None:
    expected = os.environ.get("MFG_AGENT_AUTH_TOKEN")
    if not expected:
        return None
    supplied = args.get("auth_token")
    if isinstance(supplied, str) and secrets.compare_digest(supplied, expected):
        return None
    return _mcp_response(id, {
        "content": [{"type": "text", "text": "Authentication failed: invalid or missing auth_token"}],
        "isError": True,
    })


def _result_error_text(result: dict[str, Any], fallback_code: str) -> str:
    code = result.get("error_code") or fallback_code
    message = result.get("error") or "Request failed."
    return f"Error [{code}]: {message}"


def main():
    """MCP stdio transport — read JSON-RPC from stdin, write to stdout."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
            if response is not None:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError:
            err = _mcp_error(None, -32700, "Parse error")
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()