# SPEC: Manufacturing Analyst Pro — Web Product

_The engineer who reads your data. Ship it._

Built using Nate B. Jones's Prompt 0 Framework (7 questions before touching AI).

---

## Question 1: What am I actually trying to accomplish?

A web application where any plant manager, CI engineer, or production supervisor can upload their MES/downtime/OEE data and get back an intelligent analysis report — the kind that takes a senior plant engineer half a day to produce — in under 3 minutes. No account required. No data stored. No software deployment.

The goal is not another dashboard. Every OEE tool on the market shows numbers. This one READS numbers and tells you what they mean: what's costing you the most, why, what to fix first, and whether it's getting better or worse.

This is the manufacturing-analyst skill (3,567 LOC, $0.15/report, proven on 170K+ real MES events) wrapped in a Streamlit interface and deployed to the web.

**The business outcome:** Recurring SaaS revenue from Pro subscribers ($99-149/mo) with consulting upsell for plants that want hands-on help implementing the recommendations.

---

## Question 2: Why does this matter?

Three reasons:

**For the user:** 92% of manufacturers say their tech investments haven't delivered (PwC 2025). The #1 reason is data issues — they have the data, they can't interpret it. Plants are sitting on Excel exports full of answers they can't read. A 5-minute upload that produces an actionable insight report saves them a half-day of engineering time per analysis, or the $5-50K they'd pay a consulting firm.

**For the market:** Manufacturing analytics is an $11B market growing 16% annually. OEE software is commoditized — everyone has dashboards. Nobody has interpretation. The gap is "the engineer who reads your data." That's what this product IS.

**For Bri:** This is the path from employed-to-employer. Expert network calls pay $200-500/hr but don't compound. A SaaS product with 37 subscribers at $149/mo = $5.5K/mo recurring revenue that grows while you sleep. The tool sells the consulting. The consulting validates the tool. The flywheel turns.

---

## Question 3: What does "done" look like?

A user lands on the site. They see:

> "Your production data is telling you where you're bleeding money. You're not hearing it."
> [Upload your data →]

They drag in their Excel files (event exports, OEE exports, or generic CSVs with timestamp/equipment/duration columns). They click Analyze. In under 3 minutes, they get:

### Free Tier Output
- 1-page narrative analysis: what's wrong, how bad it is, what's the #1 thing to fix
- Written in Buffett-letter style — flowing prose, not bullet dumps
- Enough to produce the "holy shit, how did it know that?" moment
- PDF download

### Pro Tier Output ($99-149/mo)
Everything in Free, plus:
- Full 2-3 page report with root cause analysis and specific corrective actions for top 3 equipment loss drivers
- Shift/crew/line breakdown with cross-shift ratio analysis
- Trend detection (improving/worsening/stable) across the data window
- Equipment MTBF, repeat failure rate, shift-specific patterns
- Memory across uploads: "Last time you uploaded data for this line, we recommended X. Since then, Y has improved/worsened."
- Unlimited reports per month
- Reports branded with their company name (optional)
- CSV/JSON export of raw analysis metrics

### Enterprise Tier Output ($499/mo)
Everything in Pro, plus:
- API access (POST /analyze with file, GET /report/{id})
- Multi-line comparison in a single report
- Custom equipment dictionaries (map their equipment names to standard categories)
- Custom shift definitions
- Webhook delivery (report auto-sent to email/Teams/Slack when processing completes)
- Priority support from Bri (the human who built it and has run the lines)

### "Done" Acceptance Criteria
1. A first-time user with zero configuration can upload an Excel file and get a PDF report in under 3 minutes
2. The narrative quality matches or exceeds the Line 1 analysis produced on 2026-02-28 (specific equipment names, shift numbers, MTBF, repeat rates, crew signals, one clear recommendation)
3. The site loads in under 2 seconds
4. Data is processed in memory and never written to disk or logged
5. Free tier is genuinely useful — not a crippled teaser, a real analysis
6. Pro tier demonstrates clear incremental value (fixes, memory, trends) that justifies $99-149/mo
7. Stripe payment works — user can go from free to paid in under 60 seconds
8. Works with: Traksys exports, SAP exports, generic CSV (timestamp, equipment/reason, duration)
9. Mobile-responsive (plant managers check things on their phones)

---

## Question 4: What does "wrong" look like?

This is the most important question. Every failure mode of Vigil and OIA lives here.

### Product-Level Wrong
- ❌ **Requires configuration before first use.** If someone has to set shift times, map equipment names, or define KPIs before seeing a result, they'll leave. Zero-config or die.
- ❌ **Produces generic output.** "Improve your maintenance practices" or "OEE is below world-class benchmark" — anything a ChatGPT prompt could generate without the data. The output must name specific equipment, specific shifts, specific numbers, specific actions.
- ❌ **Feels like a dashboard.** Tables and charts without interpretation. The whole point is that this is NOT another dashboard. It's the engineer who reads the dashboard and tells you what it means.
- ❌ **Stores user data.** Even accidentally. Even in logs. Even in error reports. If a plant manager's production data shows up anywhere after they close the tab, trust is destroyed permanently. Manufacturing data is competitive intelligence.
- ❌ **Takes more than 3 minutes.** Plant managers have the attention span of goldfish with urgent emails. If the spinner spins for 5 minutes, they close the tab and never come back.
- ❌ **Requires a specific file format.** "Export from Traksys in this exact format" = 90% of the market can't use it. Must handle messy real-world data: different column names, mixed date formats, extra columns, missing values.

### Engineering-Level Wrong
- ❌ **Exceeds 5,000 LOC total (including Streamlit wrapper).** The core is 3,567 lines and does everything. The web layer should be thin. If the total crosses 5K, we're bloating.
- ❌ **Adds dependencies beyond the current stack + Streamlit.** Python, pandas, openpyxl, fpdf2, openai, requests, streamlit. That's it. No ORMs, no auth frameworks, no CSS libraries, no React frontends.
- ❌ **Builds user management from scratch.** Use Stripe for payment gating + Streamlit's session state. Don't build a user database, password reset flow, or email verification system.
- ❌ **Tries to be real-time.** This is batch analysis. User uploads a file, gets a report. Not a live connection to their MES. That's v3 at the earliest.
- ❌ **Over-engineers the landing page.** A clean Streamlit app with good copy IS the landing page. Don't build a separate marketing site with a separate tech stack.

### Business-Level Wrong
- ❌ **Ships without a way to collect money.** A free tool with no payment path is a hobby, not a business. Stripe integration is part of v1, not v2.
- ❌ **Launches without one real testimonial/case study.** The free-tier diagnostic for an ex-colleague must happen BEFORE public launch. One anonymized case study on the landing page.
- ❌ **Prices too low.** $19/mo signals "toy." $99-149/mo signals "professional tool that saves me real money." The analysis replaces $5-50K of consulting. Price accordingly.
- ❌ **Gives away the Pro output for free.** The free tier must create desire for Pro, not satisfy it. Narrative analysis = free. Root causes + fixes + memory = paid.

---

## Question 5: What do I already know that I haven't written down?

### About the users
- **Plant managers don't read reports longer than 1 page.** The narrative must fit on one page. Data tables go on page 2. Fixes on page 3. They'll read page 1 and skim the rest.
- **"Unassigned" and "Not Scheduled" confuse everyone.** Most OEE tools lump all downtime together. Separating equipment losses from coding/supervision losses is a differentiator. The current engine already does this.
- **Reason codes are manually entered and messy.** Operators type free-text or pick from dropdown menus that don't match actual failure modes. The tool must normalize without losing the original text. The current parsers handle this.
- **Every plant thinks they're unique.** They're not. Casing machines jam everywhere. Labelers drift everywhere. Depalletizers fault everywhere. The equipment patterns are 80% universal across food manufacturing. The 20% that's unique is what makes the analysis valuable — but the foundation is shared.
- **Trust is earned by being specific and being right.** The first report must name equipment they recognize, cite numbers they can verify, and make a recommendation they hadn't considered. If the first report is generic, there's no second report.
- **IT departments block things.** Many plants run on locked-down networks. A web app that works in a browser with no install is the only path. Desktop software is dead for this market.

### About the data
- **Traksys exports are the most structured.** Clean column names, consistent date formats, proper event/OEE separation. The current parsers are battle-tested on these.
- **SAP exports are a mess.** Different column names per module, merged cells, subtotals mixed with data rows. Will need a dedicated parser.
- **Generic CSVs are the universal fallback.** Any plant can export *something* with timestamps, equipment names, and durations. A flexible CSV parser with column auto-detection covers 70% of the market that doesn't use Traksys or SAP.
- **OEE data is optional.** Many plants only track downtime events, not hourly OEE. The analysis must work with events-only (downtime analysis, MTBF, repeat rates, shift patterns) and add OEE layer when available.
- **Date formats are chaos.** US (MM/DD/YYYY), ISO (YYYY-MM-DD), European (DD/MM/YYYY), Excel serial numbers, timezone-aware, timezone-naive. The parser must handle all of them.

### About the competition
- **Excellerant, PerformOEE, MachineMetrics, Tulip** — all sell dashboards + hardware (sensors, IoT). Starting price $500-2,000/mo. They require installation, configuration, sometimes physical sensors on machines. Months to deploy.
- **Vorne XL** — hardware OEE display. $5,000+ per machine. Shows real-time OEE on the floor. Doesn't analyze anything.
- **Tableau/Power BI** — generic BI tools. Can make OEE dashboards but require an analyst to build them. No domain knowledge built in.
- **None of them write narratives.** Not one. They all show charts and expect the user to interpret them. That's the gap. "The engineer who reads your data" doesn't exist as a product.

### About the tech
- **The LLM call is the bottleneck and the moat.** Pandas analysis runs in seconds. The LLM narrative takes 30-90 seconds. This is also what makes the product defensible — the system prompt encodes 15 years of plant engineering knowledge. A competitor would need to replicate the domain expertise, not just the code.
- **Caching is critical for economics.** Same data + same question = same report. At $0.15/report, 1,000 free-tier users running 3 reports/month = $450/mo in LLM costs. Caching cuts this by 60-80% (users often re-upload the same data while testing).
- **Streamlit handles auth poorly.** No built-in user management. Options: (a) Stripe Checkout → session cookie, (b) Streamlit Community Cloud auth (limited), (c) OAuth via Google/Microsoft. Simplest: gated by a "Pro key" — user buys on Stripe, gets a key, enters it in the app.

---

## Question 6: What are the pieces?

### The Value Chain
```
User's Excel file → Upload widget → Format detection → Parsing → Analysis engine → LLM narrative → LLM fixes (Pro) → PDF render → Download
```

Everything serves this chain. Anything that doesn't is overhead.

### Piece 1: Smart File Intake (NEW — ~200 lines)
**What it does:** Accepts uploaded files, auto-detects format, routes to the right parser.

Formats to support:
- **Traksys Event Overview** — detected by column names: EventID, SystemName, EventCategoryName, DurationSeconds
- **Traksys OEE Overview** — detected by column names: OEE, Availability, Performance, Quality + timestamp
- **Generic Downtime CSV** — auto-map columns by fuzzy header matching:
  - Timestamp: "date", "time", "datetime", "start", "timestamp", "start_time", "StartDateTimeOffset"
  - Equipment: "equipment", "machine", "asset", "system", "EventCategoryName", "reason", "cause"
  - Duration: "duration", "minutes", "seconds", "hours", "DurationSeconds", "downtime"
  - Category: "type", "category", "loss_type", "OeeEventTypeName" (optional)
  - Line: "line", "area", "cell", "SystemName" (optional)
- **SAP PM Export** — detected by SAP-specific columns: AUFNR, EQUNR, FUNKT, AUSZT (v1.1, not v1.0)

Auto-detection algorithm:
1. Read first 5 rows + all column headers
2. Score each format by column name matches (exact + fuzzy)
3. Pick highest-scoring format
4. If no format scores above threshold: show user a column-mapping UI (Streamlit selectboxes)

**Depends on:** Existing parsers (event_parser.py, oee_parser.py) + new generic_parser.py
**Output:** `list[DowntimeEvent]`, `list[OEEInterval]`

### Piece 2: Analysis Engine (EXISTS — engine.py, ~260 lines)
**What it does:** Pure pandas computation. No changes needed for web deployment.
- Equipment profiles with MTBF, repeat rates, shift breakdown
- Shift profiles with OEE, unassigned rates, startup penalties, cross-shift patterns
- Trend detection
- Signal scores (internal)

**Status:** Complete. Battle-tested on 170K events.

### Piece 3: Narrative Generator (EXISTS — narrative.py, ~300 lines)
**What it does:** Serializes analysis → sends to GPT-5.2 → parses response into structured narrative.

**Changes for web:**
- Remove file-system cache dependency → use in-memory cache (dict) for session duration
- Add option to NOT load prior findings (web users don't have persistent memory on free tier)
- Pro tier: memory keyed by Stripe customer ID → findings persist across sessions

**Status:** Complete. Prompt is proven.

### Piece 4: Fix Researcher (EXISTS — researcher.py, ~280 lines)
**What it does:** Searches AgentSearch for equipment troubleshooting → feeds to GPT-5-mini → structures root causes and fixes.

**Changes for web:**
- **CRITICAL:** AgentSearch runs on localhost:3939. Web deployment can't reach localhost.
- Options: (a) Deploy AgentSearch alongside the app, (b) Use a public search API as fallback, (c) Build a static equipment knowledge base that ships with the app
- **Recommended: Option (c) for v1.** Build a curated KB of common food/packaging equipment failure modes and fixes. Covers 80% of cases. Add live search in v1.1.
- This is the Pro-tier gate: free gets narrative only, Pro gets fixes.

**Status:** Works locally. Needs search architecture decision for web.

### Piece 5: PDF Renderer (EXISTS — renderer.py, ~250 lines)
**What it does:** Renders analysis + narrative + fixes into a clean PDF.

**Changes for web:**
- Output to BytesIO instead of file path (for Streamlit download button)
- Add optional company name/logo to header (Pro tier)
- Ensure DejaVu fonts are bundled in deployment (not system-dependent)

**Status:** Complete. Minor adaptation needed.

### Piece 6: Memory System (EXISTS — memory.py, ~130 lines)
**What it does:** Saves findings after each run, loads prior findings for comparison.

**Changes for web:**
- Free tier: no memory (each upload is standalone)
- Pro tier: memory stored server-side, keyed by customer ID
- Storage: SQLite file or simple JSON directory (not a database server)
- Memory enables the killer feature: "Last month you uploaded Line 1 data. OEE was 18.3%. This month it's 21.1%. The caser improvements are working."

**Status:** Complete for local use. Needs persistence layer for web.

### Piece 7: Streamlit Web App (NEW — ~300-400 lines)
**What it does:** The entire user-facing interface.

```
app.py (main)
├── Landing section (above the fold)
│   ├── Headline + subhead
│   ├── Upload widget
│   └── "How it works" (3 steps)
├── Analysis section (appears after upload)
│   ├── File detection feedback ("Detected: Traksys Event Overview, 46,064 events")
│   ├── Progress bar during analysis
│   ├── Narrative preview (rendered in-page)
│   ├── PDF download button
│   └── Pro upsell (if free tier): "Want root causes and fixes? → Upgrade to Pro"
├── Pro section (if authenticated)
│   ├── Full report with fixes
│   ├── Upload history / memory
│   └── Settings (company name, shift times)
└── Footer
    ├── Privacy: "Your data is processed in memory and immediately discarded"
    ├── About / Contact
    └── Stripe-powered pricing
```

**Key UX decisions:**
- Single page. No navigation. Upload → result → download. That's it.
- File upload at the TOP, not behind a "Get Started" button
- Progress feedback during LLM call ("Analyzing equipment patterns... Generating narrative... Researching fixes...")
- PDF preview AND download — show the narrative on-screen, offer PDF for sharing
- Pricing section BELOW the free result — let them see value before asking for money

### Piece 8: Payment Gate (NEW — ~100 lines)
**What it does:** Stripe Checkout integration for Pro/Enterprise subscriptions.

Flow:
1. User clicks "Upgrade to Pro"
2. Redirect to Stripe Checkout (hosted by Stripe — no payment form to build)
3. On success: Stripe webhook sets a session cookie with customer ID
4. App checks cookie → unlocks Pro features
5. Stripe Customer Portal link for managing subscription

**Implementation:**
- `stripe` Python package
- Stripe Checkout Session (hosted)
- Webhook endpoint for payment confirmation
- Session state stores `pro_customer_id`
- No user database. Stripe IS the user database.

### Piece 9: Static Equipment KB (NEW — ~1 file, curated)
**What it does:** Ships a JSON file of common food/packaging equipment failure modes, root causes, and fixes. Replaces live AgentSearch for web deployment.

Contents:
- 30-50 equipment categories (caser, labeler, depalletizer, filler, seamer, wrapper, conveyor, palletizer, etc.)
- Per category: 3-5 common failure modes, probable root causes, standard corrective actions, PM recommendations
- Sourced from: Bri's domain knowledge + the existing KB + industry maintenance guides

**Why this works:** The LLM already gets the equipment data from the analysis engine. The static KB gives it domain context. The combination produces specific fixes without needing live search.

**Pro tier enhancement (v1.1):** Add live search back via a hosted search API for equipment-specific troubleshooting beyond the static KB.

### Piece 10: Deployment Config (NEW — ~50 lines)
- `requirements.txt` (locked versions)
- `Dockerfile` (for self-hosted option)
- Streamlit Cloud config (`.streamlit/config.toml`)
- Environment variables: `OPENAI_API_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`

---

## Question 7: What's the hard part?

Three hard problems, in order:

### Hard Problem 1: Generic File Parsing (Medium — 2-3 days)
The current parsers are built for Traksys. Handling arbitrary CSV/Excel files with different column names, date formats, and structures is the biggest technical risk.

**Why it's hard:** There are infinite ways to format a downtime log. Column names vary ("Equipment" vs "Machine" vs "Asset" vs "Reason Code"). Dates vary. Some files have subtotals. Some have merged cells. Some have multiple sheets with different structures.

**Mitigation:**
- Fuzzy column matching with confidence scores (not exact match)
- Fallback to user-assisted mapping via Streamlit selectboxes
- Start with the 3 most common formats (Traksys, generic CSV, Excel with headers)
- Add formats based on actual user uploads (log which formats fail)

**Acceptance criteria:** Upload a generic CSV with columns "Date, Machine, Duration_Min, Category" → get a valid analysis. Upload a Traksys export → auto-detected, no user input needed.

### Hard Problem 2: Search Architecture for Fixes (Medium — 1-2 days)
AgentSearch runs locally. Streamlit Cloud can't reach localhost. The fix researcher needs an alternative.

**Why it's hard:** The fix quality depends on search context. Without it, fixes become more generic. The static KB helps but doesn't cover equipment-specific troubleshooting guides.

**Mitigation (phased):**
- **v1.0:** Static equipment KB (covers 80%) + enhanced LLM prompt with more domain context
- **v1.1:** Deploy AgentSearch as a microservice (Docker on a $5/mo VPS) with API key auth
- **v1.2:** Let users paste equipment manual excerpts for even more specific fixes

**Acceptance criteria (v1.0):** Fix recommendations for common food/packaging equipment (caser, labeler, depal, seamer, filler) are specific enough to be actionable without live search.

### Hard Problem 3: Payment + Tier Gating Without User Management (Low — 1 day)
Streamlit doesn't have built-in auth. Building user management is scope creep.

**Why it's hard:** Need to distinguish free/Pro/Enterprise users, persist Pro memory across sessions, and handle Stripe webhooks — all without a traditional backend.

**Mitigation:**
- Stripe Checkout handles all payment UI
- "Pro Key" model: after payment, user gets a key (from Stripe metadata) they paste into the app
- Pro key unlocks features via session state
- Memory persistence: keyed by Pro key, stored as JSON files on the server
- No passwords, no email verification, no forgot-password flow

**Acceptance criteria:** User buys Pro → gets a key → enters key in app → sees full reports with fixes and memory → key works across browser sessions.

---

## Architecture Summary

```
┌─────────────────────────────────────────────┐
│              Streamlit Web App               │
│  ┌─────────┐  ┌──────────┐  ┌───────────┐  │
│  │ Upload  │→│ Detect   │→│ Parse     │  │
│  │ Widget  │  │ Format   │  │ (auto)    │  │
│  └─────────┘  └──────────┘  └─────┬─────┘  │
│                                    │         │
│  ┌─────────────────────────────────▼──────┐  │
│  │         Analysis Engine (pandas)       │  │
│  │  Equipment profiles, shifts, trends    │  │
│  └─────────────────────┬─────────────────┘  │
│                        │                     │
│         ┌──────────────┴──────────────┐      │
│         │                             │      │
│  ┌──────▼──────┐            ┌────────▼────┐ │
│  │ Narrative   │            │Fix Research │ │
│  │ (GPT-5.2)  │            │(GPT-5-mini) │ │
│  │ FREE+PRO   │            │ PRO ONLY    │ │
│  └──────┬──────┘            └──────┬──────┘ │
│         │                          │         │
│  ┌──────▼──────────────────────────▼──────┐  │
│  │           PDF Renderer (fpdf2)         │  │
│  └─────────────────────┬─────────────────┘  │
│                        │                     │
│  ┌─────────────────────▼─────────────────┐  │
│  │    Download Button + Screen Preview    │  │
│  └────────────────────────────────────────┘  │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │  Stripe Gate │ Memory (Pro) │ Privacy  │  │
│  └────────────────────────────────────────┘  │
└─────────────────────────────────────────────┘
```

---

## Build Sequence

| Phase | What | Est. Time | Depends On |
|-------|------|-----------|------------|
| **1** | Generic CSV parser + format auto-detection | 6-8 hrs | — |
| **2** | Streamlit app shell (upload → existing engine → PDF download) | 3-4 hrs | Phase 1 |
| **3** | Static equipment KB (30-50 categories, curated) | 3-4 hrs | — |
| **4** | Wire fixes to static KB instead of AgentSearch | 2-3 hrs | Phase 3 |
| **5** | Landing page copy + UX polish | 2-3 hrs | Phase 2 |
| **6** | Stripe integration (Checkout + Pro key + tier gating) | 3-4 hrs | Phase 2 |
| **7** | Memory persistence for Pro tier | 2-3 hrs | Phase 6 |
| **8** | Deploy to Streamlit Cloud + test end-to-end | 2-3 hrs | All |
| **9** | First free diagnostic for ex-colleague (case study) | 1-2 hrs | Phase 8 |
| **10** | Launch: LinkedIn post + direct outreach | 1-2 hrs | Phase 9 |

**Total: ~25-35 hours → 4-5 focused days**

Phases 1+3 can run in parallel (no dependency). Phases 2+5 can overlap. Realistic ship date: **1 week from start.**

---

## Constraints (Non-Negotiable)

1. **Total LOC ≤ 5,000** (including Streamlit wrapper, excluding tests)
2. **Zero data persistence for free tier** — process in memory, return result, discard
3. **Under 3 minutes from upload to PDF** on files up to 100K rows
4. **Works without configuration** — auto-detect everything
5. **No new frameworks** — Python + pandas + fpdf2 + openai + streamlit + stripe
6. **Privacy is the headline feature** — not buried in footer, front and center
7. **Price signals professional tool** — $99+ for Pro, not $19
8. **One page, one flow** — upload → result → download → upgrade

---

## Success Metrics (90-Day)

| Metric | Target | How Measured |
|--------|--------|-------------|
| Free reports generated | 100+ | Server logs (count only, no data) |
| Pro subscribers | 5-10 | Stripe dashboard |
| Monthly recurring revenue | $500-1,500 | Stripe |
| Report quality rating | >4/5 | Post-report feedback widget |
| Time to first report | <3 min | Client-side timer |
| Consulting leads generated | 2-3 | Contact form submissions |

---

## What's NOT In v1.0

- Multi-line comparison reports
- Live MES connections / real-time monitoring
- Mobile app
- SAP parser (v1.1)
- Team accounts / multi-user
- Custom branding beyond company name
- Email delivery of reports
- Blog / content section (LinkedIn IS the content channel)
- A/B testing, analytics, tracking pixels
- Anything that isn't "data in, insight out"

---

## The North Star

A plant manager in Arkansas gets a text from a LinkedIn connection: "Upload your downtime data to this site. Trust me." He uploads a messy Excel file from his MES. In 2 minutes, he's reading a report that names his worst equipment by name, tells him 3rd shift is recovering 26% slower than 1st, and recommends a specific PM addition for his case packer. He's never seen anything like it. He forwards the PDF to his VP of Ops. The VP calls you.

That's the product. Everything else is plumbing.
