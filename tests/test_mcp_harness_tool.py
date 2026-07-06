from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

class MCPHarnessToolTest(unittest.TestCase):
    def _import_mcp_tool(self):
        import sys

        sys.path.insert(0, str(Path("agent-skill").resolve()))
        import mcp_tool  # type: ignore

        return mcp_tool

    def test_mcp_lists_harness_tool(self) -> None:
        mcp_tool = self._import_mcp_tool()

        response = mcp_tool.handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = {tool["name"] for tool in response["result"]["tools"]}
        self.assertIn("run_manufacturing_agent_harness", names)

    def test_mcp_runs_harness_tool(self) -> None:
        mcp_tool = self._import_mcp_tool()

        sample = str(Path("samples/line_review_short_stops.csv").resolve())
        with tempfile.TemporaryDirectory() as tmp:
            response = mcp_tool.handle_request({
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "run_manufacturing_agent_harness",
                    "arguments": {
                        "message": "Review 10 months of Line 1 data. Short Stops and Unassigned are high.",
                        "data_file": sample,
                        "line": "Line 1",
                        "workspace": tmp,
                        "use_llm": False,
                    },
                },
            })

            self.assertFalse(response["result"]["isError"])
            text = response["result"]["content"][0]["text"]
            payload = json.loads(text)
            self.assertIn("AGENT.md", payload["behavior_files"])
            self.assertTrue(any(call["name"] == "run_line_review" for call in payload["tool_calls"]))
            self.assertTrue(payload["artifacts"])

    def test_mcp_rejects_arbitrary_local_file(self) -> None:
        mcp_tool = self._import_mcp_tool()

        with tempfile.TemporaryDirectory() as tmp:
            response = mcp_tool.handle_request({
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "run_manufacturing_agent_harness",
                    "arguments": {
                        "message": "Try to read an arbitrary host file.",
                        "data_file": "/etc/hosts",
                        "workspace": tmp,
                        "use_llm": False,
                    },
                },
            })

            self.assertTrue(response["result"]["isError"])
            self.assertIn("path_outside_allowed_roots", response["result"]["content"][0]["text"])
            self.assertFalse((Path(tmp) / "inbox" / "hosts").exists())

    def test_mcp_auth_token_is_required_when_configured(self) -> None:
        mcp_tool = self._import_mcp_tool()

        old = os.environ.get("MFG_AGENT_AUTH_TOKEN")
        os.environ["MFG_AGENT_AUTH_TOKEN"] = "secret"
        try:
            denied = mcp_tool.handle_request({
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "equipment_health_check",
                    "arguments": {"data_file": "samples/line_review_short_stops.csv"},
                },
            })
            self.assertTrue(denied["result"]["isError"])
            self.assertIn("Authentication failed", denied["result"]["content"][0]["text"])

            allowed = mcp_tool.handle_request({
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "run_manufacturing_agent_harness",
                    "arguments": {
                        "auth_token": "secret",
                        "message": "Review 10 months of Line 1 data.",
                        "data_file": "samples/line_review_short_stops.csv",
                        "workspace": tempfile.mkdtemp(),
                        "use_llm": False,
                    },
                },
            })
            self.assertFalse(allowed["result"]["isError"])
        finally:
            if old is None:
                os.environ.pop("MFG_AGENT_AUTH_TOKEN", None)
            else:
                os.environ["MFG_AGENT_AUTH_TOKEN"] = old

    def test_legacy_mcp_tools_reject_arbitrary_local_file(self) -> None:
        mcp_tool = self._import_mcp_tool()

        old = os.environ.get("MFG_AGENT_ALLOWED_ROOTS")
        os.environ["MFG_AGENT_ALLOWED_ROOTS"] = "/nonexistent"
        try:
            for idx, tool_name in enumerate([
                "analyze_production_data",
                "generate_shift_report",
                "equipment_health_check",
                "run_shift_intelligence_workflow",
            ], start=10):
                response = mcp_tool.handle_request({
                    "jsonrpc": "2.0",
                    "id": idx,
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": {"data_file": "/etc/hosts"},
                    },
                })

                self.assertTrue(response["result"]["isError"], tool_name)
                self.assertIn("path_outside_allowed_roots", response["result"]["content"][0]["text"])
        finally:
            self._restore_env("MFG_AGENT_ALLOWED_ROOTS", old)

    def test_legacy_workflow_rejects_kb_evals_and_output_outside_policy(self) -> None:
        mcp_tool = self._import_mcp_tool()
        sample = str(Path("samples/line_review_short_stops.csv").resolve())
        old_read = os.environ.get("MFG_AGENT_ALLOWED_ROOTS")
        old_workspace = os.environ.get("MFG_AGENT_WORKSPACE_ROOTS")

        try:
            for idx, extra in enumerate([
                {"kb_file": "/etc/hosts"},
                {"evals_file": "/etc/hosts"},
            ], start=20):
                os.environ["MFG_AGENT_ALLOWED_ROOTS"] = os.pathsep.join([str(Path(sample).parent), "/nonexistent"])
                response = mcp_tool.handle_request({
                    "jsonrpc": "2.0",
                    "id": idx,
                    "method": "tools/call",
                    "params": {
                        "name": "run_shift_intelligence_workflow",
                        "arguments": {"data_file": sample, **extra},
                    },
                })

                self.assertTrue(response["result"]["isError"], extra)
                self.assertIn("path_outside_allowed_roots", response["result"]["content"][0]["text"])

            with tempfile.TemporaryDirectory() as tmp:
                os.environ["MFG_AGENT_ALLOWED_ROOTS"] = str(Path(sample).parent)
                os.environ["MFG_AGENT_WORKSPACE_ROOTS"] = "/nonexistent"
                response = mcp_tool.handle_request({
                    "jsonrpc": "2.0",
                    "id": 30,
                    "method": "tools/call",
                    "params": {
                        "name": "run_shift_intelligence_workflow",
                        "arguments": {
                            "data_file": sample,
                            "scenario": "passdown and verification",
                            "output": tmp,
                        },
                    },
                })

                self.assertTrue(response["result"]["isError"])
                self.assertIn("path_outside_workspace_roots", response["result"]["content"][0]["text"])
                self.assertFalse(any(Path(tmp).iterdir()))
        finally:
            self._restore_env("MFG_AGENT_ALLOWED_ROOTS", old_read)
            self._restore_env("MFG_AGENT_WORKSPACE_ROOTS", old_workspace)

    def test_missing_required_args_are_sanitized(self) -> None:
        mcp_tool = self._import_mcp_tool()

        response = mcp_tool.handle_request({
            "jsonrpc": "2.0",
            "id": 40,
            "method": "tools/call",
            "params": {"name": "analyze_production_data", "arguments": {}},
        })

        text = response["result"]["content"][0]["text"]
        self.assertTrue(response["result"]["isError"])
        self.assertIn("missing_required_argument", text)
        self.assertNotIn("'data_file'", text)

    @staticmethod
    def _restore_env(name: str, value: str | None) -> None:
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


if __name__ == "__main__":
    unittest.main()