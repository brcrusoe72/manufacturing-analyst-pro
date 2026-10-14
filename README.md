# Manufacturing Analyst Pro

Prototype Streamlit application and Python CLI for exploring manufacturing event and
OEE exports, calculating equipment/shift metrics, and generating narrative/PDF reports.

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Model-generated narratives require an `OPENAI_API_KEY` in the server environment.
Review `analyst/__main__.py` for the CLI options. Supported input paths include MES
event/OEE exports and generic CSV/Excel; compatibility depends on column names,
units, timestamps, and equipment identifiers. Test a representative fixture first.

## Data handling

The web loader reads uploaded files in memory, and Streamlit retains result/session
state while the session runs. `analyst/narrative.py` sends analysis context to OpenAI.
Optional research calls can send equipment queries to external services and write
local caches. The CLI uses `analyst/memory.py` to save findings under `memory/findings`.
The web path does not establish that this CLI history is used across uploads.

Therefore this project does **not** offer a blanket no-storage/no-sharing guarantee.
Configure retention and provider access before using confidential data. Removing a
browser upload is not proof that every derived report, cache, or provider record was deleted.

## Interpretation and status

Metrics describe the supplied dataset. Suggested causes and corrective actions need
plant evidence and operator review; correlations alone do not establish root cause.
Runtime depends on input size and provider latency, so no fixed three-minute guarantee
is made. Pricing and Pro UI elements are not proof of a working paid subscription.

The 2026-10-13 audit reviewed source and corrected inaccurate documentation/privacy
copy. A live customer deployment and model-backed report were not certified.
Maintained by Brian Crusoe.
