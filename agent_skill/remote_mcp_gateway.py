"""HTTP JSON-RPC gateway for the manufacturing MCP server.

This is a small network bridge around the repo's stdio MCP handler. It keeps
tool behavior in ``mcp_tool.handle_request`` and adds only transport concerns:
HTTP, bearer auth, request size limits, and health checks.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

try:
    from . import mcp_tool
except ImportError:  # pragma: no cover - direct script execution fallback
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import mcp_tool  # type: ignore  # noqa: E402


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
MAX_BODY_BYTES = 2 * 1024 * 1024
DEFAULT_MAX_BATCH_REQUESTS = 10
DEFAULT_READ_TIMEOUT_SECONDS = 10
DEFAULT_MAX_CONCURRENCY = 16
_SEMAPHORE: threading.BoundedSemaphore | None = None
_SEMAPHORE_LIMIT: int | None = None


def _json_rpc_error(id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


def _bearer_token() -> str | None:
    return os.environ.get("MFG_AGENT_REMOTE_BEARER_TOKEN")


def _origin_allowed(origin: str | None) -> bool:
    allowed = os.environ.get("MFG_AGENT_REMOTE_ALLOWED_ORIGINS")
    if not allowed:
        return False
    origins = {item.strip() for item in allowed.split(",") if item.strip()}
    return bool(origin and origin in origins)


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _max_body_bytes() -> int:
    return _int_env("MFG_AGENT_REMOTE_MAX_BODY_BYTES", MAX_BODY_BYTES)


def _max_batch_requests() -> int:
    return _int_env("MFG_AGENT_REMOTE_MAX_BATCH", DEFAULT_MAX_BATCH_REQUESTS)


def _read_timeout_seconds() -> int:
    return _int_env("MFG_AGENT_REMOTE_READ_TIMEOUT_SECONDS", DEFAULT_READ_TIMEOUT_SECONDS)


def _request_semaphore() -> threading.BoundedSemaphore:
    global _SEMAPHORE, _SEMAPHORE_LIMIT
    limit = _int_env("MFG_AGENT_REMOTE_MAX_CONCURRENCY", DEFAULT_MAX_CONCURRENCY)
    if _SEMAPHORE is None or _SEMAPHORE_LIMIT != limit:
        _SEMAPHORE = threading.BoundedSemaphore(limit)
        _SEMAPHORE_LIMIT = limit
    return _SEMAPHORE


def _with_internal_auth(request: dict[str, Any]) -> dict[str, Any]:
    """Pass bearer-authenticated remote calls through the existing MCP auth gate."""
    expected = os.environ.get("MFG_AGENT_AUTH_TOKEN")
    if not expected or request.get("method") != "tools/call":
        return request

    params = request.setdefault("params", {})
    if not isinstance(params, dict):
        return request
    args = params.setdefault("arguments", {})
    if isinstance(args, dict) and "auth_token" not in args:
        args["auth_token"] = expected
    return request


class MCPGatewayHandler(BaseHTTPRequestHandler):
    server_version = "ManufacturingMCPGateway/1.0"

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json({"status": "ok", "server": "manufacturing-management-agent"})
            return
        self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._write_cors_headers()
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.end_headers()

    def do_POST(self) -> None:
        semaphore = _request_semaphore()
        if not semaphore.acquire(blocking=False):
            self._send_json({"error": "too many concurrent requests"}, status=HTTPStatus.TOO_MANY_REQUESTS)
            return
        try:
            self._do_post()
        finally:
            semaphore.release()

    def _do_post(self) -> None:
        if self.path not in {"/", "/mcp"}:
            self._send_json({"error": "not found"}, status=HTTPStatus.NOT_FOUND)
            return
        if not self._authorized():
            self._send_json({"error": "unauthorized"}, status=HTTPStatus.UNAUTHORIZED)
            return

        try:
            body = self._read_body()
            payload = json.loads(body)
        except json.JSONDecodeError:
            self._send_json(_json_rpc_error(None, -32700, "Parse error"), status=HTTPStatus.BAD_REQUEST)
            return
        except ValueError as exc:
            self._send_json(_json_rpc_error(None, -32700, str(exc)), status=HTTPStatus.BAD_REQUEST)
            return

        try:
            response = self._dispatch(payload)
        except Exception:  # defensive transport guard; tool errors stay in MCP result.
            response = _json_rpc_error(None, -32603, "Internal error")
            self._send_json(response, status=HTTPStatus.INTERNAL_SERVER_ERROR)
            return

        if response is None:
            self.send_response(HTTPStatus.NO_CONTENT)
            self._write_cors_headers()
            self.end_headers()
            return
        self._send_json(response)

    def log_message(self, format: str, *args: Any) -> None:
        if os.environ.get("MFG_AGENT_REMOTE_QUIET") == "1":
            return
        super().log_message(format, *args)

    def _authorized(self) -> bool:
        expected = _bearer_token()
        if not expected:
            return False
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return False
        supplied = auth.removeprefix("Bearer ").strip()
        return secrets.compare_digest(supplied, expected)

    def _read_body(self) -> str:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("Missing Content-Length")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("Invalid Content-Length") from exc
        if length < 0:
            raise ValueError("Invalid Content-Length")
        if length > _max_body_bytes():
            raise ValueError("Request body too large")
        self.connection.settimeout(_read_timeout_seconds())
        try:
            return self.rfile.read(length).decode("utf-8")
        except TimeoutError as exc:
            raise ValueError("Request body read timed out") from exc
        except OSError as exc:
            raise ValueError("Request body read failed") from exc
        except UnicodeDecodeError as exc:
            raise ValueError("Invalid UTF-8 request body") from exc

    def _dispatch(self, payload: Any) -> Any:
        if isinstance(payload, list):
            if len(payload) > _max_batch_requests():
                return _json_rpc_error(None, -32600, "Batch too large")
            responses = []
            for item in payload:
                if not isinstance(item, dict):
                    responses.append(_json_rpc_error(None, -32600, "Invalid Request"))
                    continue
                response = mcp_tool.handle_request(_with_internal_auth(item))
                if response is not None:
                    responses.append(response)
            return responses or None
        if not isinstance(payload, dict):
            return _json_rpc_error(None, -32600, "Invalid Request")
        return mcp_tool.handle_request(_with_internal_auth(payload))

    def _write_cors_headers(self) -> None:
        origin = self.headers.get("Origin")
        if _origin_allowed(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")

    def _send_json(self, payload: Any, *, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self._write_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def run_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    if not _bearer_token():
        raise RuntimeError(
            "Refusing to start remote MCP gateway without "
            "MFG_AGENT_REMOTE_BEARER_TOKEN."
        )
    server = ThreadingHTTPServer((host, port), MCPGatewayHandler)
    print(f"Manufacturing MCP gateway listening on http://{host}:{port}/mcp", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="HTTP gateway for the manufacturing MCP JSON-RPC server")
    parser.add_argument("--host", default=os.environ.get("MFG_AGENT_REMOTE_HOST", DEFAULT_HOST))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MFG_AGENT_REMOTE_PORT", DEFAULT_PORT)))
    args = parser.parse_args()
    run_server(args.host, args.port)


if __name__ == "__main__":
    main()