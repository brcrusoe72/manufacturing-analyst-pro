# Codex Run Prompt - Manufacturing Management Agent Harness

Register the MCP server with Codex:

```bash
cd /path/to/manufacturing-analyst
python -m venv .venv
.venv/bin/python -m pip install -e .
codex mcp add manufacturing-management-agent -- \
  "$(pwd)/.venv/bin/python" \
  "$(pwd)/agent-skill/mcp_tool.py"
```

Run a Codex smoke:

```bash
codex exec \
  -C /path/to/manufacturing-analyst \
  --sandbox danger-full-access \
  --dangerously-bypass-approvals-and-sandbox \
  "Use the manufacturing-management-agent MCP tool named run_manufacturing_agent_harness. Run it with message='Review 10 months of Line 1 data. Short Stops and Unassigned are high. Build the supervisor, production manager, and CI manager artifacts.', data_file='samples/line_review_short_stops.csv', line='Line 1', workspace='/tmp/codex-mfg-harness-smoke', use_llm=false. Do not edit files. Return the tool result summary and artifact paths."
```

Expected signal in Codex output:

```text
mcp: manufacturing-management-agent/run_manufacturing_agent_harness started
mcp: manufacturing-management-agent/run_manufacturing_agent_harness (completed)
```

Expected artifacts:

```text
/tmp/codex-mfg-harness-smoke/artifacts/<run-id>/line-review.md
/tmp/codex-mfg-harness-smoke/artifacts/<run-id>/management-brief.md
/tmp/codex-mfg-harness-smoke/artifacts/<run-id>/event-fidelity-sprint.md
/tmp/codex-mfg-harness-smoke/artifacts/<run-id>/operating-brief.md
```

Use `use_llm=false` for deterministic smoke tests. Use `use_llm=true` when
`OPENAI_API_KEY` is available and you want the harness planner to use an LLM.