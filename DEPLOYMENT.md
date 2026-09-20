# Deployment Guide

This project is safest as a local MCP stdio server used by Codex, OpenClaw, or
another trusted desktop/agent runtime. Remote deployment needs an extra wrapper
because stdio MCP itself does not provide network authentication.

## Local MCP

```bash
python -m venv .venv
.venv/bin/python -m pip install -e .

codex mcp add manufacturing-management-agent -- \
  "$(pwd)/.venv/bin/mfg-mcp-tool"
```

Optional local hardening:

```bash
export MFG_AGENT_ALLOWED_ROOTS="$(pwd):/path/to/plant-data"
export MFG_AGENT_WORKSPACE_ROOTS="$(pwd):/tmp"
export MFG_AGENT_AUTH_TOKEN="local-long-random-token"
```

When `MFG_AGENT_AUTH_TOKEN` is set, every MCP tool call must include
`auth_token`.

## Remote MCP Gateway

Do not expose stdio MCP directly on the internet. The installed
`mfg-mcp-gateway` command is a small HTTP JSON-RPC bridge around the same
`mcp_tool.handle_request` implementation used by stdio MCP. The repo-local
`agent-skill/remote_mcp_gateway.py` path remains available for editable/dev
setups.

Run it on loopback behind a real TLS edge:

```bash
python -m venv .venv
.venv/bin/python -m pip install -e .

export MFG_AGENT_DATA_ROOTS="/srv/mfg-agent/data"
export MFG_AGENT_BEHAVIOR_ROOTS="/srv/mfg-agent/behavior:/srv/mfg-agent/manufacturing-analyst"
export MFG_AGENT_WORKSPACE_ROOTS="/srv/mfg-agent/workspaces"
export MFG_AGENT_REMOTE_BEARER_TOKEN="<long-random-edge-token>"
export MFG_AGENT_AUTH_TOKEN="<long-random-internal-token>"
export MFG_AGENT_REMOTE_MAX_BATCH=10
export MFG_AGENT_REMOTE_MAX_CONCURRENCY=16

.venv/bin/mfg-mcp-gateway --host 127.0.0.1 --port 8765
```

Use Caddy, nginx, Tailscale Funnel, Cloudflare Tunnel, or an equivalent edge
proxy to provide HTTPS and forward only to `http://127.0.0.1:8765/mcp`.

HTTP requests must include:

```text
Authorization: Bearer <long-random-edge-token>
Content-Type: application/json
```

Example:

```bash
curl -sS http://127.0.0.1:8765/mcp \
  -H "Authorization: Bearer $MFG_AGENT_REMOTE_BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

For `tools/call`, the gateway injects `MFG_AGENT_AUTH_TOKEN` into the MCP tool
arguments when the caller has already passed the edge bearer check. Direct stdio
MCP clients can still pass `auth_token` themselves.

The service account should only have read access to plant-data roots and write
access to the workspace root.

LLM egress is disabled by default even when `OPENAI_API_KEY` exists. Enable only
the features needed by the deployment:

```bash
export MFG_AGENT_ALLOW_LLM_PLANNER=1
export MFG_AGENT_ALLOW_LLM_NARRATIVE=1
export MFG_AGENT_ALLOW_LLM_RESEARCH=1
export MFG_AGENT_ALLOW_LLM_SMART_PARSER=1
```

Use `MFG_AGENT_CACHE=0` and `MFG_AGENT_LLM_CACHE=0` for no-cache remote runs.
Use `MFG_AGENT_DEBUG=1` only in trusted local debugging; otherwise external
errors are sanitized and tracebacks stay out of MCP/HTTP/UI responses.

### Minimal systemd service

```ini
[Unit]
Description=Manufacturing MCP Gateway
After=network.target

[Service]
WorkingDirectory=/srv/mfg-agent/manufacturing-analyst
Environment=MFG_AGENT_DATA_ROOTS=/srv/mfg-agent/data
Environment=MFG_AGENT_BEHAVIOR_ROOTS=/srv/mfg-agent/manufacturing-analyst
Environment=MFG_AGENT_WORKSPACE_ROOTS=/srv/mfg-agent/workspaces
Environment=MFG_AGENT_REMOTE_BEARER_TOKEN=replace-me
Environment=MFG_AGENT_AUTH_TOKEN=replace-me-too
Environment=MFG_AGENT_REMOTE_MAX_BATCH=10
Environment=MFG_AGENT_REMOTE_MAX_CONCURRENCY=16
ExecStart=/srv/mfg-agent/manufacturing-analyst/.venv/bin/mfg-mcp-gateway --host 127.0.0.1 --port 8765
Restart=on-failure
User=mfg-agent
Group=mfg-agent

[Install]
WantedBy=multi-user.target
```

## Release

CI runs on every push and pull request. Release builds run on `v*.*.*` tags and
upload source/wheel artifacts from `dist/`.

```bash
git tag v0.1.0
git push origin v0.1.0
```

The current release workflow does not publish to PyPI automatically. That is
intentional until package ownership and secrets/trusted publishing are set up.