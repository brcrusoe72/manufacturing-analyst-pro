"""Piece F: CLI Runner — data in, insight out."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="analyst",
        description="Manufacturing Analyst — drop data, get insight",
    )
    sub = parser.add_subparsers(dest="command")

    # Run command
    p_run = sub.add_parser("run", help="Analyze data and produce PDF report")
    p_run.add_argument("data", type=str, help="Path to directory containing Excel files")
    p_run.add_argument("--question", "-q", type=str, default=None, help="Question to answer")
    p_run.add_argument("--output", "-o", type=str, default=".", help="Output directory for PDF")
    p_run.add_argument("--no-fixes", action="store_true", help="Skip fix research (faster, cheaper)")
    p_run.add_argument("--research-fixes", action="store_true", help="Force LLM fix research even when KB available")
    p_run.add_argument("--kb", type=str, default=None, help="Path to equipment_kb.json (auto-detected if not set)")

    args = parser.parse_args()

    if args.command == "run":
        _run(args)
    else:
        parser.print_help()
        sys.exit(1)


def _run(args: argparse.Namespace) -> None:
    t0 = time.time()

    # Load
    print("Loading data...", file=sys.stderr)
    from .loader import load_data
    events, oee = load_data(args.data)
    print(f"  {len(events)} events, {len(oee)} OEE intervals", file=sys.stderr)

    # Analyze
    print("Analyzing...", file=sys.stderr)
    from .engine import analyze
    result = analyze(events, oee)
    print(
        f"  Line: {result.line_id} | Events: {result.total_events} | "
        f"Downtime: {result.total_downtime_hours:.1f}h | "
        f"OEE: {result.avg_oee:.1%}" if result.avg_oee else f"  Line: {result.line_id} | Events: {result.total_events}",
        file=sys.stderr,
    )

    # Load knowledge base
    import json
    kb = None
    kb_path = args.kb
    if not kb_path:
        # Auto-detect KB in memory/ directory relative to skill
        _skill_dir = Path(__file__).resolve().parent.parent
        _auto_kb = _skill_dir / "memory" / "equipment_kb.json"
        if _auto_kb.is_file():
            kb_path = str(_auto_kb)
    if kb_path and Path(kb_path).is_file():
        try:
            kb = json.loads(Path(kb_path).read_text())
            print(f"  Knowledge base loaded: {kb['meta']['equipment_categories']} equipment categories, "
                  f"{kb['meta']['total_events']} passdown events", file=sys.stderr)
        except Exception as exc:
            print(f"  [warn] Failed to load KB: {exc}", file=sys.stderr)

    # Narrative — now with KB context
    print("Generating narrative...", file=sys.stderr)
    from .narrative import generate_narrative
    narrative = generate_narrative(result, args.question, kb=kb)

    # Fixes — use LLM research only if explicitly requested or no KB available
    fixes = []
    use_research = args.research_fixes or (not args.no_fixes and kb is None)
    if use_research:
        print("Researching fixes...", file=sys.stderr)
        from .researcher import research_fixes
        operational_names = {"unassigned", "not scheduled", "unknown", "short stop",
                             "change over", "break-lunch", "breaks/lunch/meals",
                             "breaks, lunch, meals", "break relief other line",
                             "training - meeting", "meetings", "other", "holiday",
                             "no stock", "bad stock", "drive off", "power outage"}
        real_equipment = [
            ep for ep in result.equipment_profiles
            if ep.equipment_raw_name.lower().strip() not in operational_names and ep.equipment_id is not None
        ]
        fixes = research_fixes(real_equipment[:3])
    elif kb is not None:
        print("  Using knowledge base for fixes (skipping LLM research)", file=sys.stderr)

    # Render
    print("Rendering PDF...", file=sys.stderr)
    from .renderer import render_pdf
    out_path = render_pdf(
        result, narrative, fixes,
        output_dir=args.output,
        question=args.question,
    )

    # Save finding to memory
    print("Saving to memory...", file=sys.stderr)
    from .memory import save_finding
    from datetime import date as _date

    # Build top equipment snapshot
    top_equip_snapshot = [
        {
            "name": ep.equipment_raw_name,
            "events": ep.event_count,
            "hours": round(ep.total_downtime_hours, 1),
            "repeat_rate": round(ep.repeat_failure_rate, 2),
        }
        for ep in result.equipment_profiles[:5]
    ]

    # Shift OEE spread
    shift_spread = {
        sp.shift: round(sp.avg_oee, 3) if sp.avg_oee is not None else None
        for sp in result.shift_profiles
    }

    # Key metrics
    key_metrics = {
        "total_events": result.total_events,
        "total_downtime_hours": round(result.total_downtime_hours, 1),
    }
    # Find unassigned hours
    for ep in result.equipment_profiles:
        if "unassigned" in ep.equipment_raw_name.lower():
            key_metrics["unassigned_hours"] = round(ep.total_downtime_hours, 1)
            break

    finding_path = save_finding(
        line_id=result.line_id,
        analysis_date=_date.today().isoformat(),
        data_start=result.date_range[0].date().isoformat(),
        data_end=result.date_range[1].date().isoformat(),
        question=args.question or "General analysis",
        verdict=narrative.verdict or (narrative.evidence_paragraphs[0][:500] if narrative.evidence_paragraphs else ""),
        avg_oee=round(result.avg_oee, 3) if result.avg_oee else None,
        top_equipment=top_equip_snapshot,
        shift_spread=shift_spread,
        recommendation=narrative.recommendation or (narrative.evidence_paragraphs[-1][:500] if narrative.evidence_paragraphs else ""),
        key_metrics=key_metrics,
    )
    print(f"  Finding saved: {finding_path.name}", file=sys.stderr)

    elapsed = time.time() - t0
    print(f"\nReport saved: {out_path}", file=sys.stderr)
    print(f"Completed in {elapsed:.1f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
