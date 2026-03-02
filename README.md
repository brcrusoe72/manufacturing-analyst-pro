# 🏭 Manufacturing Analyst Pro

**Your production data is telling you where you're bleeding money. You're not hearing it.**

Upload your MES downtime exports, OEE reports, or any CSV with equipment & duration data. Get an intelligent analysis report in under 3 minutes — written like a senior plant engineer, not a dashboard.

## What It Does

- **Reads your data like an engineer** — names specific equipment, specific shifts, specific numbers
- **One clear recommendation** — the single highest-leverage fix
- **Root cause analysis** (Pro) — specific corrective actions for your top 3 equipment issues
- **Memory** (Pro) — tracks whether your fixes are working across uploads
- **Zero data storage** — processed in memory, immediately discarded

## Supported Formats

- Traksys MES Event Overview & OEE Overview exports
- Generic CSV/Excel with columns like: date, equipment/machine, duration
- Multiple files (event + OEE together)

## Quick Start

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Built By

A production supervisor with 8+ years in food manufacturing, Six Sigma Black Belt, and deep MES/Traksys experience. This tool exists because every OEE software shows dashboards — none of them tell you what the numbers mean.

## Privacy

Your data is processed in memory and immediately discarded. Nothing is stored, logged, or shared. Ever.
