---
name: manufacturing-analyst
description: >-
  Analyze manufacturing production data (MES/OEE/downtime exports — common
  commercial MES or generic CSV/Excel) to find the operating constraint, profile
  equipment reliability (MTBF, repeat-failure, event counts), compare shifts, build
  long-horizon line reviews, draft passdowns, triage RCA, and roll up OEE +
  target attainment by line/month/quarter/year. Use when the user points at
  plant-floor data — downtime logs, OEE Overview, Event Overview, shift reports —
  and wants an analysis, a line/shift brief, a constraint, or an operating
  artifact, not a raw chart. Claude does the reading and the narrative; the
  deterministic CLI does the math.
allowed-tools: Bash, Read, Write
---

# Manufacturing Analyst

A local, deterministic manufacturing-analysis toolkit. **You (Claude Code) are the
brain** — you decide which analysis to run, read the structured output, and write
the operating brief. The CLI is the deterministic hands: pandas computes the
numbers and builds traceable artifacts; no external LLM is required.

Run everything with `--no-llm` / the deterministic subcommands. The tool has an
optional built-in OpenAI planner, but you don't want it — you *are* the planner.

## Setup (one-time, from the repo root)

The repo is `~/.openclaw/workspace/skills/manufacturing-analyst`. A `.venv` already
exists there. If `python -m analyst --help` fails, install the package editable:

```bash
cd ~/.openclaw/workspace/skills/manufacturing-analyst
python -m venv .venv 2>/dev/null; .venv/bin/python -m pip install -q -e .
```

Then invoke either as `.venv/bin/python -m analyst <command>` or, once installed,
the console script `mfg-analyst <command>`. All commands below assume you `cd` into
the repo first and use `.venv/bin/python -m analyst`.

## Which command for which question

| The user asks… | Run |
|---|---|
| "What's costing this line the most / what do I fix first?" over months of history | `line-review` |
| "How are we doing on OEE / target attainment by month/quarter/year?" | `rollup` |
| "What's the constraint this shift, what do I pass down, what do I escalate?" | `agent` or `workflow` |
| "Profile the equipment — MTBF, repeat failures" | `agent` (equipment profiles are in the output) |
| "Run the full role-based operating brief (supervisor / prod mgr / CI mgr)" | `harness --no-llm` |
| "Run a bounded autonomous observe→decide→verify cycle and log the decision" | `autonomous run` |
| "I need a client-style PDF report" | `run --no-fixes` |

## Commands (verified subcommands)

```bash
# Long-horizon line intelligence review → markdown (deterministic; the workhorse)
.venv/bin/python -m analyst line-review <data> --line "Line 1" -o reports/line_review.md

# OEE + target attainment rollup → CSVs + HTML, by line/month/quarter/year
.venv/bin/python -m analyst rollup <data> --grains year,quarter,month --line line-2 -o reports/rollup

# Shift Intelligence Agent → JSON (constraint, risk, approval gate, passdown,
# watchlist, equipment profiles, 7/30/90 verification cadence)
.venv/bin/python -m analyst agent <data> -s "Short Stops and Unassigned are high on Line 1" -o out.json

# Full load→analyze→agent→(eval) workflow → JSON artifact
.venv/bin/python -m analyst workflow <data> -s "General shift intelligence" -o reports

# Markdown-driven role harness (supervisor/prod-mgr/CI-mgr briefs). --no-llm keeps
# it deterministic — you supply the intelligence, it stages data + writes artifacts.
.venv/bin/python -m analyst harness --no-llm -m "Review 10 months of Line 1. Build the three role briefs." --data <data> --workspace agent-workspace

# Autonomous operating loop: one bounded cycle (writes local artifacts only,
# no plant changes, no external sends), then check status / record the outcome.
.venv/bin/python -m analyst autonomous run --data <data> --line "Line 1" --workspace agent-workspace
.venv/bin/python -m analyst autonomous status --workspace agent-workspace
.venv/bin/python -m analyst autonomous outcome --workspace agent-workspace --decision-id <id> --quality good --outcome "repeat rate fell vs baseline"
```

`<data>` is a **directory** containing your CSV/XLSX exports — the CLI subcommands
(`run`, `agent`, `workflow`, `line-review`, `rollup`) load *every* supported file
in it, so drop the event export and the OEE export into one folder and point at the
folder, not a single file. Formats are auto-detected (common MES Event Overview / OEE
Overview / pivot, or generic CSV/Excel with date + equipment/machine + duration
columns). (`harness` and `autonomous` take `--data` as either a file or a directory —
they stage it into the workspace inbox.)

## Reading the output → write the brief

`line-review` prints markdown you can hand back nearly as-is. `agent` / `workflow`
return JSON — the fields worth surfacing:

- `constraint` — the suspected operating constraint
- `risk` / `approval_gate` — whether a human sign-off is required before acting
- `equipment_profiles[]` — `equipment`, `events`, `downtime_hours`, `repeat_failure_rate`, `mtbf_minutes`
- `verification_followups.cadence[]` — the 7/30/90-day checks to schedule
- `visibility_score` (line-review) — treat **Short Stops / Unassigned / Unknown / Other**
  as visibility-loss signals, not just downtime codes; a low score means fix the
  *signal* (event-fidelity sprint) before launching RCA

Then write the operating brief yourself: name specific equipment, specific shifts,
specific numbers, one highest-leverage recommendation, and point every claim back
to the tool output. Don't invent plant facts the data doesn't support.

## Sandbox (for `harness` / `autonomous`)

These stage data into a workspace and are path-confined by env roots. Set them to
keep the tool inside safe directories:

```bash
export MFG_AGENT_DATA_ROOTS=~/Downloads          # where input data may be read from
export MFG_AGENT_WORKSPACE_ROOTS=~/agent-workspace  # where artifacts may be written
```

LLM egress is **off by default** (`MFG_AGENT_ALLOW_LLM_*` unset) and every path has
a deterministic fallback, so the toolkit runs fully offline. Keep it that way when
running inside Claude Code.

## Guardrails

- Plant data stays local — never upload or send it externally.
- Prefer the deterministic subcommands (`line-review`, `rollup`, `agent`,
  `workflow`, `harness --no-llm`). Only enable the internal LLM planner if Claude
  Code is *not* available to drive.
- The autonomous loop is autonomous only in the local-artifact sense: it observes,
  decides, writes markdown/JSON, and schedules verification. It makes no plant
  changes and contacts no one. Keep it that way.
