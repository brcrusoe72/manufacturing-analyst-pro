# Manufacturing Intelligence Analyst — Agent Skill

A vertical AI skill that analyzes MES/SCADA production data for OEE losses, equipment reliability, shift performance, and trends. Packaged for deployment as a standalone agent (via Agent Café) or as an MCP tool for any agent.

## What It Does

- **OEE Analysis** — Overall Equipment Effectiveness breakdown
- **Equipment Profiling** — MTBF, repeat failure rates, shift-by-shift behavior
- **Shift Comparison** — Cross-shift performance gaps, startup penalties, notable patterns
- **Trend Detection** — Monthly trend direction (improving/worsening/stable)
- **Narrative Reports** — LLM-generated executive briefs (~$0.005/report)
- **Shift Intelligence Workflow** — tool trace, constraint triage, RCA/passdown memory, risk scoring, approval gate, action plan, recurrence watchlist, and 7/30/90-day verification

Input: Excel/CSV files with downtime events and/or OEE intervals  
Output: Structured JSON analysis + optional markdown narrative

## How The Harness Works

The harness is the bridge between a general AI agent and the manufacturing tool layer.

```text
User / supervisor request
  -> outer AI agent decides whether plant data is needed
  -> harness validates required inputs
  -> workflow tool loads MES/OEE files
  -> deterministic analyzer computes plant facts
  -> Shift Intelligence Agent runs tools in order
  -> harness returns final answer + full JSON trace
  -> outer AI agent explains, asks follow-up, or routes approval
```

The AI agent is not supposed to invent plant facts. It should call the workflow
tool, read the returned trace/evidence, and only then answer.

## Quick Start

### As a Python Library

```python
from agent_wrapper import run_analysis

result = run_analysis({
    "data_file": "/path/to/data/directory",
    "question": "What's driving the most downtime on Line 3?",
    "generate_narrative": True,
})

print(result["status"])  # "success"
print(result["analysis"]["top_loss_driver"])
print(result["narrative"]["full_text"])
```

### As A Harness

```python
from harness import ManufacturingAgentHarness

response = ManufacturingAgentHarness().handle({
    "message": "Line 1 has repeated tray packer jams. Build passdown, escalation, and 7/30/90 verification.",
    "data_file": "/path/to/line-1-data/",
    "evals_file": "../evals/shift_intelligence_scenarios.json",
    "output": "reports/",
})

print(response.status)
print(response.message)
print(response.payload["answer"])
```

CLI:

```bash
python harness.py /path/to/line-1-data/ \
  --message "Repeated tray packer jams need passdown, RCA, escalation, and verification" \
  --evals-file ../evals/shift_intelligence_scenarios.json \
  --output reports/
```

### As Its Own Standalone Agent

Use this when you want the tool to behave more like a focused OpenClaw-style
worker: it watches an inbox, notices new plant data, runs the workflow, writes
state, and creates alert/highlight files when risk deserves attention.

Run once:

```bash
python standalone_agent.py /path/to/plant-inbox/ \
  --state-dir agent-state/ \
  --evals-file ../evals/shift_intelligence_scenarios.json
```

Watch continuously:

```bash
python standalone_agent.py /path/to/plant-inbox/ \
  --state-dir agent-state/ \
  --evals-file ../evals/shift_intelligence_scenarios.json \
  --watch \
  --interval 300
```

Outputs:

```text
agent-state/
  state.json          # fingerprints already processed datasets
  runs/               # full workflow JSON artifacts
  alerts/             # medium/high-priority highlights
```

This is not a general-purpose agent OS. It is a standalone agentic highlighter:
it observes plant data, decides whether the signal matters, runs tools, records
evidence, and produces a highlight for a human or larger agent to act on.

### CLI Testing

```bash
cd skills/manufacturing-analyst/agent-skill
python agent_wrapper.py /path/to/data/directory "What's the top loss driver?"
```

## Deploy as MCP Tool

Add to your MCP client config (e.g., Claude Desktop, OpenClaw):

```json
{
  "mcpServers": {
    "manufacturing-analyst": {
      "command": "/path/to/repo/.venv/bin/python",
      "args": ["/path/to/repo/agent-skill/mcp_tool.py"],
      "env": {
        "OPENAI_API_KEY": "optional-key",
        "MFG_AGENT_ALLOW_LLM_PLANNER": "0",
        "MFG_AGENT_DATA_ROOTS": "/path/to/plant-data",
        "MFG_AGENT_BEHAVIOR_ROOTS": "/path/to/repo",
        "MFG_AGENT_WORKSPACE_ROOTS": "/path/to/repo:/tmp"
      }
    }
  }
}
```

There is also a local example at `agent-skill/mcp-config.example.json`.

### Available Tools

| Tool | Description |
|------|-------------|
| `analyze_production_data` | Full OEE/downtime/shift/trend analysis |
| `generate_shift_report` | Shift-specific analysis (optionally filtered to one shift) |
| `equipment_health_check` | Equipment profiling — MTBF, repeat rates, shift breakdown |
| `run_shift_intelligence_workflow` | Full tool-using plant agent workflow with trace, approval gate, watchlist, verification, and evals |
| `run_manufacturing_agent_harness` | Markdown-driven OpenClaw/Codex-facing harness that loads AGENT.md/TOOLS.md/role files, stages data, plans tool calls, and writes workspace artifacts |

### MCP Tool Use

An AI agent connected through MCP should call `run_shift_intelligence_workflow`
when the user asks operational questions like:

- "What should the supervisor do about repeated jams?"
- "Draft the next shift passdown."
- "Does this need escalation?"
- "Build a recurrence watchlist."
- "Check whether the fix held after 7/30/90 days."

It should call the simpler analysis tools when the user only needs raw analysis,
shift comparison, or equipment-health facts.

Use `run_manufacturing_agent_harness` when the user wants an agentic experience:

- "Act like the production manager and CI manager. Build what we need from this data."
- "Use the harness behavior files and decide the next artifact."
- "Take this 10-month line export and build the supervisor/manager/CI package."
- "Create the run workspace and artifacts so I can inspect the agent's work."

Example MCP call arguments:

```json
{
  "message": "Review 10 months of Line 1 data. Short Stops and Unassigned are suspected to be the highest codes. Build what supervisor, production manager, and CI need next.",
  "data_file": "samples/line_review_short_stops.csv",
  "line": "Line 1",
  "workspace": "agent-workspace",
  "use_llm": true
}
```

The tool returns a JSON harness run containing loaded behavior files, planner
choice, tool trace, artifact paths, and final answer.

Security boundary: keep `MFG_AGENT_DATA_ROOTS`, `MFG_AGENT_BEHAVIOR_ROOTS`, and
`MFG_AGENT_WORKSPACE_ROOTS` narrow. `MFG_AGENT_ALLOWED_ROOTS` remains as a
legacy alias for data roots. The MCP tool rejects local paths outside those
roots, sanitizes staged filenames, and writes local artifacts into the
configured workspace. LLM egress is disabled unless the relevant
`MFG_AGENT_ALLOW_LLM_*` flag is set.

## Deploy on Agent Café

### Environment Variables

```bash
export AGENT_CAFE_URL="https://your-cafe.example.com"
export AGENT_CAFE_KEY="your-agent-key"
export OPENAI_API_KEY="sk-..."  # Optional; also set MFG_AGENT_ALLOW_LLM_NARRATIVE=1
```

### Run the Agent

```bash
cd skills/manufacturing-analyst/agent-skill
python cafe_integration.py
```

The agent will:
1. Register on Agent Café with its skill manifest
2. Poll the job board every 30s for matching jobs
3. Auto-bid on jobs tagged with manufacturing/OEE/downtime capabilities
4. Run analysis and deliver results through the wire protocol

### Job Format

Jobs should include data as an attachment (URL or base64):

```json
{
  "title": "Analyze Line 3 downtime for March",
  "tags": ["oee-analysis", "downtime-analysis"],
  "attachments": [
    { "url": "https://example.com/line3-march.xlsx", "filename": "line3-events.xlsx" }
  ],
  "question": "What's driving the most downtime?"
}
```

## Architecture

```
agent-skill/
├── skill_manifest.json   # Capability manifest (what this agent can do)
├── agent_wrapper.py      # Core wrapper (job → analysis → results)
├── harness.py            # Conversational harness (request → tool workflow → answer)
├── standalone_agent.py   # Watch/inbox agentic highlighter
├── cafe_integration.py   # Agent Café marketplace client
├── mcp_tool.py           # MCP tool server (stdio transport)
└── README.md

analyst/                  # The actual engine (imported by wrappers)
├── engine.py             # Pure pandas analysis
├── loader.py             # File loading + format detection
├── parsers/              # MES data parsers
├── narrative.py          # LLM narrative generation
└── ...
```

## Pricing

- Pandas analysis: free (CPU only)
- Narrative generation: ~$0.003-0.01 via OpenAI (gpt-5.2)
- Agent Café base bid: $1.00/analysis (configurable)

## Requirements

- Python ≥ 3.10
- pandas, openpyxl
- openai (for narrative generation)
- requests (for café integration)