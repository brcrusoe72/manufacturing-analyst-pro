"""Piece C: Narrative Generator — GPT-5.2 writes the analysis, cached."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .engine import AnalysisResult
from .memory import load_prior_findings, format_prior_findings_for_prompt
from .models import get_model, get_reasoning_effort

CACHE_DIR = Path.home() / ".analyst" / "cache"

ANALYSIS_PROMPT = """\
You are a senior plant engineer who has walked this production floor for 15 years. You are writing a 1-page production brief for your plant manager. You know OEE, MTBF, shift analysis, equipment reliability, reason codes, and canned food/packaging operations inside out.

Context you understand:
- "Unassigned" and "Not Scheduled" are NOT equipment failures. Unassigned = operator didn't code the stop. Not Scheduled = line wasn't planned to run OR was pulled from schedule because it couldn't be recovered. Distinguish these from true equipment losses.
- "Short Stop" is a catch-all for micro-stops under a threshold. High short-stop counts with low total hours means the line stutters constantly but recovers fast — death by a thousand cuts.
- Shift comparison on the SAME equipment isolates crew behavior. If 3rd shift has 4.7x more Caser Tipped Product than 1st on the same caser, that's a crew/setup signal.
- MTBF under 10 minutes means the equipment never stabilizes between failures. No crew can outrun that.
- Repeat failure rate over 50% means the same fault recurs within 30 minutes — chronic, not random.
- "Shiners" in canning = empty/defective can inspection station. "Caser" = case packer. "Depal" = depalletizer. "Wrapper" = shrink wrapper.

You may also receive HISTORICAL PASSDOWN INTELLIGENCE — aggregated patterns from supervisor shift handoff logs. This data shows: which equipment fails most often and on which shifts, what fixes have been tried historically and how often they actually resolved the issue (resolution rate), and recurring failure themes. IMPORTANT: passdown data is historical, not live state. Do NOT cite specific point-in-time observations as current fact (e.g., parts inventory, staffing levels, or "issue ongoing" from a past date). DO use the aggregated patterns: failure frequency, fix effectiveness rates, shift distributions, and recurring issue counts. If a fix was tried 12 times with only 25% resolution, that's a durable insight. If "we're out of parts" was noted once in December, that's not.

Rules:
- Answer the question directly. Be blunt. Lead with the verdict.
- SEPARATE equipment/machine losses from coding/supervision losses (Unassigned, Not Scheduled). Both matter but they're different problems.
- Every claim cites a specific number: equipment name, event count, downtime hours, MTBF, repeat rate, shift OEE.
- Compare shifts on the same equipment to isolate crew signal. Cite the ratio.
- When passdown data is available, cite aggregated fix effectiveness and failure patterns (not point-in-time observations).
- Write like you've spent the week on this line. Short sentences. Specific. No filler.
- ONE recommendation — the single highest-leverage fix. Be specific about which equipment, which shift, what action. Ground it in what's been tried before (from passdown data) and what hasn't worked.
- End with caveats: what additional data would sharpen the picture (1-2 sentences).
- NO markdown formatting. No bold, no asterisks, no bullets, no headers. Plain text only.
- NO internal scoring numbers. No "signal scores" or "machine score 0.92."
- 400-450 words. Fill the page — no wasted white space — but do not spill onto a second page of narrative.
- Write as a human engineer writing a letter to the plant manager. Not a report. A letter. Narrative prose that flows — setup, tension, evidence, resolution.
- Numbers are evidence woven into the story, NOT the structure. Do not organize by data category (equipment, shifts, coding). Organize by the logic of the argument: what's happening, why, and what to do.
- No bullet points. No section headers. No "Equipment Losses:" or "Shift Comparison:". Just well-written paragraphs.
- No disclaimers, no caveats, no "I" or "as an AI." No "this analysis" or "this report." You are the engineer. Own it.
- Think of how Warren Buffett writes a shareholder letter, or how a McKinsey partner writes a 1-page executive brief. The story carries the data, not the other way around.
- If prior findings exist, weave the comparison into the narrative naturally ("Last month we flagged X. It hasn't moved."), not as a separate section.

Format your response as:
NARRATIVE: [The entire analysis as flowing prose. 3-4 short paragraphs. First paragraph: what's wrong and how bad it is (the headline). Second paragraph: the evidence — equipment patterns and what they mean, with numbers as proof. Third paragraph: the crew/shift story and the coding/visibility gaps. Fourth paragraph: one recommendation and what's needed next. Every paragraph should read like it belongs in a well-edited article, not a spreadsheet summary.]"""


@dataclass(slots=True)
class Narrative:
    verdict: str
    evidence_paragraphs: list[str]
    recommendation: str
    caveat: str


def generate_narrative(result: AnalysisResult, question: str | None = None, kb: dict | None = None) -> Narrative:
    """Generate analysis narrative via GPT-5.2 with caching.
    
    Args:
        result: Structured analysis from engine
        question: User's question
        kb: Equipment knowledge base (from passdown data) — optional
    """
    q = question or "What is costing this line the most production, and what's the top action to fix it?"
    serialized = _serialize(result, q, kb=kb)
    cache_key = hashlib.sha256(serialized.encode()).hexdigest()

    # Check cache
    cached = _load_cache(cache_key)
    if cached is not None:
        print("[cached] narrative", file=sys.stderr)
        return cached

    # Call LLM
    api_key = _get_api_key()
    if not api_key:
        print("[no-api-key] Set OPENAI_API_KEY for LLM narratives", file=sys.stderr)
        return _fallback(result)

    try:
        raw = _call_llm(serialized, api_key)
        narrative = _parse_response(raw)
        _save_cache(cache_key, narrative)
        print("[llm] narrative", file=sys.stderr)
        return narrative
    except Exception as exc:
        print(f"[llm-error] narrative: {exc}", file=sys.stderr)
        return _fallback(result)


def _serialize(result: AnalysisResult, question: str, kb: dict | None = None) -> str:
    lines = [
        f"Question: {question}",
        f"Line: {result.line_id}",
        f"Date Range: {result.date_range[0].date()} to {result.date_range[1].date()}",
        f"Total Events: {result.total_events}",
        f"Total Downtime: {result.total_downtime_hours:.1f}h",
        f"Average OEE: {result.avg_oee:.1%}" if result.avg_oee else "Average OEE: N/A",
    ]

    # Separate equipment losses from operational/coding losses
    equip_losses = []
    coding_losses = []
    operational_names = {"unassigned", "not scheduled", "unknown", "short stop",
                         "change over", "break-lunch", "breaks/lunch/meals",
                         "breaks, lunch, meals", "break relief other line",
                         "training - meeting", "meetings", "other", "holiday",
                         "no stock", "bad stock", "drive off", "power outage"}
    for ep in result.equipment_profiles:
        if ep.equipment_raw_name.lower().strip() in operational_names or ep.equipment_id is None:
            coding_losses.append(ep)
        else:
            equip_losses.append(ep)

    lines.extend(["", "=== EQUIPMENT/MACHINE LOSSES (true equipment failures) ==="])
    for i, ep in enumerate(equip_losses[:15], 1):
        mtbf = f"{ep.mtbf_minutes:.1f}" if ep.mtbf_minutes else "N/A"
        lines.append(
            f"{i}. {ep.equipment_raw_name}: {ep.event_count} events, "
            f"{ep.total_downtime_hours:.1f}h downtime, MTBF {mtbf} min, "
            f"repeat rate {ep.repeat_failure_rate:.1%}, avg duration {ep.avg_duration_minutes:.1f} min"
        )
        # Shift breakdown with cross-shift ratios
        shift_counts = {s: d["count"] for s, d in ep.by_shift.items() if d["count"] > 0}
        shift_hours = {s: d["hours"] for s, d in ep.by_shift.items() if d["count"] > 0}
        for shift in ("1st", "2nd", "3rd"):
            if shift in shift_counts:
                lines.append(f"   {shift} shift: {shift_counts[shift]} events, {shift_hours[shift]:.1f}h")
        # Cross-shift ratio if significant
        if len(shift_counts) >= 2:
            sorted_shifts = sorted(shift_counts.items(), key=lambda x: x[1])
            low_s, low_c = sorted_shifts[0]
            high_s, high_c = sorted_shifts[-1]
            if low_c > 0 and high_c / low_c >= 2.0:
                ratio = high_c / low_c
                lines.append(f"   >> {high_s} shift has {ratio:.1f}x more events than {low_s} shift")

    lines.extend(["", "=== OPERATIONAL/CODING LOSSES (not equipment — supervision/process) ==="])
    for i, ep in enumerate(coding_losses[:10], 1):
        lines.append(
            f"{i}. {ep.equipment_raw_name}: {ep.event_count} events, "
            f"{ep.total_downtime_hours:.1f}h"
        )
        for shift in ("1st", "2nd", "3rd"):
            d = ep.by_shift.get(shift, {})
            if d.get("count", 0) > 0:
                lines.append(f"   {shift} shift: {d['count']} events, {d['hours']:.1f}h")

    lines.extend(["", "=== SHIFT PERFORMANCE ==="])
    for sp in result.shift_profiles:
        oee = f"{sp.avg_oee:.1%}" if sp.avg_oee else "N/A"
        startup = f"{sp.startup_penalty_points:.1%}" if sp.startup_penalty_points else "N/A"
        lines.append(
            f"- {sp.shift} shift: OEE {oee}, {sp.event_count} events, "
            f"{sp.total_downtime_hours:.1f}h total downtime, "
            f"unassigned rate {sp.unassigned_rate:.1%}, "
            f"startup penalty {startup}, avg recovery {sp.avg_recovery_minutes:.1f} min"
        )
        for p in sp.notable_patterns[:5]:
            lines.append(f"  Notable: {p}")

    if result.trends:
        lines.extend(["", "=== TRENDS ==="])
        for t in result.trends:
            vals = ", ".join(f"{m}: {v:.2f}" for m, v in t.monthly_values)
            lines.append(f"- {t.metric_name}: {vals} — {t.direction}, {t.magnitude:.3f} change")

    # Inject prior analysis findings for this line
    prior = load_prior_findings(result.line_id, limit=3)
    if prior:
        lines.append(format_prior_findings_for_prompt(prior))

    # Inject knowledge base context from supervisor passdown notes
    if kb and kb.get("equipment"):
        lines.extend(["", "=== SUPERVISOR PASSDOWN INTELLIGENCE (real floor observations) ==="])

        # Match KB equipment to top MES equipment by fuzzy name matching
        mes_names = {ep.equipment_raw_name.lower().strip() for ep in result.equipment_profiles[:15]}
        kb_matched = []
        for eq in kb["equipment"]:
            area_lower = eq["area"].lower()
            # Check if KB area matches any MES equipment name (substring match)
            for mes_name in mes_names:
                if (area_lower in mes_name or mes_name in area_lower or
                    any(word in mes_name for word in area_lower.split() if len(word) > 3)):
                    kb_matched.append(eq)
                    break

        # Also include top KB items by event count even if no direct MES match
        top_kb = sorted(kb["equipment"], key=lambda x: -x["event_count"])[:8]
        seen = {eq["area"] for eq in kb_matched}
        for eq in top_kb:
            if eq["area"] not in seen:
                kb_matched.append(eq)
                seen.add(eq["area"])

        for eq in kb_matched[:10]:
            lines.append(
                f"\n--- {eq['area']} (passdown: {eq['event_count']} events, "
                f"{eq['total_minutes']} min, resolution rate {eq['resolution_rate']:.0%}) ---"
            )
            lines.append(f"  Shifts: {eq['by_shift']}")
            lines.append(f"  Lines: {eq['by_line']}")

            if eq.get("recurring_issues"):
                lines.append("  Recurring issues:")
                for ri in eq["recurring_issues"][:4]:
                    lines.append(f"    [{ri['count']}x] {ri['issue'][:150]}")

            if eq.get("known_fixes"):
                lines.append("  Known fixes tried:")
                for kf in eq["known_fixes"][:4]:
                    lines.append(
                        f"    [{kf['count']}x] {kf['action'][:100]} → {kf['result'][:80]}"
                    )

        # Add rate targets if available
        if kb.get("rates"):
            lines.extend(["", "=== PRODUCTION RATE TARGETS ==="])
            for r in kb["rates"]:
                parts = [f"{r['line']}: {r['product']}"]
                if r.get("cases_per_shift"):
                    parts.append(f"{r['cases_per_shift']} cases/shift")
                if r.get("cases_per_pallet"):
                    parts.append(f"{r['cases_per_pallet']} cases/pallet")
                lines.append("  ".join(parts))

    return "\n".join(lines)


def _parse_response(text: str) -> Narrative:
    # Strip any markdown
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)

    # Look for NARRATIVE: tag
    narrative_text = text
    if "NARRATIVE:" in text.upper():
        idx = text.upper().index("NARRATIVE:")
        narrative_text = text[idx + len("NARRATIVE:"):].strip()

    # Split into paragraphs by double newlines
    raw_paras = [p.strip() for p in narrative_text.split("\n\n") if p.strip()]

    if not raw_paras:
        # Fall back to single-newline split
        raw_paras = [p.strip() for p in narrative_text.split("\n") if p.strip()]

    if not raw_paras:
        raw_paras = ["No analysis generated."]

    # First paragraph is the verdict/headline, rest is the body
    verdict = raw_paras[0] if raw_paras else "Analysis complete."
    evidence = raw_paras[1:] if len(raw_paras) > 1 else []

    # If the LLM only wrote one paragraph, use it as both
    if not evidence:
        evidence = [verdict]
        verdict = verdict.split(".")[0] + "." if "." in verdict else verdict

    return Narrative(
        verdict=verdict,
        evidence_paragraphs=evidence,
        recommendation="",  # recommendation is woven into the narrative now
        caveat="",
    )


def _call_llm(serialized: str, api_key: str) -> str:
    from openai import OpenAI
    model = get_model("narrative")
    effort = get_reasoning_effort("narrative")

    # Reasoning models burn tokens on invisible thinking.
    # gpt-5.2 typically uses ~3000 reasoning + ~1500 output.
    is_reasoning = model.startswith("gpt-5")
    max_tokens = 4000 if is_reasoning else 1500

    client = OpenAI(api_key=api_key)
    kwargs: dict = {
        "model": model,
        "max_completion_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": ANALYSIS_PROMPT},
            {"role": "user", "content": serialized},
        ],
    }
    if effort is not None:
        kwargs["reasoning_effort"] = effort
    if not is_reasoning:
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
        Path.home() / ".bashrc",
    ]:
        if path.is_file():
            text = path.read_text().strip()
            for line in text.splitlines():
                if "OPENAI_API_KEY=" in line:
                    return line.split("OPENAI_API_KEY=", 1)[1].strip().strip('"').strip("'").strip()
            if text.startswith("sk-"):
                return text
    return None


def _load_cache(key: str) -> Narrative | None:
    path = CACHE_DIR / f"narrative_{key}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())["narrative"]
        return Narrative(
            verdict=data["verdict"],
            evidence_paragraphs=data["evidence_paragraphs"],
            recommendation=data["recommendation"],
            caveat=data["caveat"],
        )
    except (KeyError, json.JSONDecodeError):
        return None


def _save_cache(key: str, n: Narrative) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "narrative": {
            "verdict": n.verdict,
            "evidence_paragraphs": n.evidence_paragraphs,
            "recommendation": n.recommendation,
            "caveat": n.caveat,
        },
        "model": get_model("narrative"),
        "created": datetime.now(timezone.utc).isoformat(),
    }
    (CACHE_DIR / f"narrative_{key}.json").write_text(json.dumps(data, indent=2))


def _fallback(result: AnalysisResult) -> Narrative:
    top = result.equipment_profiles[0] if result.equipment_profiles else None
    if top:
        v = f"Top loss: {top.equipment_raw_name} ({top.event_count} events, {top.total_downtime_hours:.1f}h)."
    else:
        v = "Insufficient data."
    return Narrative(
        verdict=v,
        evidence_paragraphs=["LLM unavailable. Set OPENAI_API_KEY for full analysis."],
        recommendation="Review top equipment loss driver.",
        caveat="Fallback mode — no LLM narrative.",
    )
