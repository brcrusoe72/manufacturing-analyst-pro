"""Piece F: CLI Runner — data in, insight out."""
from __future__ import annotations

import argparse
import json
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

    # Agent command
    p_agent = sub.add_parser("agent", help="Run the Shift Intelligence Agent on data")
    p_agent.add_argument("data", type=str, help="Path to directory containing Excel files")
    p_agent.add_argument("--scenario", "-s", type=str, default="General shift intelligence", help="Scenario/question for the agent")
    p_agent.add_argument("--kb", type=str, default=None, help="Path to equipment_kb.json (auto-detected if not set)")
    p_agent.add_argument("--output", "-o", type=str, default=None, help="Optional JSON output path")
    p_agent.add_argument("--evals", type=str, default=None, help="Optional eval scenario JSON to score the agent")

    # Workflow command
    p_workflow = sub.add_parser("workflow", help="Run full load/analyze/agent/eval workflow")
    p_workflow.add_argument("data", type=str, help="Path to directory containing Excel files")
    p_workflow.add_argument("--scenario", "-s", type=str, default="General shift intelligence", help="Scenario/question for the workflow")
    p_workflow.add_argument("--kb", type=str, default=None, help="Path to equipment_kb.json (auto-detected if not set)")
    p_workflow.add_argument("--evals", type=str, default=None, help="Optional eval scenario JSON to score the workflow")
    p_workflow.add_argument("--output", "-o", type=str, default="reports", help="Output directory or JSON path")

    # Line review command
    p_line = sub.add_parser("line-review", help="Run long-horizon line intelligence review")
    p_line.add_argument("data", type=str, help="Path to directory containing Excel/CSV files")
    p_line.add_argument("--line", type=str, default=None, help="Line name/id filter, e.g. 'line-1' or 'L2'")
    p_line.add_argument("--context", type=str, default="", help="Plant/line context to include in the review")
    p_line.add_argument("--photo-name", type=str, default=None, help="Name of attached photo/context artifact")
    p_line.add_argument("--output", "-o", type=str, default="reports/line_review.md", help="Output markdown or JSON path")

    # Rollup command — OEE + target attainment by line / month / quarter / year
    p_rollup = sub.add_parser("rollup", help="OEE + target attainment by line, month, quarter, year")
    p_rollup.add_argument("data", type=str, help="Path to directory containing OEE + Event Excel/CSV files")
    p_rollup.add_argument("--grains", type=str, default="year,quarter,month",
                          help="Comma-separated period grains (subset of year,quarter,month)")
    p_rollup.add_argument("--line", type=str, default=None, help="Optional line_id filter, e.g. 'line-2'")
    p_rollup.add_argument("--output", "-o", type=str, default="reports/rollup",
                          help="Output directory for CSVs + HTML report")

    # Agentic harness command
    p_harness = sub.add_parser("harness", help="Run the markdown-driven manufacturing agent harness")
    p_harness.add_argument("--message", "-m", type=str, default=None, help="Agent request. Omit for interactive mode.")
    p_harness.add_argument("--data", type=str, default=None, help="Optional data file or directory to stage into harness inbox")
    p_harness.add_argument("--line", type=str, default=None, help="Optional line filter")
    p_harness.add_argument("--workspace", type=str, default="agent-workspace", help="Harness workspace directory")
    p_harness.add_argument("--behavior-dir", type=str, default=None, help="Override behavior markdown directory")
    p_harness.add_argument("--photo-name", type=str, default=None, help="Optional photo/context artifact name")
    p_harness.add_argument("--no-llm", action="store_true", help="Disable optional LLM planner and use deterministic planning")
    p_harness.add_argument(
        "--model",
        type=str,
        default="gpt-5-mini",
        help="Planner model when MFG_AGENT_ALLOW_LLM_PLANNER=1 and OPENAI_API_KEY are available",
    )

    # Autonomous operating loop
    p_auto = sub.add_parser("autonomous", help="Run or inspect the autonomous manufacturing operating loop")
    auto_sub = p_auto.add_subparsers(dest="autonomous_command")

    p_auto_run = auto_sub.add_parser("run", help="Run one observe/decide/act/verify cycle")
    p_auto_run.add_argument("--data", required=True, help="Plant data file or directory")
    p_auto_run.add_argument("--line", type=str, default=None, help="Optional line filter")
    p_auto_run.add_argument("--workspace", type=str, default="agent-workspace", help="Harness workspace directory")
    p_auto_run.add_argument("--objective", type=str, default=None, help="Override the default autonomous objective")
    p_auto_run.add_argument("--use-llm", action="store_true", help="Allow the optional LLM planner")
    p_auto_run.add_argument("--model", type=str, default="gpt-5-mini", help="Planner model when --use-llm is set")

    p_auto_status = auto_sub.add_parser("status", help="Show autonomous loop status")
    p_auto_status.add_argument("--workspace", type=str, default="agent-workspace", help="Harness workspace directory")

    p_auto_outcome = auto_sub.add_parser("outcome", help="Record an observed decision outcome")
    p_auto_outcome.add_argument("--workspace", type=str, default="agent-workspace", help="Harness workspace directory")
    p_auto_outcome.add_argument("--decision-id", required=True, help="Decision id from autonomy/decisions.jsonl")
    p_auto_outcome.add_argument("--quality", required=True, choices=["good", "mixed", "bad"], help="Observed quality")
    p_auto_outcome.add_argument("--outcome", required=True, help="What happened")
    p_auto_outcome.add_argument("--helped", default="", help="What helped the decision work")
    p_auto_outcome.add_argument("--misled", default="", help="What misled the decision")
    p_auto_outcome.add_argument("--verification-id", default=None, help="Optional verification item id")

    args = parser.parse_args()

    if args.command == "run":
        _run(args)
    elif args.command == "agent":
        _run_agent(args)
    elif args.command == "workflow":
        _run_workflow(args)
    elif args.command == "line-review":
        _run_line_review(args)
    elif args.command == "rollup":
        _run_rollup(args)
    elif args.command == "harness":
        _run_harness(args)
    elif args.command == "autonomous":
        _run_autonomous(args)
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


def _load_kb(kb_path: str | None) -> dict | None:
    if not kb_path:
        _skill_dir = Path(__file__).resolve().parent.parent
        _auto_kb = _skill_dir / "memory" / "equipment_kb.json"
        if _auto_kb.is_file():
            kb_path = str(_auto_kb)
    if kb_path and Path(kb_path).is_file():
        return json.loads(Path(kb_path).read_text())
    return None


def _run_agent(args: argparse.Namespace) -> None:
    t0 = time.time()

    print("Loading data...", file=sys.stderr)
    from .loader import load_data
    events, oee = load_data(args.data)
    print(f"  {len(events)} events, {len(oee)} OEE intervals", file=sys.stderr)

    print("Analyzing...", file=sys.stderr)
    from .engine import analyze
    result = analyze(events, oee)

    kb = _load_kb(args.kb)
    if kb is not None:
        meta = kb.get("meta", {})
        print(
            f"  Knowledge base loaded: {meta.get('equipment_categories', '?')} equipment categories",
            file=sys.stderr,
        )

    if args.evals:
        print("Running agent evals...", file=sys.stderr)
        from .agents.eval_runner import load_scenarios, run_evals
        payload = run_evals(result, load_scenarios(args.evals), kb=kb)
    else:
        print("Running Shift Intelligence Agent...", file=sys.stderr)
        from .agents import ShiftIntelligenceAgent
        payload = ShiftIntelligenceAgent(kb=kb).run(result, args.scenario).to_dict()

    rendered = json.dumps(payload, indent=2, default=str)
    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered)
        print(f"Agent output saved: {out_path}", file=sys.stderr)
    else:
        print(rendered)

    elapsed = time.time() - t0
    print(f"Completed in {elapsed:.1f}s", file=sys.stderr)


def _run_workflow(args: argparse.Namespace) -> None:
    t0 = time.time()
    kb = _load_kb(args.kb)
    if kb is not None:
        meta = kb.get("meta", {})
        print(
            f"Knowledge base loaded: {meta.get('equipment_categories', '?')} equipment categories",
            file=sys.stderr,
        )

    print("Running Shift Intelligence workflow...", file=sys.stderr)
    from .agents.workflow import run_shift_workflow, save_workflow_run
    run = run_shift_workflow(
        args.data,
        scenario=args.scenario,
        kb=kb,
        evals_path=args.evals,
    )
    out_path = save_workflow_run(run, args.output)
    print(f"Workflow output saved: {out_path}", file=sys.stderr)
    print(f"Completed in {time.time() - t0:.1f}s", file=sys.stderr)
    print(run.to_json())


def _run_line_review(args: argparse.Namespace) -> None:
    t0 = time.time()

    print("Loading data...", file=sys.stderr)
    from .loader import load_data
    events, oee = load_data(args.data)
    print(f"  {len(events)} events, {len(oee)} OEE intervals", file=sys.stderr)

    print("Running line intelligence review...", file=sys.stderr)
    from .line_review import render_markdown_report, run_line_review
    review = run_line_review(
        events,
        oee,
        line_hint=args.line,
        context=args.context,
        photo_name=args.photo_name,
    )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix.lower() == ".json":
        out_path.write_text(json.dumps(review.to_dict(), indent=2, default=str))
    else:
        out_path.write_text(render_markdown_report(review))

    print(
        f"  {review.line_id}: {review.months_covered} months, "
        f"{review.total_events} events, visibility {review.visibility_score}/100",
        file=sys.stderr,
    )
    print(f"Line review saved: {out_path}", file=sys.stderr)
    print(f"Completed in {time.time() - t0:.1f}s", file=sys.stderr)
    print(render_markdown_report(review))


def _run_rollup(args: argparse.Namespace) -> None:
    t0 = time.time()

    print("Loading data...", file=sys.stderr)
    from .loader import load_data
    events, oee = load_data(args.data)
    if args.line:
        events = [e for e in events if e.line_id == args.line]
        oee = [o for o in oee if o.line_id == args.line]
    print(f"  {len(events)} events, {len(oee)} OEE intervals", file=sys.stderr)

    grains = tuple(g.strip() for g in args.grains.split(",") if g.strip())
    print("Building rollup...", file=sys.stderr)
    from .rollup import build_rollup, render_console, render_html, write_csvs
    result = build_rollup(events, oee, grains=grains)

    out_dir = Path(args.output)
    csvs = write_csvs(result, out_dir)
    html_path = out_dir / "rollup_report.html"
    html_path.write_text(render_html(result))

    print(render_console(result))
    print(f"\nCSVs: {', '.join(p.name for p in csvs)}", file=sys.stderr)
    print(f"Report: {html_path}", file=sys.stderr)
    print(f"Completed in {time.time() - t0:.1f}s", file=sys.stderr)


def _run_harness(args: argparse.Namespace) -> None:
    from .agentic_harness import ManufacturingAgenticHarness
    harness = ManufacturingAgenticHarness(
        workspace=args.workspace,
        behavior_dir=args.behavior_dir,
        use_llm=not args.no_llm,
        model=args.model,
    )
    if not args.message:
        harness.interactive()
        return
    run = harness.run(
        args.message,
        data_path=args.data,
        line=args.line,
        photo_name=args.photo_name,
    )
    print(json.dumps(run.to_dict(), indent=2, default=str))


def _run_autonomous(args: argparse.Namespace) -> None:
    from .autonomous import autonomy_status, record_outcome, run_autonomous_cycle

    if args.autonomous_command == "run":
        result = run_autonomous_cycle(
            data_path=args.data,
            workspace=args.workspace,
            line=args.line,
            objective=args.objective,
            use_llm=args.use_llm,
            model=args.model,
        )
        print(json.dumps(result.to_dict(), indent=2, default=str))
        return

    if args.autonomous_command == "status":
        print(json.dumps(autonomy_status(workspace=args.workspace), indent=2, default=str))
        return

    if args.autonomous_command == "outcome":
        payload = record_outcome(
            workspace=args.workspace,
            decision_id=args.decision_id,
            quality=args.quality,
            outcome=args.outcome,
            helped=args.helped,
            misled=args.misled,
            verification_id=args.verification_id,
        )
        print(json.dumps(payload, indent=2, default=str))
        return

    print("Choose an autonomous command: run, status, or outcome.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()