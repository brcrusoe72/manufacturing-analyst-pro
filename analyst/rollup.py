"""Piece G: Period Rollup — OEE + target attainment by line, month, quarter, year.

Answers the only two questions that matter on a passdown: *are we hitting target,
and where is the loss going* — sliced by line and by month / quarter / year.

Pure stdlib math over parsed ``OEEInterval`` / ``DowntimeEvent`` records (no LLM,
no Streamlit). Aggregation is mathematically exact, not an average-of-percentages:

    Availability = Σ production_sec / Σ planned_sec        (planned = net-operation time)
    Performance  = Σ (perf_i · production_sec_i) / Σ production_sec   (exact run-time identity)
    Quality      = Σ good_units / Σ total_units
    OEE          = Availability · Performance · Quality
    Attainment   = Σ actual_units / Σ target_units          (actual vs scheduled target)

Averaging the per-interval OEE column instead (what the legacy engine did) silently
overweights idle hours and understates real OEE — so we never do that here.
"""
from __future__ import annotations

import csv
import html
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .parsers import DowntimeEvent, OEEInterval

GRAINS = ("year", "quarter", "month")

# An event counts as "uncoded" when nobody assigned a real reason — the single
# biggest, most fixable blind spot on most lines.
_UNCODED = {"", "unassigned", "downtime", "unknown", "none"}


def period_key(dt: datetime, grain: str) -> str:
    """Bucket a timestamp into a year / quarter / month label."""
    if grain == "year":
        return f"{dt.year}"
    if grain == "quarter":
        return f"{dt.year}-Q{(dt.month - 1) // 3 + 1}"
    if grain == "month":
        return f"{dt.year}-{dt.month:02d}"
    raise ValueError(f"unknown grain: {grain}")


def _is_availability_loss(e: DowntimeEvent) -> bool:
    """True for stoppages that burn availability (the OEE 'down' bucket)."""
    lt = (e.loss_type or "").lower()
    if "avail" in lt:
        return True
    # Tolerate plants whose loss-type normalization differs: fall back to the
    # event_type flag, excluding the planned / performance / legal buckets.
    if e.event_type == "downtime" and not any(t in lt for t in ("perform", "not", "legal", "schedul")):
        return True
    return False


@dataclass(slots=True)
class LossRow:
    category: str
    hours: float
    events: int


@dataclass(slots=True)
class PeriodCell:
    line_id: str
    grain: str
    period: str
    planned_hours: float
    downtime_hours: float
    availability: float | None
    performance: float | None
    quality: float | None
    oee: float | None
    attainment: float | None
    good_cases: int
    target_cases: float | None
    uncoded_hours: float
    uncoded_pct: float | None
    top_loss: str
    top_loss_hours: float


@dataclass(slots=True)
class RollupResult:
    lines: list[str]
    date_range: tuple[datetime, datetime]
    cells: dict[str, list[PeriodCell]] = field(default_factory=dict)  # grain -> rows
    pareto: dict[str, list[LossRow]] = field(default_factory=dict)    # line_id -> ranked losses
    overall: dict[str, PeriodCell] = field(default_factory=dict)      # line_id -> all-time cell
    notes: list[str] = field(default_factory=list)


_UNKNOWN_LINES = {"line-unknown", "line_unknown", ""}


def _reconcile_lines(events: list[DowntimeEvent], oee: list[OEEInterval]) -> str | None:
    """Join OEE and event records that disagree on line identity.

    Hourly OEE exports often omit the line name per row (it parses as
    'line-unknown'), while the event export carries it via SystemName. When the
    data describes exactly one real line, fold the unknowns into it so metrics
    and downtime align. With genuine multi-line data the unknowns are left alone
    rather than guessed.
    """
    ids = {e.line_id for e in events} | {o.line_id for o in oee}
    real = ids - _UNKNOWN_LINES
    if len(real) != 1 or not (ids & _UNKNOWN_LINES):
        return None
    target = next(iter(real))
    for e in events:
        if e.line_id in _UNKNOWN_LINES:
            e.line_id = target
    for o in oee:
        if o.line_id in _UNKNOWN_LINES:
            o.line_id = target
    return target


# ── core math ────────────────────────────────────────────────────────────────

def _aggregate(intervals: list[OEEInterval]) -> dict:
    """Exact OEE decomposition + attainment for a set of intervals."""
    planned = production = runtime = 0.0
    good = total = 0
    actual_u = target_u = 0.0
    have_target = False
    for o in intervals:
        plan = o.net_operation_seconds if (o.net_operation_seconds or 0) > 0 else o.interval_seconds
        plan = plan or 0.0
        down = o.downtime_seconds or 0.0
        prod = plan - down
        if prod < 0:
            prod = 0.0
        planned += plan
        production += prod
        runtime += (o.performance if o.performance is not None else 1.0) * prod
        good += o.good_units or 0
        total += o.total_units or 0
        if o.target_units and o.target_units > 0:
            target_u += o.target_units
            actual_u += o.actual_calculation_units or 0.0
            have_target = True

    A = production / planned if planned else None
    P = runtime / production if production else None
    Q = good / total if total else None
    oee = (A or 0) * (P or 0) * (Q or 0) if None not in (A, P, Q) else None
    attainment = (actual_u / target_u) if (have_target and target_u) else None
    return {
        "planned_hours": planned / 3600.0,
        "downtime_hours": sum((o.downtime_seconds or 0.0) for o in intervals) / 3600.0,
        "availability": A,
        "performance": P,
        "quality": Q,
        "oee": oee,
        "attainment": attainment,
        "good_cases": good,
        "target_cases": target_u if have_target else None,
    }


def _pareto(events: list[DowntimeEvent], top_n: int = 20) -> tuple[list[LossRow], float]:
    """Rank availability-loss categories by downtime hours; return (rows, uncoded_hours)."""
    by_cat: dict[str, list[float]] = defaultdict(list)
    uncoded_h = 0.0
    for e in events:
        if not _is_availability_loss(e):
            continue
        cat = (e.equipment_raw_name or "Unassigned").strip()
        hrs = (e.duration_seconds or 0.0) / 3600.0
        by_cat[cat].append(hrs)
        if cat.lower() in _UNCODED:
            uncoded_h += hrs
    rows = [LossRow(cat, sum(v), len(v)) for cat, v in by_cat.items()]
    rows.sort(key=lambda r: r.hours, reverse=True)
    return rows[:top_n], uncoded_h


def _cell(line_id: str, grain: str, period: str,
          intervals: list[OEEInterval], events: list[DowntimeEvent]) -> PeriodCell:
    agg = _aggregate(intervals)
    pareto, uncoded_h = _pareto(events, top_n=1)
    down_h = agg["downtime_hours"]
    top = pareto[0] if pareto else LossRow("—", 0.0, 0)
    return PeriodCell(
        line_id=line_id, grain=grain, period=period,
        planned_hours=agg["planned_hours"], downtime_hours=down_h,
        availability=agg["availability"], performance=agg["performance"],
        quality=agg["quality"], oee=agg["oee"], attainment=agg["attainment"],
        good_cases=agg["good_cases"], target_cases=agg["target_cases"],
        uncoded_hours=uncoded_h,
        uncoded_pct=(uncoded_h / down_h) if down_h else None,
        top_loss=top.category, top_loss_hours=top.hours,
    )


def build_rollup(events: list[DowntimeEvent], oee: list[OEEInterval],
                 grains: tuple[str, ...] = GRAINS) -> RollupResult:
    """Group OEE intervals + downtime events into line × period cells."""
    if not oee and not events:
        raise ValueError("No OEE or event data to roll up")

    folded = _reconcile_lines(events, oee)
    lines = sorted({o.line_id for o in oee} | {e.line_id for e in events})
    stamps = [o.timestamp for o in oee] + [e.start_time for e in events]
    result = RollupResult(lines=lines, date_range=(min(stamps), max(stamps)))
    if folded:
        result.notes.append(f"OEE intervals had no per-row line name; folded into {folded}.")

    for grain in grains:
        buckets_o: dict[tuple[str, str], list[OEEInterval]] = defaultdict(list)
        buckets_e: dict[tuple[str, str], list[DowntimeEvent]] = defaultdict(list)
        for o in oee:
            buckets_o[(o.line_id, period_key(o.timestamp, grain))].append(o)
        for e in events:
            buckets_e[(e.line_id, period_key(e.start_time, grain))].append(e)
        keys = sorted(set(buckets_o) | set(buckets_e),
                      key=lambda k: (k[0], k[1]))
        result.cells[grain] = [
            _cell(ln, grain, per, buckets_o.get((ln, per), []), buckets_e.get((ln, per), []))
            for (ln, per) in keys
        ]

    for ln in lines:
        l_oee = [o for o in oee if o.line_id == ln]
        l_evt = [e for e in events if e.line_id == ln]
        result.overall[ln] = _cell(ln, "all", "all-time", l_oee, l_evt)
        result.pareto[ln], _ = _pareto(l_evt, top_n=20)
    return result


# ── rendering ────────────────────────────────────────────────────────────────

def _pct(v: float | None) -> str:
    return f"{v * 100:.1f}%" if v is not None else "—"


def _verdict(att: float | None) -> str:
    if att is None:
        return "no target"
    if att >= 0.95:
        return "ON TARGET"
    if att >= 0.80:
        return "BEHIND"
    return "WELL SHORT"


def render_console(r: RollupResult) -> str:
    out: list[str] = []
    d0, d1 = r.date_range
    out.append(f"OEE + TARGET ROLLUP   lines={', '.join(r.lines)}   "
               f"{d0.date()} → {d1.date()}")
    for ln in r.lines:
        c = r.overall[ln]
        out.append("")
        out.append(f"=== {ln}  (all-time) ===")
        out.append(f"  OEE {_pct(c.oee)}   A {_pct(c.availability)}  P {_pct(c.performance)}  "
                   f"Q {_pct(c.quality)}   attainment {_pct(c.attainment)} [{_verdict(c.attainment)}]")
        out.append(f"  planned {c.planned_hours:,.0f} h | downtime {c.downtime_hours:,.0f} h | "
                   f"uncoded {_pct(c.uncoded_pct)} of downtime")
        out.append(f"  YEAR  | {'OEE':>6} {'Avail':>6} {'Perf':>6} {'Qual':>6} {'Attain':>7}  Top loss")
        for cell in r.cells["year"]:
            if cell.line_id != ln:
                continue
            out.append(f"  {cell.period:<5} | {_pct(cell.oee):>6} {_pct(cell.availability):>6} "
                       f"{_pct(cell.performance):>6} {_pct(cell.quality):>6} {_pct(cell.attainment):>7}"
                       f"  {cell.top_loss} ({cell.top_loss_hours:,.0f}h)")
        out.append(f"  Top downtime categories:")
        for lr in r.pareto[ln][:8]:
            out.append(f"    {lr.hours:7,.0f} h  {lr.events:6,} ev   {lr.category}")
    return "\n".join(out)


def _att_color(att: float | None) -> str:
    if att is None:
        return "#888"
    if att >= 0.95:
        return "#1a7f37"
    if att >= 0.80:
        return "#9a6700"
    return "#cf222e"


def _rows_html(cells: list[PeriodCell]) -> str:
    body = []
    for c in cells:
        body.append(
            "<tr>"
            f"<td>{html.escape(c.line_id)}</td>"
            f"<td>{html.escape(c.period)}</td>"
            f"<td class='n'>{_pct(c.oee)}</td>"
            f"<td class='n'>{_pct(c.availability)}</td>"
            f"<td class='n'>{_pct(c.performance)}</td>"
            f"<td class='n'>{_pct(c.quality)}</td>"
            f"<td class='n' style='color:{_att_color(c.attainment)};font-weight:600'>{_pct(c.attainment)}</td>"
            f"<td>{html.escape(_verdict(c.attainment))}</td>"
            f"<td class='n'>{c.good_cases:,}</td>"
            f"<td class='n'>{c.planned_hours:,.0f}</td>"
            f"<td class='n'>{c.downtime_hours:,.0f}</td>"
            f"<td class='n'>{_pct(c.uncoded_pct)}</td>"
            f"<td>{html.escape(c.top_loss)} <span class='muted'>({c.top_loss_hours:,.0f}h)</span></td>"
            "</tr>"
        )
    return "".join(body)


_TABLE_HEAD = ("<tr><th>Line</th><th>Period</th><th>OEE</th><th>Avail</th><th>Perf</th>"
               "<th>Qual</th><th>Attain</th><th>Verdict</th><th>Good cases</th>"
               "<th>Planned h</th><th>Down h</th><th>Uncoded</th><th>Top loss</th></tr>")


def render_html(r: RollupResult) -> str:
    d0, d1 = r.date_range
    parts = [f"""<!doctype html><meta charset=utf-8>
<title>OEE + Target Rollup</title>
<style>
 body{{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:32px;color:#1c2024;max-width:1180px}}
 h1{{font-size:22px;margin:0 0 2px}} h2{{font-size:16px;margin:28px 0 8px;border-bottom:2px solid #eaecef;padding-bottom:4px}}
 .sub{{color:#656d76;margin-bottom:18px}}
 table{{border-collapse:collapse;width:100%;font-size:13px;margin-bottom:8px}}
 th,td{{padding:5px 9px;border-bottom:1px solid #eaecef;text-align:left;white-space:nowrap}}
 th{{background:#f6f8fa;font-weight:600}} td.n{{text-align:right;font-variant-numeric:tabular-nums}}
 .muted{{color:#8b949e;font-weight:400}} tr:hover td{{background:#fbfcfd}}
 .cards{{display:flex;gap:14px;flex-wrap:wrap;margin:14px 0 4px}}
 .card{{border:1px solid #d0d7de;border-radius:8px;padding:12px 16px;min-width:150px}}
 .card .k{{font-size:12px;color:#656d76}} .card .v{{font-size:21px;font-weight:600}}
 .bar{{height:7px;border-radius:4px;background:#eaecef;overflow:hidden;margin-top:5px}}
 .bar>span{{display:block;height:100%}}
</style>
<h1>OEE &amp; Target-Attainment Rollup</h1>
<div class=sub>Lines: {html.escape(', '.join(r.lines))} &nbsp;·&nbsp; {d0.date()} → {d1.date()} &nbsp;·&nbsp; generated by manufacturing-analyst</div>
"""]
    for ln in r.lines:
        c = r.overall[ln]
        att_w = min(int((c.attainment or 0) * 100), 100)
        oee_w = min(int((c.oee or 0) * 100), 100)
        parts.append(f"<h2>{html.escape(ln)} — all-time</h2><div class=cards>")
        for k, v, extra in [
            ("OEE", _pct(c.oee), f"<div class=bar><span style='width:{oee_w}%;background:#0969da'></span></div>"),
            ("Attainment", _pct(c.attainment),
             f"<div class=bar><span style='width:{att_w}%;background:{_att_color(c.attainment)}'></span></div>"),
            ("Availability", _pct(c.availability), ""),
            ("Performance", _pct(c.performance), ""),
            ("Quality", _pct(c.quality), ""),
            ("Uncoded downtime", _pct(c.uncoded_pct), ""),
        ]:
            parts.append(f"<div class=card><div class=k>{k}</div><div class=v>{v}</div>{extra}</div>")
        parts.append("</div>")

    titles = {"year": "By year", "quarter": "By quarter", "month": "By month"}
    for grain in ("year", "quarter", "month"):
        if grain not in r.cells:
            continue
        rows = r.cells[grain]
        if grain == "month":
            rows = rows[-24:]  # keep it readable
        parts.append(f"<h2>{titles[grain]}</h2><table>{_TABLE_HEAD}{_rows_html(rows)}</table>")

    for ln in r.lines:
        parts.append(f"<h2>{html.escape(ln)} — downtime Pareto (availability loss)</h2><table>"
                     "<tr><th>Category</th><th>Hours</th><th>Events</th><th>Avg min/event</th></tr>")
        for lr in r.pareto[ln]:
            avg = (lr.hours * 60 / lr.events) if lr.events else 0
            parts.append(f"<tr><td>{html.escape(lr.category)}</td><td class=n>{lr.hours:,.0f}</td>"
                         f"<td class=n>{lr.events:,}</td><td class=n>{avg:.1f}</td></tr>")
        parts.append("</table>")
    return "".join(parts)


def write_csvs(r: RollupResult, out_dir: str | Path) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    header = ["line", "grain", "period", "oee", "availability", "performance", "quality",
              "attainment", "verdict", "good_cases", "target_cases", "planned_hours",
              "downtime_hours", "uncoded_hours", "uncoded_pct", "top_loss", "top_loss_hours"]
    for grain, cells in r.cells.items():
        p = out / f"oee_rollup_{grain}.csv"
        with p.open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            for c in cells:
                w.writerow([c.line_id, c.grain, c.period, c.oee, c.availability, c.performance,
                            c.quality, c.attainment, _verdict(c.attainment), c.good_cases,
                            c.target_cases, round(c.planned_hours, 1), round(c.downtime_hours, 1),
                            round(c.uncoded_hours, 1), c.uncoded_pct, c.top_loss,
                            round(c.top_loss_hours, 1)])
        written.append(p)
    # Pareto
    p = out / "downtime_pareto.csv"
    with p.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["line", "category", "downtime_hours", "events", "avg_minutes_per_event"])
        for ln, rows in r.pareto.items():
            for lr in rows:
                avg = (lr.hours * 60 / lr.events) if lr.events else 0
                w.writerow([ln, lr.category, round(lr.hours, 1), lr.events, round(avg, 1)])
    written.append(p)
    return written