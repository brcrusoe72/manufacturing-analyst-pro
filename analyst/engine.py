"""Piece B: Analysis Engine — pure pandas math, no LLM, no agents."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from statistics import median

from .parsers import DowntimeEvent, OEEInterval


def _shift_for(dt: datetime) -> str:
    h = dt.hour
    if 7 <= h < 15:
        return "1st"
    if 15 <= h < 23:
        return "2nd"
    return "3rd"


def _month_label(dt: datetime) -> str:
    return f"{dt.year}-{dt.month:02d}"


@dataclass(slots=True)
class EquipmentProfile:
    equipment_id: str | None
    equipment_raw_name: str
    event_count: int
    total_downtime_hours: float
    avg_duration_minutes: float
    mtbf_minutes: float | None
    repeat_failure_rate: float
    top_reason_codes: list[tuple[str, int, float]]  # (raw_name, count, pct)
    by_shift: dict[str, dict]  # shift -> {count, hours}


@dataclass(slots=True)
class ShiftProfile:
    shift: str
    avg_oee: float | None
    event_count: int
    total_downtime_hours: float
    unassigned_rate: float
    startup_penalty_points: float | None
    avg_recovery_minutes: float
    notable_patterns: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TrendMetric:
    metric_name: str
    monthly_values: list[tuple[str, float]]
    direction: str  # "improving", "worsening", "stable"
    magnitude: float


@dataclass(slots=True)
class AnalysisResult:
    line_id: str
    date_range: tuple[datetime, datetime]
    total_events: int
    total_downtime_hours: float
    avg_oee: float | None
    equipment_profiles: list[EquipmentProfile]
    shift_profiles: list[ShiftProfile]
    trends: list[TrendMetric]
    top_loss_driver: str
    machine_signal_score: float
    crew_signal_score: float
    oversight_signal_score: float


def analyze(events: list[DowntimeEvent], oee: list[OEEInterval]) -> AnalysisResult:
    """Run full analysis on parsed data. Returns structured result."""
    if not events:
        raise ValueError("No events to analyze")

    # Basic stats
    line_ids = Counter(e.line_id for e in events)
    line_id = line_ids.most_common(1)[0][0]
    line_events = [e for e in events if e.line_id == line_id]
    line_oee = [o for o in oee if o.line_id == line_id]

    start = min(e.start_time for e in line_events)
    end = max(e.end_time for e in line_events)
    total_hours = sum(e.duration_seconds for e in line_events) / 3600.0

    # Equipment profiles
    equip_profiles = _build_equipment_profiles(line_events)

    # Shift profiles
    shift_profiles = _build_shift_profiles(line_events, line_oee)

    # Trends
    trends = _build_trends(line_events)

    # Signal scores
    machine_score, crew_score, oversight_score = _compute_signal_scores(
        equip_profiles, shift_profiles
    )

    top_loss = equip_profiles[0].equipment_raw_name if equip_profiles else "unknown"

    return AnalysisResult(
        line_id=line_id,
        date_range=(start, end),
        total_events=len(line_events),
        total_downtime_hours=total_hours,
        avg_oee=_safe_mean([o.oee for o in line_oee if o.oee is not None]),
        equipment_profiles=equip_profiles,
        shift_profiles=shift_profiles,
        trends=trends,
        top_loss_driver=top_loss,
        machine_signal_score=machine_score,
        crew_signal_score=crew_score,
        oversight_signal_score=oversight_score,
    )


def _build_equipment_profiles(events: list[DowntimeEvent]) -> list[EquipmentProfile]:
    """Group events by equipment, compute metrics, rank by downtime hours."""
    by_equip: dict[str, list[DowntimeEvent]] = defaultdict(list)
    for e in events:
        key = e.equipment_raw_name or "Unknown"
        by_equip[key].append(e)

    profiles: list[EquipmentProfile] = []
    for raw_name, evts in by_equip.items():
        count = len(evts)
        total_h = sum(e.duration_seconds for e in evts) / 3600.0
        avg_dur = (sum(e.duration_seconds for e in evts) / count / 60.0) if count else 0.0

        # MTBF: median interval between consecutive failures
        sorted_evts = sorted(evts, key=lambda e: e.start_time)
        intervals = []
        for i in range(1, len(sorted_evts)):
            gap = (sorted_evts[i].start_time - sorted_evts[i - 1].end_time).total_seconds()
            if gap >= 0:
                intervals.append(gap / 60.0)  # minutes
        mtbf = median(intervals) if intervals else None

        # Repeat failure rate: same equipment fails again within 30 min
        repeats = 0
        for i in range(1, len(sorted_evts)):
            gap_min = (sorted_evts[i].start_time - sorted_evts[i - 1].end_time).total_seconds() / 60.0
            if 0 <= gap_min <= 30:
                repeats += 1
        repeat_rate = repeats / max(count - 1, 1) if count > 1 else 0.0

        # By shift
        shift_data: dict[str, dict] = {}
        for shift in ("1st", "2nd", "3rd"):
            shift_evts = [e for e in evts if _shift_for(e.start_time) == shift]
            shift_data[shift] = {
                "count": len(shift_evts),
                "hours": sum(e.duration_seconds for e in shift_evts) / 3600.0,
            }

        # Reason codes (sub-breakdown by raw name within same equipment_id)
        # For equipment that normalizes multiple raw names to one ID, show sub-codes
        # Otherwise just show the raw name itself
        reason_counts = Counter(e.equipment_raw_name for e in evts)
        top_reasons = [
            (name, cnt, cnt / count) for name, cnt in reason_counts.most_common(5)
        ]

        profiles.append(EquipmentProfile(
            equipment_id=evts[0].equipment_id,
            equipment_raw_name=raw_name,
            event_count=count,
            total_downtime_hours=total_h,
            avg_duration_minutes=avg_dur,
            mtbf_minutes=mtbf,
            repeat_failure_rate=repeat_rate,
            top_reason_codes=top_reasons,
            by_shift=shift_data,
        ))

    profiles.sort(key=lambda p: p.total_downtime_hours, reverse=True)
    return profiles


def _build_shift_profiles(
    events: list[DowntimeEvent], oee: list[OEEInterval]
) -> list[ShiftProfile]:
    """Compute per-shift metrics."""
    profiles: list[ShiftProfile] = []
    for shift in ("1st", "2nd", "3rd"):
        shift_evts = [e for e in events if _shift_for(e.start_time) == shift]
        shift_oee = [o for o in oee if _shift_for(o.timestamp) == shift]
        count = len(shift_evts)
        total_h = sum(e.duration_seconds for e in shift_evts) / 3600.0
        avg_recovery = (sum(e.duration_seconds for e in shift_evts) / count / 60.0) if count else 0.0

        # Unassigned rate
        unassigned = sum(
            1 for e in shift_evts
            if e.equipment_raw_name and "unassigned" in e.equipment_raw_name.lower()
        )
        unassigned_rate = unassigned / max(count, 1)

        # OEE
        avg_oee = _safe_mean([o.oee for o in shift_oee if o.oee is not None])

        # Startup penalty: first hour OEE vs rest
        startup_penalty = _startup_penalty(shift, shift_oee)

        # Notable patterns: cross-shift equipment comparisons
        notable: list[str] = []
        profiles.append(ShiftProfile(
            shift=shift,
            avg_oee=avg_oee,
            event_count=count,
            total_downtime_hours=total_h,
            unassigned_rate=unassigned_rate,
            startup_penalty_points=startup_penalty,
            avg_recovery_minutes=avg_recovery,
            notable_patterns=notable,
        ))

    # Compute notable patterns (cross-shift comparisons)
    _add_notable_patterns(events, profiles)
    return profiles


def _add_notable_patterns(events: list[DowntimeEvent], profiles: list[ShiftProfile]) -> None:
    """Find equipment with big shift-to-shift variation."""
    equip_by_shift: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for e in events:
        if e.equipment_raw_name:
            equip_by_shift[e.equipment_raw_name][_shift_for(e.start_time)] += 1

    shift_map = {p.shift: p for p in profiles}
    for raw_name, shift_counts in equip_by_shift.items():
        if len(shift_counts) < 2:
            continue
        counts = sorted(shift_counts.items(), key=lambda x: x[1])
        low_shift, low_count = counts[0]
        high_shift, high_count = counts[-1]
        if low_count > 0 and high_count / low_count >= 3.0:
            ratio = high_count / low_count
            pattern = f"{high_shift} shift has {high_count} {raw_name} events vs {low_shift} shift's {low_count} ({ratio:.1f}x)"
            if high_shift in shift_map:
                shift_map[high_shift].notable_patterns.append(pattern)


def _startup_penalty(shift: str, oee_intervals: list[OEEInterval]) -> float | None:
    """OEE gap between first hour of shift and remaining hours."""
    shift_starts = {"1st": 7, "2nd": 15, "3rd": 23}
    start_hour = shift_starts.get(shift)
    if start_hour is None or not oee_intervals:
        return None

    first_hour = [o for o in oee_intervals if o.timestamp.hour == start_hour and o.oee is not None]
    rest = [o for o in oee_intervals if o.timestamp.hour != start_hour and o.oee is not None]

    avg_first = _safe_mean([o.oee for o in first_hour])
    avg_rest = _safe_mean([o.oee for o in rest])

    if avg_first is not None and avg_rest is not None:
        return avg_rest - avg_first  # positive = first hour is worse
    return None


def _build_trends(events: list[DowntimeEvent]) -> list[TrendMetric]:
    """Monthly trends for key metrics."""
    trends: list[TrendMetric] = []

    # Unassigned rate trend
    by_month: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))
    monthly_totals: dict[str, int] = Counter()
    monthly_unassigned: dict[str, int] = Counter()
    for e in events:
        m = _month_label(e.start_time)
        monthly_totals[m] += 1
        if e.equipment_raw_name and "unassigned" in e.equipment_raw_name.lower():
            monthly_unassigned[m] += 1

    months = sorted(monthly_totals.keys())
    if len(months) >= 2:
        vals = []
        for m in months:
            rate = monthly_unassigned[m] / max(monthly_totals[m], 1)
            vals.append((m, round(rate, 3)))
        first_val = vals[0][1]
        last_val = vals[-1][1]
        mag = last_val - first_val
        direction = "improving" if mag < -0.02 else ("worsening" if mag > 0.02 else "stable")
        trends.append(TrendMetric(
            metric_name="unassigned_rate",
            monthly_values=vals,
            direction=direction,
            magnitude=round(mag, 3),
        ))

    return trends


def _compute_signal_scores(
    equip: list[EquipmentProfile], shifts: list[ShiftProfile]
) -> tuple[float, float, float]:
    """Score machine/crew/oversight signals 0-1. Internal only, never displayed."""
    # Machine: based on top equipment concentration + repeat rates
    if equip:
        total_h = sum(e.total_downtime_hours for e in equip)
        top3_h = sum(e.total_downtime_hours for e in equip[:3])
        concentration = top3_h / max(total_h, 0.01)
        avg_repeat = _safe_mean([e.repeat_failure_rate for e in equip[:5]]) or 0.0
        avg_mtbf = _safe_mean([e.mtbf_minutes for e in equip[:5] if e.mtbf_minutes]) or 60.0
        mtbf_score = max(0, 1.0 - (avg_mtbf / 60.0))  # lower MTBF = higher score
        machine = min(1.0, (concentration * 0.4) + (avg_repeat * 0.3) + (mtbf_score * 0.3))
    else:
        machine = 0.0

    # Crew: based on shift OEE variance
    oee_vals = [s.avg_oee for s in shifts if s.avg_oee is not None]
    if len(oee_vals) >= 2:
        oee_spread = max(oee_vals) - min(oee_vals)
        crew = min(1.0, oee_spread / 0.15)  # 15% spread = score 1.0
    else:
        crew = 0.0

    # Oversight: based on unassigned rates
    unassigned_rates = [s.unassigned_rate for s in shifts]
    avg_unassigned = _safe_mean(unassigned_rates) or 0.0
    oversight = min(1.0, avg_unassigned / 0.15)  # 15% unassigned = score 1.0

    return round(machine, 2), round(crew, 2), round(oversight, 2)


def _safe_mean(vals: list[float | None]) -> float | None:
    clean = [v for v in vals if v is not None]
    return sum(clean) / len(clean) if clean else None
