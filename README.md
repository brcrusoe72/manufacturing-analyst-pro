# Manufacturing Management Agent Harness

An OpenClaw-style manufacturing agent harness: markdown behavior files, a tool
registry, persistent workspace artifacts, and plant-data tools for production
supervisor, production manager, and CI manager work.

This is not a business landing page and not just a dashboard. The goal is an
actual agentic app that can engage with a user, inspect manufacturing data,
choose tools, and build the artifacts it thinks are needed.

Behavior lives in markdown:

```text
agent-harness/
├── AGENT.md
├── TOOLS.md
└── roles/
    ├── PRODUCTION_SUPERVISOR.md
    ├── PRODUCTION_MANAGER.md
    └── CI_MANAGER.md
```

Run one agent turn:

```bash
python -m pip install -e .

python -m analyst harness \
  --data samples/line_review_short_stops.csv \
  --line "Line 1" \
  --message "Review 10 months of Line 1 data. Short Stops and Unassigned are suspected to be the highest codes." \
  --workspace agent-workspace \
  --no-llm
```

Run interactively:

```bash
python -m analyst harness --workspace agent-workspace
```

Inside the interactive shell:

```text
/data samples/line_review_short_stops.csv
/line Line 1
Review this like a production manager and CI manager. Build what we need next.
```

The harness writes:

```text
agent-workspace/
├── MEMORY.md
├── inbox/
├── artifacts/
└── runs/
```

For the Short Stops / Unassigned sample, one run builds:

```text
artifacts/<run-id>/
├── line-review.md
├── management-brief.md
├── event-fidelity-sprint.md
└── operating-brief.md
```

That is the intended shape: the agent inspects data, chooses tools, and then
builds the next useful operating artifacts from the results.

## MCP / OpenClaw Access

The harness is exposed through the MCP stdio server at:

```text
mfg-mcp-tool
```

After `pip install .` or installing the wheel, add this server to an
MCP-capable client such as OpenClaw, Codex, or Claude Desktop. For editable
repo-local development, `python agent-skill/mcp_tool.py` remains supported. The
key tool is:

```text
run_manufacturing_agent_harness
```

That tool loads the markdown behavior files, optionally uses an LLM planner,
stages plant data, runs the harness, and returns artifact paths plus the run
trace.

For a repeatable Codex command, see `codex-run-prompt.md`.
For remote deployment and release guidance, see `DEPLOYMENT.md`.

### Remote MCP Gateway

The repo also includes an HTTP JSON-RPC gateway for network use:

```bash
export MFG_AGENT_REMOTE_BEARER_TOKEN="$(python - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)"
export MFG_AGENT_AUTH_TOKEN="$(python - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)"
export MFG_AGENT_DATA_ROOTS="/path/to/plant-data"
export MFG_AGENT_BEHAVIOR_ROOTS="$(pwd)"
export MFG_AGENT_WORKSPACE_ROOTS="/srv/mfg-agent/workspaces:/tmp"

mfg-mcp-gateway --host 127.0.0.1 --port 8765
```

Then put Caddy, nginx, Tailscale Funnel, Cloudflare Tunnel, or another TLS
terminating reverse proxy in front of `http://127.0.0.1:8765/mcp`.

Remote requests are normal MCP JSON-RPC payloads over HTTP:

```bash
curl -sS http://127.0.0.1:8765/mcp \
  -H "Authorization: Bearer $MFG_AGENT_REMOTE_BEARER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

The gateway rejects unauthenticated requests and passes authenticated tool calls
through the same MCP handler used by the stdio server.

### Path Safety

The MCP tool is intended to run as a trusted local tool. By default, it only
reads plant data and behavior files from the repo/current directory and only
writes workspaces under the current directory or the system temp directory.

To allow real plant data folders, set explicit roots:

```bash
export MFG_AGENT_DATA_ROOTS="/path/to/plant-data"
export MFG_AGENT_BEHAVIOR_ROOTS="/path/to/behavior-files"
export MFG_AGENT_WORKSPACE_ROOTS="/path/to/agent-workspaces:/tmp"
```

`MFG_AGENT_ALLOWED_ROOTS` remains as a legacy alias for data roots. Once explicit
data roots are set, the project root is not silently added for plant-data reads.
Do not expose the MCP server directly to untrusted remote users without keeping
these roots narrow.

If `MFG_AGENT_AUTH_TOKEN` is set on the MCP server, every tool call must include
the matching `auth_token` argument.

## What It Does

- Loads markdown behavior and role files
- Stages plant data into a local harness workspace
- Inspects CSV/Excel downtime and OEE files
- Chooses from manufacturing tools
- Builds line reviews, shift workflows, passdowns, watchlists, and verification artifacts
- Builds follow-on artifacts such as management briefs and 14-day event-fidelity sprints
- Saves run JSON, tool traces, markdown artifacts, and harness memory

## Supported Formats

- Common commercial MES Event Overview & OEE Overview exports
- Generic CSV/Excel with columns like: date, equipment/machine, duration
- Multiple files (event + OEE together)

## Legacy Analyzer UI

```bash
pip install -r requirements.txt
streamlit run app.py
```

The Streamlit analyzer is still present, but the main project direction is the
markdown-driven agent harness.

## Shift Intelligence Agent

The repo now includes a tool-using agent layer. It does not just chat over a report:
it queries structured OEE/downtime facts, finds the current constraint, searches
prior passdown/RCA memory, scores escalation risk, applies approval gates, creates
a supervisor action plan, drafts passdown notes, builds a recurrence watchlist,
schedules 7/30/90-day verification follow-ups, and records every tool call.

Run it on a data folder:

```bash
python -m analyst agent ./data \
  --scenario "Line 1 has repeated tray packer jams after changeover"
```

Save a JSON trace:

```bash
python -m analyst agent ./data \
  --scenario "Draft the next shift passdown for the top constraint" \
  --output reports/shift_agent_report.json
```

Run agent evals:

```bash
python -m analyst agent ./data \
  --evals evals/shift_intelligence_scenarios.json
```

Run the root-to-tip workflow:

```bash
python -m analyst workflow ./data \
  --scenario "Repeated tray packer jams need passdown, RCA, escalation, and verification" \
  --evals evals/shift_intelligence_scenarios.json \
  --output reports/
```

## Autonomous Operating Loop

The `autonomous` command wraps the harness in a bounded operating cycle:

```text
observe data -> decide constraint -> write local artifacts -> schedule verification -> capture outcome
```

It does not send messages, create tickets, change schedules, hold QA product, or
claim proven root cause. Those remain human-gated. The agent's autonomous action
surface is local: artifacts, decision logs, verification queues, and operating
board updates.

Run one cycle:

```bash
python -m analyst autonomous run \
  --data samples/line_review_short_stops.csv \
  --line "Line 1" \
  --workspace agent-workspace
```

The cycle writes:

```text
agent-workspace/
├── artifacts/
├── runs/
└── autonomy/
    ├── cycles/<cycle-id>.json
    ├── decisions.jsonl
    ├── verification_queue.json
    ├── outcomes.jsonl
    └── operating-board.md
```

Check status:

```bash
python -m analyst autonomous status --workspace agent-workspace
```

Record what actually happened:

```bash
python -m analyst autonomous outcome \
  --workspace agent-workspace \
  --decision-id dec_20260706-120000-000000 \
  --quality mixed \
  --outcome "Downtime fell, but coding stayed too vague to prove the cause class." \
  --helped "The watchlist forced recurrence checks." \
  --misled "Short Stop volume masked the equipment family."
```

That outcome record is the important part. Without it, this is just a scheduled
report generator. With it, the tool starts accumulating a grounded operating
memory: what it decided, what it expected, what actually happened, and what
helped or misled.

The workflow produces one JSON artifact containing:

- parsed data counts
- deterministic analysis snapshot
- agent intent classification
- ordered tool trace
- current constraint and numeric evidence
- prior RCA/passdown matches
- risk score and human approval gate
- escalation path
- supervisor action plan
- shift passdown draft
- recurrence watchlist
- 7/30/90-day verification plan
- optional eval results

### Agent Workflow Layers

```text
MES/OEE exports
  -> loader/parsers
  -> deterministic analysis engine
  -> agent intent classifier
  -> tool policy
  -> data query + constraint finder
  -> prior RCA/passdown search
  -> risk scoring + approval gate
  -> escalation path
  -> supervisor action plan
  -> passdown draft
  -> recurrence watchlist
  -> 7/30/90 verification follow-up
  -> trace + eval report
```

Agent tools:

- `query_oee_data`
- `classify_agent_intent`
- `find_constraint_area`
- `find_prior_rcas`
- `risk_score_event`
- `human_approval_required`
- `recommend_escalation_path`
- `create_action_plan`
- `draft_shift_passdown`
- `build_recurrence_watchlist`
- `schedule_verification_followups`

## Built By

A production supervisor with 8+ years in food manufacturing, Six Sigma Black Belt, and deep MES experience. This tool exists because every OEE software shows dashboards — none of them tell you what the numbers mean.

## Privacy

The harness writes local artifacts by design: staged inbox files, run JSON,
markdown reports, and `MEMORY.md` inside the selected workspace. It does not
send plant data to an LLM by default. LLM egress requires an explicit feature
flag in addition to `OPENAI_API_KEY`:

```bash
export MFG_AGENT_ALLOW_LLM_PLANNER=1
export MFG_AGENT_ALLOW_LLM_NARRATIVE=1
export MFG_AGENT_ALLOW_LLM_RESEARCH=1
export MFG_AGENT_ALLOW_LLM_SMART_PARSER=1
```

Parser cache and LLM cache can be disabled with `MFG_AGENT_CACHE=0` and
`MFG_AGENT_LLM_CACHE=0`. The deterministic path works with `--no-llm`.

## Related Projects

- **[AgentSearch](https://github.com/brcrusoe72/agent-search)** — Free, self-hosted search API for AI agents
- **[Agent Café](https://github.com/brcrusoe72/agent-cafe)** — AI agent marketplace ([live at thecafe.dev](https://thecafe.dev))
- **[AI True Cost Calculator](https://trueaicost.com)** — Know what your AI project really costs