# SPEC: Manufacturing Analyst Agent

_Data in, insight out. Nothing else._

---

## 1. What am I actually trying to accomplish?

An autonomous agent that takes MES data exports (Excel files), analyzes them, researches fixes for the top problems, and delivers a PDF report — without a human in the loop.

Not a platform. Not a framework. Not 23K lines. A tool that works.

## 2. Why does this matter?

Because the analysis I did manually today — loading 46K events, computing MTBF, comparing shifts, searching for case packer troubleshooting guides, writing a narrative a PM would act on — took an AI agent with tools about 15 minutes. It would take a plant engineer half a day. It would take Vigil's 23K-line agent pipeline... never, because it can't do it.

The value isn't in the infrastructure. It's in the output. A plant manager gets a 1-page report that says: "Your caser is failing every 6 minutes. Here's why. Here's how to fix it. Here's what 1st shift does differently than 3rd." That's worth money. Everything else is overhead.

## 3. What does "done" look like?

Drop Excel files in a folder. Get a PDF on your desktop (or in your inbox) that contains:

**Page 1: Production Analysis**
- Direct answer to "what's costing this line the most?"
- Top equipment by downtime hours, with MTBF and repeat failure rates
- Shift comparison with specific OEE numbers
- Trend direction (improving/worsening)
- One recommendation: "if you can only fix one thing"

**Page 2: Root Cause & Fixes**
- For the top 3 equipment loss drivers:
  - What the failure mode likely means mechanically
  - Probable root causes based on industry knowledge + equipment research
  - Specific fixes (with PM checklist items)
  - If shift variation exists, what the crew difference likely indicates
- Sources cited (equipment manufacturer resources, industry guides)

**Delivered automatically.** No human says "run analysis." The agent watches for new data, processes it, delivers the report.

## 4. What does "wrong" look like?

- ❌ Requires a human to trigger or interpret
- ❌ Produces stats without interpretation ("OEE is 20%" — so what?)
- ❌ Generic advice ("improve maintenance practices")
- ❌ Takes more than 5 minutes to produce a report
- ❌ Requires configuration, setup wizards, or onboarding
- ❌ More than 1,000 lines of code
- ❌ Has its own agent framework, entity model, or event bus
- ❌ Needs anything beyond Python, pandas, fpdf2, openai, and a search API

## 5. What do I already know?

### The analysis pipeline that works (proven today)

```
Excel files
  → parse with openpyxl (event exports + OEE exports)
  → pandas groupby/agg for:
      - equipment rollup (count, hours, avg duration)
      - shift derivation from timestamps (1st/2nd/3rd)
      - shift OEE comparison from OEE intervals
      - MTBF (median inter-failure interval per equipment)
      - repeat failure rate (same equipment within 30 min)
      - reason code ranking by hours
      - unassigned rate per shift
      - monthly trend buckets
  → structured dict with all metrics
  → GPT-5.2 writes 1-page narrative (system prompt: "you're a plant engineer")
  → GPT-5.2 researches fixes (system prompt: "you're a reliability engineer, here are the top failures, suggest root causes and fixes")
  → fpdf2 renders PDF
  → save/deliver
```

### What the parsers need to handle

MES exports come in two flavors:
- **Event Overview**: columns include EventID, StartDateTimeOffset, EndDateTimeOffset, DurationSeconds, SystemName (line), EventCategoryName (equipment), EventDefinitionName (event type), OeeEventTypeName (loss type), Notes
- **OEE Overview**: columns include timestamp, line, availability, performance, quality, OEE, MTBF, MTTR, units, downtime

The parsers from Vigil (`event_parser.py` and `oee_parser.py`) are solid and battle-tested on 170K+ events. **Reuse them.** They're ~600 lines total with caching, normalization, and error handling. Don't rewrite.

### Equipment normalization matters

Raw equipment names like "Caser Disch Rail Jam" and "Caser Tipped Product" both normalize to "caser" for rollup purposes, but the raw names are what the PM recognizes. Keep both: normalized for grouping, raw for display.

### Shift definitions

- 1st: 07:00–15:00
- 2nd: 15:00–23:00
- 3rd: 23:00–07:00

These should be configurable but default to the above.

### The LLM prompts that work

**Analysis narrative (proven):**
```
You are a plant engineer writing a concise production brief for your plant manager.
Rules:
- Answer directly. Be blunt. Every claim cites a number.
- Name equipment, shifts, rates. No filler.
- ONE recommendation. End with caveats (1-2 sentences).
- Plain text only. No markdown. ~400 words max.
Format: VERDICT / EVIDENCE / RECOMMENDATION / CAVEAT
```

**Root cause research (proven):**
```
You are a reliability engineer analyzing equipment failure data from a canned food production line.
For each failure mode below, provide:
1. What this failure likely means mechanically
2. Top 3 probable root causes
3. Specific corrective actions (what to inspect, replace, adjust)
4. Preventive maintenance additions
Be specific to canning/packaging equipment. No generic advice.
```

### Search enhances the fixes

AgentSearch (localhost:3939) can pull equipment manufacturer resources, troubleshooting guides, and PM checklists. The agent should search for the top 2-3 failure modes and incorporate what it finds into the fixes section. This is what separated my analysis today from a pure data dump — I looked up what "discharge rail jam" actually means mechanically and how to fix it.

### Caching saves money

Same data + same question = same output. Hash the analysis metrics, cache the LLM response. Don't pay twice.

## 6. What are the pieces?

### Piece A: Data Loader
- Takes a directory path containing Excel files
- Separates into event files and OEE files (by filename pattern or column detection)
- Calls existing parsers (`parse_event_file`, `parse_oee_file`)
- Returns typed lists: `list[DowntimeEvent]`, `list[OEEInterval]`
- **Reuse Vigil's parsers directly** — copy `event_parser.py`, `oee_parser.py`, and their dependencies into this project

### Piece B: Analysis Engine
- Takes parsed events + OEE intervals
- Computes all metrics as a flat dict:
  - `total_events`, `total_downtime_hours`, `date_range`
  - `equipment_profiles`: list of {name, raw_name, count, hours, mtbf_min, repeat_rate, avg_duration_min, by_shift: {shift: {count, hours}}}
  - `shift_profiles`: list of {shift, avg_oee, event_count, hours, unassigned_rate, startup_penalty}
  - `trends`: list of {metric, monthly_values, direction}
  - `signal_scores`: {machine, crew, oversight} (internal, never displayed)
- Pure pandas. No LLM. No agents. Deterministic.
- **~200 lines**

### Piece C: Narrative Generator
- Takes analysis dict + question string
- Serializes metrics into structured text
- Calls GPT-5.2 with plant-engineer system prompt
- Parses response into verdict/evidence/recommendation/caveat
- Caches by content hash
- **~100 lines**

### Piece D: Fix Researcher  
- Takes top 3 equipment profiles (by downtime hours)
- For each: searches AgentSearch for "{equipment_raw_name} troubleshooting root cause fix"
- Feeds search snippets + failure data to GPT-5.2 with reliability-engineer prompt
- Returns structured fixes: {equipment, likely_cause, root_causes[], corrective_actions[], pm_additions[]}
- Caches by equipment + failure pattern hash
- **~100 lines**

### Piece E: PDF Renderer
- Takes narrative + fixes → 2-page PDF
- Page 1: Production Analysis (verdict, evidence, recommendation, caveat)
- Page 2: Root Cause & Fixes (top 3 equipment with specific actions)
- DejaVu fonts, clean layout, blue headers
- **~100 lines**

### Piece F: Runner
- CLI: `analyst run /path/to/data/ --question "..." --output /path/to/output/`
- File watcher mode: `analyst watch /path/to/inbox/ --output /path/to/reports/`
- OpenClaw skill mode: triggered by cron or heartbeat when new files appear
- **~50 lines**

**Total: ~550 lines + ~600 lines of reused parsers = ~1,150 lines**

Compare to Vigil: 23,693 lines. This does more.

## 7. What's the hard part?

**Piece D: Fix Researcher.** Getting useful, specific fixes from search + LLM.

The analysis (Piece B) is straightforward math. The narrative (Piece C) is a solved prompt. The PDF (Piece E) is boilerplate. The runner (Piece F) is trivial.

The fix researcher has to:
1. Search for the right terms (not too broad, not too narrow)
2. Read search results and extract actionable maintenance knowledge
3. Connect the search findings to the specific failure data (e.g., "your rail jam happens 3.5x more on 1st shift at higher throughput — this suggests speed-related mechanical stress, not wear")
4. Produce fixes that a maintenance tech can actually execute

This is where domain knowledge + search + LLM interpretation intersect. It's also what made today's analysis valuable — not just "the caser is broken" but "here's specifically what to check and why."

The mitigation: seed the LLM with domain context (canned food packaging, common equipment types, standard PM practices). The system prompt carries the domain knowledge. Search fills in equipment-specific details.

---

## Acceptance Criteria

1. `analyst run /path/to/line_1/ --question "Is Line 1's problem machine, man, or supervisor?"` produces a 2-page PDF
2. Page 1 matches quality of the GPT-5.2 narrative produced today (specific equipment, shifts, numbers)
3. Page 2 contains specific root causes and fixes for top 3 equipment, not generic advice
4. Total execution time < 3 minutes (including LLM calls and search)
5. Zero configuration required — works with just an OpenAI API key and AgentSearch running
6. Codebase is under 1,200 lines (excluding reused parsers)
7. No frameworks, no agent pipelines, no entity models, no event buses
8. Cached results return in < 5 seconds

## Tech Stack

- Python 3.12
- pandas (analysis)
- openpyxl (Excel parsing)
- fpdf2 (PDF generation)
- openai (GPT-5.2 narrative + fix research)
- requests (AgentSearch API)
- No other dependencies

## File Structure

```
manufacturing-analyst/
├── SKILL.md              # OpenClaw skill definition
├── SPEC.md               # This file
├── analyst/
│   ├── __init__.py
│   ├── __main__.py        # CLI entry point (Piece F)
│   ├── loader.py          # Data loading (Piece A)
│   ├── engine.py          # Analysis computations (Piece B)
│   ├── narrative.py       # LLM narrative generation (Piece C)
│   ├── researcher.py      # Fix research via search + LLM (Piece D)
│   ├── renderer.py        # PDF output (Piece E)
│   └── parsers/           # Copied from Vigil
│       ├── event_parser.py
│       ├── oee_parser.py
│       └── utils.py
└── tests/
    └── test_engine.py     # Analysis engine unit tests
```

## Not In Scope (v1)

- Multi-line comparison (one line per report)
- Historical trending across multiple runs
- Email/Slack delivery (add later as skill enhancement)
- Web UI or dashboard
- User authentication
- Database storage
- Anything that isn't "data in, insight out"

## Future (v2+, only if v1 works)

- Auto-detect file type and line from column headers
- Multi-line comparison report
- Trend tracking across weekly runs
- Delivery to email/Teams/Slack
- Integration with live MES data feeds (replace file drops)
- Custom equipment dictionaries per plant
