"""Piece D: Fix Researcher — search + GPT-5.2 for root causes and fixes."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import requests

from .engine import EquipmentProfile
from .models import get_model, get_reasoning_effort

CACHE_DIR = Path.home() / ".analyst" / "cache"
SEARCH_URL = "http://localhost:3939/search"

RESEARCH_PROMPT = """\
You are a reliability engineer analyzing equipment failure data from a food/beverage production line (canning, packaging). For each failure mode below, provide specific, actionable analysis.

Rules:
- Be specific to the equipment type. No generic advice like "improve maintenance practices."
- Name specific parts, adjustments, and inspections.
- If shift variation exists, explain what it likely indicates mechanically.
- NO markdown. Plain text only. No asterisks, no bullets, no headers.
- Keep each equipment section to ~100 words.

For each equipment failure, provide:
EQUIPMENT: [name]
LIKELY CAUSE: [1-2 sentences on what this failure mode means mechanically]
ROOT CAUSES: [3 specific probable causes, numbered]
FIXES: [3 specific corrective actions, numbered]
PM ADDITIONS: [2-3 preventive maintenance items to add]
---"""


@dataclass(slots=True)
class EquipmentFix:
    equipment_name: str
    likely_cause: str
    root_causes: list[str]
    fixes: list[str]
    pm_additions: list[str]
    search_sources: list[str] = field(default_factory=list)


def research_fixes(
    top_equipment: list[EquipmentProfile], max_items: int = 3
) -> list[EquipmentFix]:
    """Research fixes for top equipment loss drivers."""
    items = top_equipment[:max_items]
    if not items:
        return []

    cache_key = _cache_key(items)
    cached = _load_cache(cache_key)
    if cached is not None:
        print("[cached] fixes", file=sys.stderr)
        return cached

    # Search for each equipment
    search_context: list[str] = []
    all_sources: dict[str, list[str]] = {}
    for ep in items:
        snippets, sources = _search_equipment(ep.equipment_raw_name)
        search_context.append(
            f"Equipment: {ep.equipment_raw_name}\n"
            f"Events: {ep.event_count}, Downtime: {ep.total_downtime_hours:.1f}h, "
            f"MTBF: {ep.mtbf_minutes:.1f} min, Repeat rate: {ep.repeat_failure_rate:.1%}\n"
            f"Shift breakdown: {_shift_summary(ep)}\n"
            f"Industry context:\n{snippets}\n"
        )
        all_sources[ep.equipment_raw_name] = sources

    # Call LLM
    api_key = _get_api_key()
    if not api_key:
        print("[no-api-key] Set OPENAI_API_KEY for fix research — skipping (no fallback)", file=sys.stderr)
        return []

    try:
        prompt = "\n---\n".join(search_context)
        raw = _call_llm(prompt, api_key)
        print(f"[llm-raw] fixes response length: {len(raw)}", file=sys.stderr)
        fixes = _parse_fixes(raw, items, all_sources)
        if not fixes:
            print("[llm-parse-warn] parser returned nothing, raw starts: {raw[:200]}", file=sys.stderr)
            return []
        _save_cache(cache_key, fixes)
        print("[llm] fixes", file=sys.stderr)
        return fixes
    except Exception as exc:
        print(f"[llm-error] fixes: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        return []


def _search_equipment(raw_name: str) -> tuple[str, list[str]]:
    """Search AgentSearch for equipment troubleshooting info."""
    # Clean up the name for search
    clean = re.sub(r'[^a-zA-Z0-9 ]', ' ', raw_name).strip()
    queries = [
        f"{clean} troubleshooting root cause fix",
        f"{clean} preventive maintenance checklist packaging line",
    ]
    snippets: list[str] = []
    sources: list[str] = []

    for query in queries:
        try:
            resp = requests.get(SEARCH_URL, params={"q": query, "count": 3}, timeout=10)
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                for r in results[:3]:
                    title = r.get("title", "")
                    snippet = r.get("snippet", "")
                    url = r.get("url", "")
                    if snippet:
                        snippets.append(f"- {title}: {snippet}")
                    if url:
                        sources.append(url)
        except Exception:
            pass

    return "\n".join(snippets[:6]) if snippets else "No search results available.", sources[:4]


def _shift_summary(ep: EquipmentProfile) -> str:
    parts = []
    for shift in ("1st", "2nd", "3rd"):
        data = ep.by_shift.get(shift, {})
        count = data.get("count", 0)
        hours = data.get("hours", 0.0)
        if count > 0:
            parts.append(f"{shift}: {count} events, {hours:.1f}h")
    return "; ".join(parts)


def _parse_fixes(
    text: str, items: list[EquipmentProfile], sources: dict[str, list[str]]
) -> list[EquipmentFix]:
    """Parse LLM response into structured fixes."""
    # Strip markdown
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)

    fixes: list[EquipmentFix] = []
    current_equip = ""
    current: dict[str, str | list[str]] = {}

    def _flush():
        if current_equip and current:
            fixes.append(EquipmentFix(
                equipment_name=current_equip,
                likely_cause=str(current.get("likely_cause", "")),
                root_causes=_extract_numbered(str(current.get("root_causes", ""))),
                fixes=_extract_numbered(str(current.get("fixes", ""))),
                pm_additions=_extract_numbered(str(current.get("pm_additions", ""))),
                search_sources=sources.get(current_equip, []),
            ))

    for line in text.splitlines():
        s = line.strip()
        if s.upper().startswith("EQUIPMENT:"):
            _flush()
            current_equip = s[len("EQUIPMENT:"):].strip()
            current = {}
        elif s.upper().startswith("LIKELY CAUSE:"):
            current["likely_cause"] = s[len("LIKELY CAUSE:"):].strip()
        elif s.upper().startswith("ROOT CAUSES:"):
            current["root_causes"] = s[len("ROOT CAUSES:"):].strip()
        elif s.upper().startswith("FIXES:"):
            current["fixes"] = s[len("FIXES:"):].strip()
        elif s.upper().startswith("PM ADDITIONS:"):
            current["pm_additions"] = s[len("PM ADDITIONS:"):].strip()
        elif s and current:
            # Append to last section
            last_key = list(current.keys())[-1] if current else None
            if last_key:
                current[last_key] = str(current[last_key]) + " " + s

    _flush()

    return fixes


def _extract_numbered(text: str) -> list[str]:
    """Extract numbered items from text like '1. First 2. Second 3. Third'"""
    items = re.split(r'\d+\.\s+', text)
    return [item.strip() for item in items if item.strip()]


def _call_llm(prompt: str, api_key: str) -> str:
    from openai import OpenAI
    model = get_model("research")
    effort = get_reasoning_effort("research")

    client = OpenAI(api_key=api_key)
    # Reasoning models (gpt-5 family) burn tokens on invisible thinking.
    # gpt-5 at medium effort needs ~2000 reasoning + ~500 output = ~4000 safe.
    # Non-reasoning models just need output tokens.
    is_reasoning = effort is not None
    max_tokens = 3000 if is_reasoning else 2000

    kwargs: dict = {
        "model": model,
        "max_completion_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": RESEARCH_PROMPT},
            {"role": "user", "content": prompt},
        ],
    }
    if is_reasoning:
        kwargs["reasoning_effort"] = effort
    else:
        kwargs["temperature"] = 0.3
    response = client.chat.completions.create(**kwargs)
    return response.choices[0].message.content or ""


def _get_api_key() -> str | None:
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key.strip()
    for path in [
        Path.home() / ".openclaw" / "auth" / "openai",
        Path.home() / ".openclaw" / ".env",
    ]:
        if path.is_file():
            text = path.read_text().strip()
            for line in text.splitlines():
                if line.startswith("OPENAI_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
            if text.startswith("sk-"):
                return text
    return None


def _cache_key(items: list[EquipmentProfile]) -> str:
    blob = "|".join(
        f"{ep.equipment_raw_name}:{ep.event_count}:{ep.total_downtime_hours:.0f}"
        for ep in items
    )
    return hashlib.sha256(blob.encode()).hexdigest()


def _load_cache(key: str) -> list[EquipmentFix] | None:
    path = CACHE_DIR / f"fixes_{key}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
        return [
            EquipmentFix(
                equipment_name=f["equipment_name"],
                likely_cause=f["likely_cause"],
                root_causes=f["root_causes"],
                fixes=f["fixes"],
                pm_additions=f["pm_additions"],
                search_sources=f.get("search_sources", []),
            )
            for f in data["fixes"]
        ]
    except (KeyError, json.JSONDecodeError):
        return None


def _save_cache(key: str, fixes: list[EquipmentFix]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "fixes": [
            {
                "equipment_name": f.equipment_name,
                "likely_cause": f.likely_cause,
                "root_causes": f.root_causes,
                "fixes": f.fixes,
                "pm_additions": f.pm_additions,
                "search_sources": f.search_sources,
            }
            for f in fixes
        ],
        "model": get_model("research"),
        "created": datetime.now(timezone.utc).isoformat(),
    }
    (CACHE_DIR / f"fixes_{key}.json").write_text(json.dumps(data, indent=2))


def _fallback_fix(ep: EquipmentProfile) -> EquipmentFix:
    return EquipmentFix(
        equipment_name=ep.equipment_raw_name,
        likely_cause=f"Chronic failure mode: {ep.event_count} events, {ep.total_downtime_hours:.1f}h downtime.",
        root_causes=["Mechanical wear", "Speed/timing mismatch", "Inadequate PM interval"],
        fixes=["Full mechanical inspection", "Speed audit at all transfer points", "Replace worn consumables"],
        pm_additions=["Add to daily startup checklist", "Weekly inspection of wear components"],
    )
