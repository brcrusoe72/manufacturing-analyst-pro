from __future__ import annotations

import http.client
import json
import os
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path("agent-skill").resolve()))

import remote_mcp_gateway  # type: ignore  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class RemoteMCPGatewayTest(unittest.TestCase):
    def setUp(self) -> None:
        self.old_remote = os.environ.get("MFG_AGENT_REMOTE_BEARER_TOKEN")
        self.old_auth = os.environ.get("MFG_AGENT_AUTH_TOKEN")
        self.old_quiet = os.environ.get("MFG_AGENT_REMOTE_QUIET")
        self.old_batch = os.environ.get("MFG_AGENT_REMOTE_MAX_BATCH")
        self.old_origins = os.environ.get("MFG_AGENT_REMOTE_ALLOWED_ORIGINS")
        os.environ["MFG_AGENT_REMOTE_BEARER_TOKEN"] = "edge-secret"
        os.environ["MFG_AGENT_AUTH_TOKEN"] = "internal-secret"
        os.environ["MFG_AGENT_REMOTE_QUIET"] = "1"

        self.port = _free_port()
        self.server = remote_mcp_gateway.ThreadingHTTPServer(
            ("127.0.0.1", self.port),
            remote_mcp_gateway.MCPGatewayHandler,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self._restore("MFG_AGENT_REMOTE_BEARER_TOKEN", self.old_remote)
        self._restore("MFG_AGENT_AUTH_TOKEN", self.old_auth)
        self._restore("MFG_AGENT_REMOTE_QUIET", self.old_quiet)
        self._restore("MFG_AGENT_REMOTE_MAX_BATCH", self.old_batch)
        self._restore("MFG_AGENT_REMOTE_ALLOWED_ORIGINS", self.old_origins)

    def test_unauthorized_post_is_rejected(self) -> None:
        status, payload = self._post({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, token=None)

        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "unauthorized")

    def test_lists_tools_over_http_json_rpc(self) -> None:
        status, payload = self._post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})

        self.assertEqual(status, 200)
        names = {tool["name"] for tool in payload["result"]["tools"]}
        self.assertIn("run_manufacturing_agent_harness", names)

    def test_remote_gateway_runs_harness_and_injects_internal_auth(self) -> None:
        sample = str(Path("samples/line_review_short_stops.csv").resolve())
        with tempfile.TemporaryDirectory() as tmp:
            status, payload = self._post({
                "jsonrpc": "2.0",
                "id": 3,
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

            self.assertEqual(status, 200)
            self.assertFalse(payload["result"]["isError"])
            result = json.loads(payload["result"]["content"][0]["text"])
            self.assertTrue(result["artifacts"])
            self.assertTrue(any(call["name"] == "run_line_review" for call in result["tool_calls"]))

    def test_gateway_does_not_use_internal_token_as_remote_bearer(self) -> None:
        self._restore("MFG_AGENT_REMOTE_BEARER_TOKEN", None)

        status, payload = self._post(
            {"jsonrpc": "2.0", "id": 4, "method": "tools/list"},
            token="internal-secret",
        )

        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "unauthorized")

    def test_batch_size_is_capped(self) -> None:
        os.environ["MFG_AGENT_REMOTE_MAX_BATCH"] = "1"

        status, payload = self._post([
            {"jsonrpc": "2.0", "id": 5, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 6, "method": "tools/list"},
        ])

        self.assertEqual(status, 200)
        self.assertEqual(payload["error"]["message"], "Batch too large")

    def test_wildcard_cors_is_not_credentialed(self) -> None:
        os.environ["MFG_AGENT_REMOTE_ALLOWED_ORIGINS"] = "*"
        body = json.dumps({"jsonrpc": "2.0", "id": 7, "method": "tools/list"}).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(
                "POST",
                "/mcp",
                body,
                {
                    "Authorization": "Bearer edge-secret",
                    "Content-Type": "application/json",
                    "Content-Length": str(len(body)),
                    "Origin": "https://example.com",
                },
            )
            response = conn.getresponse()
            response.read()
            self.assertIsNone(response.getheader("Access-Control-Allow-Origin"))
        finally:
            conn.close()

    def _post(self, request: dict, *, token: str | None = "edge-secret") -> tuple[int, dict]:
        body = json.dumps(request).encode("utf-8")
        headers = {"Content-Type": "application/json", "Content-Length": str(len(body))}
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request("POST", "/mcp", body, headers)
            response = conn.getresponse()
            data = response.read()
            return response.status, json.loads(data.decode("utf-8"))
        finally:
            conn.close()

    @staticmethod
    def _restore(name: str, value: str | None) -> None:
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


if __name__ == "__main__":
    unittest.main()