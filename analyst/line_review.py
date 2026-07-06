"""Long-horizon line review for production leadership roles."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from statistics import median
from typing import Any

from .engine import _month_label, _shift_for
from .parsers import DowntimeEvent, OEEInterval


SHORT_STOP_TERMS = ("short stop", "shortstop", "micro stop", "micro-stop", "minor stop")
UNASSIGNED_TERMS = ("unassigned", "unknown", "not assigned", "no code", "other")
SCHEDULE_LOSS_TERMS = (
    "not scheduled",
    "no demand",
    "break-lunch",
    "break lunch",
    "lunch",
    "meeting",
    "meetings",
    "power outage",
    "site emergency",
    "drive off",
)


@dataclass(slots=True)
class MonthlyLineMetric:
    month: str
    event_count: int
    downtime_hours: float
    short_stop_events: int
    short_stop_hours: float
    unassigned_events: int
    unassigned_hours: float
    avg_oee: float | None


@dataclass(slots=True)
class RoleBrief:
    role: str
    focus: str
    verdict: str
    actions: list[str]
    evidence: list[str]


@dataclass(slots=True)
class ActionableConstraint:
    name: str
    events: int
    downtime_hours: float
    avg_duration_minutes: float
    mtbf_minutes: float | None
    repeat_failure_rate: float
    members: list[str]
    by_shift: dict[str, dict[str, float]]
    by_month: dict[str, dict[str, float]]
    maintenance_questions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "events": self.events,
            "downtime_hours": round(self.downtime_hours, 2),
            "avg_duration_minutes": round(self.avg_duration_minutes, 2),
            "mtbf_minutes": round(self.mtbf_minutes, 1) if self.mtbf_minutes is not None else None,
            "repeat_failure_rate": round(self.repeat_failure_rate, 3),
            "members": self.members,
            "by_shift": {
                shift: {k: round(v, 2) for k, v in values.items()}
                for shift, values in self.by_shift.items()
            },
            "by_month": {
                month: {k: round(v, 2) for k, v in values.items()}
                for month, values in self.by_month.items()
            },
            "maintenance_questions": self.maintenance_questions,
        }


@dataclass(slots=True)
class DecisionCockpit:
    suspected_constraint: str
    confidence: str
    decision: str
    target_status: str
    sku_status: str
    next_observation_rule: str
    proof_to_seek: list[str]
    disproof_to_watch: list[str]
    target_attainment: dict[str, Any]
    job_signals: list[dict[str, Any]]
    sku_signals: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "suspected_constraint": self.suspected_constraint,
            "confidence": self.confidence,
            "decision": self.decision,
            "target_status": self.target_status,
            "sku_status": self.sku_status,
            "next_observation_rule": self.next_observation_rule,
            "proof_to_seek": self.proof_to_seek,
            "disproof_to_watch": self.disproof_to_watch,
            "target_attainment": self.target_attainment,
            "job_signals": self.job_signals,
            "sku_signals": self.sku_signals,
        }


@dataclass(slots=True)
class OperatingModel:
    recorded_signal: str
    interpretation: str
    duration_profile: list[dict[str, Any]]
    duration_bias: list[str]
    attribution_risks: list[str]
    flow_hypotheses: list[str]
    cause_classes: list[dict[str, Any]]
    evidence_gaps: list[str]
    leadership_actions: list[dict[str, str]]
    decision_rule: str
    dashboard_gap: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "recorded_signal": self.recorded_signal,
            "interpretation": self.interpretation,
            "duration_profile": self.duration_profile,
            "duration_bias": self.duration_bias,
            "attribution_risks": self.attribution_risks,
            "flow_hypotheses": self.flow_hypotheses,
            "cause_classes": self.cause_classes,
            "evidence_gaps": self.evidence_gaps,
            "leadership_actions": self.leadership_actions,
            "decision_rule": self.decision_rule,
            "dashboard_gap": self.dashboard_gap,
        }


@dataclass(slots=True)
class LineReview:
    line_id: str
    date_range: tuple[datetime, datetime]
    months_covered: int
    total_events: int
    total_downtime_hours: float
    short_stop_events: int
    short_stop_hours: float
    unassigned_events: int
    unassigned_hours: float
    visibility_score: int
    visibility_verdict: str
    management_signal: str
    top_codes: list[tuple[str, int, float, float]]
    actionable_constraints: list[ActionableConstraint]
    masking_summary: str
    maintenance_questions: list[str]
    operating_model: OperatingModel
    decision_cockpit: DecisionCockpit
    monthly_metrics: list[MonthlyLineMetric]
    shift_visibility: dict[str, dict[str, float]]
    role_briefs: list[RoleBrief]
    context_summary: str
    photo_summary: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "line_id": self.line_id,
            "date_range": [self.date_range[0].isoformat(), self.date_range[1].isoformat()],
            "months_covered": self.months_covered,
            "total_events": self.total_events,
            "total_downtime_hours": round(self.total_downtime_hours, 2),
            "short_stop_events": self.short_stop_events,
            "short_stop_hours": round(self.short_stop_hours, 2),
            "unassigned_events": self.unassigned_events,
            "unassigned_hours": round(self.unassigned_hours, 2),
            "visibility_score": self.visibility_score,
            "visibility_verdict": self.visibility_verdict,
            "management_signal": self.management_signal,
            "top_codes": [
                {
                    "code": code,
                    "events": events,
                    "downtime_hours": round(hours, 2),
                    "event_share": round(event_share, 4),
                }
                for code, events, hours, event_share in self.top_codes
            ],
            "actionable_constraints": [item.to_dict() for item in self.actionable_constraints],
            "masking_summary": self.masking_summary,
            "maintenance_questions": self.maintenance_questions,
            "operating_model": self.operating_model.to_dict(),
            "decision_cockpit": self.decision_cockpit.to_dict(),
            "monthly_metrics": [
                {
                    "month": m.month,
                    "event_count": m.event_count,
                    "downtime_hours": round(m.downtime_hours, 2),
                    "short_stop_events": m.short_stop_events,
                    "short_stop_hours": round(m.short_stop_hours, 2),
                    "unassigned_events": m.unassigned_events,
                    "unassigned_hours": round(m.unassigned_hours, 2),
                    "avg_oee": round(m.avg_oee, 4) if m.avg_oee is not None else None,
                }
                for m in self.monthly_metrics
            ],
            "shift_visibility": {
                shift: {k: round(v, 4) for k, v in vals.items()}
                for shift, vals in self.shift_visibility.items()
            },
            "role_briefs": [
                {
                    "role": brief.role,
                    "focus": brief.focus,
                    "verdict": brief.verdict,
                    "actions": brief.actions,
                    "evidence": brief.evidence,
                }
                for brief in self.role_briefs
            ],
            "context_summary": self.context_summary,
            "photo_summary": self.photo_summary,
        }


def run_line_review(
    events: list[DowntimeEvent],
    oee: list[OEEInterval],
    *,
    line_hint: str | None = None,
    context: str = "",
    photo_name: str | None = None,
) -> LineReview:
    """Review one line across months and create management-role outputs."""
    if not events:
        raise ValueError("No downtime events available for line review")

    selected_events = _select_line_events(events, line_hint)
    if not selected_events:
        raise ValueError(f"No downtime events found for line '{line_hint}'")

    line_id = selected_events[0].line_id
    selected_oee = [row for row in oee if row.line_id == line_id]
    start = min(event.start_time for event in selected_events)
    end = max(event.end_time for event in selected_events)
    month_count = len({_month_label(event.start_time) for event in selected_events})

    total_events = len(selected_events)
    total_hours = _sum_hours(selected_events)
    short_events = [event for event in selected_events if _is_short_stop(event)]
    unassigned_events = [event for event in selected_events if _is_unassigned(event)]
    short_event_rate = len(short_events) / max(total_events, 1)
    unassigned_event_rate = len(unassigned_events) / max(total_events, 1)
    visibility_score = _visibility_score(short_event_rate, unassigned_event_rate)

    top_codes = _top_codes(selected_events)
    actionable_constraints = _actionable_constraints(selected_events)
    masking_summary = _masking_summary(short_events, unassigned_events, actionable_constraints)
    maintenance_questions = _maintenance_questions(actionable_constraints, short_events)
    operating_model = _operating_model(
        selected_events,
        actionable_constraints,
        short_events,
        unassigned_events,
        context,
    )
    cockpit = _decision_cockpit(
        selected_events,
        selected_oee,
        actionable_constraints,
        short_events,
        unassigned_events,
        operating_model,
    )
    monthly = _monthly_metrics(selected_events, selected_oee)
    shift_visibility = _shift_visibility(selected_events)
    verdict = _visibility_verdict(visibility_score, short_event_rate, unassigned_event_rate)
    signal = _management_signal(visibility_score, short_event_rate, unassigned_event_rate)
    photo_summary = f"Photo/context artifact attached: {photo_name}" if photo_name else None

    review = LineReview(
        line_id=line_id,
        date_range=(start, end),
        months_covered=month_count,
        total_events=total_events,
        total_downtime_hours=total_hours,
        short_stop_events=len(short_events),
        short_stop_hours=_sum_hours(short_events),
        unassigned_events=len(unassigned_events),
        unassigned_hours=_sum_hours(unassigned_events),
        visibility_score=visibility_score,
        visibility_verdict=verdict,
        management_signal=signal,
        top_codes=top_codes,
        actionable_constraints=actionable_constraints,
        masking_summary=masking_summary,
        maintenance_questions=maintenance_questions,
        operating_model=operating_model,
        decision_cockpit=cockpit,
        monthly_metrics=monthly,
        shift_visibility=shift_visibility,
        role_briefs=[],
        context_summary=context.strip() or "No added plant context provided.",
        photo_summary=photo_summary,
    )
    review.role_briefs = _role_briefs(review)
    return review


def render_markdown_report(review: LineReview) -> str:
    """Render the line review as a portable markdown report."""
    start, end = review.date_range
    lines = [
        f"# Line Intelligence Review - {review.line_id}",
        "",
        f"**Date range:** {start.date().isoformat()} to {end.date().isoformat()}",
        f"**Months covered:** {review.months_covered}",
        f"**Events:** {review.total_events:,}",
        f"**Downtime:** {review.total_downtime_hours:.1f} hours",
        f"**Visibility score:** {review.visibility_score}/100",
        "",
        "## Management Signal",
        "",
        review.management_signal,
        "",
        "## Decision Cockpit",
        "",
        f"- Suspected constraint: {review.decision_cockpit.suspected_constraint}",
        f"- Confidence: {review.decision_cockpit.confidence}",
        f"- Decision: {review.decision_cockpit.decision}",
        f"- Target status: {review.decision_cockpit.target_status}",
        f"- SKU/job status: {review.decision_cockpit.sku_status}",
        f"- Next observation rule: {review.decision_cockpit.next_observation_rule}",
        "",
        "Proof to seek:",
    ]
    for item in review.decision_cockpit.proof_to_seek:
        lines.append(f"- {item}")
    lines.extend([
        "",
        "Disproof to watch:",
    ])
    for item in review.decision_cockpit.disproof_to_watch:
        lines.append(f"- {item}")
    if review.decision_cockpit.job_signals:
        lines.extend(["", "Top job/SKU signals:"])
        for item in review.decision_cockpit.job_signals[:5]:
            label = item.get("label") or item.get("job_id") or "unknown job"
            lines.append(
                f"- {label}: OEE {item.get('avg_oee', 'n/a')}, performance {item.get('avg_performance', 'n/a')}, "
                f"target gap {item.get('target_gap_units', 'n/a')} units"
            )
    if review.decision_cockpit.sku_signals:
        lines.extend(["", "Top SKU rollups:"])
        for item in review.decision_cockpit.sku_signals[:5]:
            lines.append(
                f"- SKU {item.get('sku')}: {item.get('jobs', 0)} jobs, performance {item.get('avg_performance', 'n/a')}, "
                f"target gap {item.get('target_gap_units', 'n/a')} units"
            )
    lines.extend([
        "",
        "## Operating Model",
        "",
        f"- Best recorded signal: {review.operating_model.recorded_signal}",
        f"- Interpretation: {review.operating_model.interpretation}",
        f"- Decision rule: {review.operating_model.decision_rule}",
        f"- Dashboard gap: {review.operating_model.dashboard_gap}",
        "",
        "Duration/capture profile:",
    ])
    for bucket in review.operating_model.duration_profile:
        lines.append(
            f"- {bucket['bucket']}: {bucket['events']:,} events, {bucket['hours']:.1f}h, "
            f"{bucket['generic_events']:,} generic events"
        )
    lines.extend(["", "Attribution risks:"])
    for item in review.operating_model.attribution_risks:
        lines.append(f"- {item}")
    lines.extend(["", "Cause-class map:"])
    for item in review.operating_model.cause_classes:
        evidence = "; ".join(item.get("evidence", [])[:2])
        lines.append(f"- {item['class']}: {item['read']} ({evidence})")
    lines.extend(["", "Leadership actions:"])
    for action in review.operating_model.leadership_actions:
        lines.append(f"- {action['owner']} / {action['due']}: {action['action']}")
    lines.extend([
        "",
        "## Visibility Loss",
        "",
        f"- Short Stops: {review.short_stop_events:,} events / {review.short_stop_hours:.1f} hours",
        f"- Unassigned: {review.unassigned_events:,} events / {review.unassigned_hours:.1f} hours",
        f"- Verdict: {review.visibility_verdict}",
        f"- Masking read: {review.masking_summary}",
        "",
        "## Actionable Constraint Candidates",
        "",
    ])
    for item in review.actionable_constraints[:5]:
        lines.append(
            f"- {item.name}: {item.events:,} events, {item.downtime_hours:.1f} hours, "
            f"MTBF {item.mtbf_minutes:.1f} min, repeat {item.repeat_failure_rate:.1%}"
            if item.mtbf_minutes is not None else
            f"- {item.name}: {item.events:,} events, {item.downtime_hours:.1f} hours, repeat {item.repeat_failure_rate:.1%}"
        )
        if item.members:
            lines.append(f"  - Includes: {', '.join(item.members[:6])}")
        shift_hours = sorted(item.by_shift.items(), key=lambda row: row[1].get("hours", 0), reverse=True)
        if shift_hours:
            lines.append(
                "  - Shift hours: "
                + ", ".join(f"{shift} {vals.get('hours', 0):.1f}h" for shift, vals in shift_hours)
            )

    lines.extend([
        "",
        "## Maintenance Questions",
        "",
    ])
    for question in review.maintenance_questions[:8]:
        lines.append(f"- {question}")
    lines.extend([
        "",
        "## Top Codes",
        "",
    ])
    for code, events, hours, event_share in review.top_codes[:10]:
        lines.append(f"- {code}: {events:,} events, {hours:.1f} hours, {event_share:.1%} of events")

    lines.extend(["", "## Role Briefs", ""])
    for brief in review.role_briefs:
        lines.extend([f"### {brief.role}", "", f"**Focus:** {brief.focus}", "", brief.verdict, ""])
        lines.append("Actions:")
        for action in brief.actions:
            lines.append(f"- {action}")
        lines.append("")
        lines.append("Evidence:")
        for item in brief.evidence:
            lines.append(f"- {item}")
        lines.append("")

    lines.extend(["## Context", "", review.context_summary])
    if review.photo_summary:
        lines.extend(["", review.photo_summary])
    return "\n".join(lines).strip() + "\n"


def _select_line_events(events: list[DowntimeEvent], line_hint: str | None) -> list[DowntimeEvent]:
    if not line_hint:
        line_id = Counter(event.line_id for event in events).most_common(1)[0][0]
        return [event for event in events if event.line_id == line_id]

    hint = line_hint.strip().lower()
    matched = [
        event for event in events
        if hint in event.line_id.lower() or hint in event.line_raw_name.lower()
    ]
    return matched


def _is_short_stop(event: DowntimeEvent) -> bool:
    name = event.equipment_raw_name.lower()
    return any(term in name for term in SHORT_STOP_TERMS)


def _is_unassigned(event: DowntimeEvent) -> bool:
    name = event.equipment_raw_name.lower()
    return any(term in name for term in UNASSIGNED_TERMS)


def _sum_hours(events: list[DowntimeEvent]) -> float:
    return sum(event.duration_seconds for event in events) / 3600.0


def _visibility_score(short_rate: float, unassigned_rate: float) -> int:
    penalty = min(85, round((short_rate * 45) + (unassigned_rate * 70)))
    return max(0, 100 - penalty)


def _visibility_verdict(score: int, short_rate: float, unassigned_rate: float) -> str:
    combined = short_rate + unassigned_rate
    if score < 55:
        return (
            "The line has a visibility problem before it has a clean Pareto problem. "
            f"{combined:.1%} of events are Short Stop or Unassigned, so the current data is masking the real constraint."
        )
    if score < 75:
        return (
            "The line has usable data, but Short Stop and Unassigned are still large enough "
            "to distort the improvement priority."
        )
    return "The line has enough event fidelity to move directly into equipment/process RCA."


def _management_signal(score: int, short_rate: float, unassigned_rate: float) -> str:
    if score < 55:
        return (
            "Treat this as a production management and CI control issue. The first countermeasure is not "
            "a mechanical fix; it is restoring event fidelity so supervisors, operators, and CI can see "
            "which machine, product, condition, or habit is actually creating the loss."
        )
    if unassigned_rate >= 0.08:
        return (
            "Unassigned downtime is high enough to require supervisor standard work: audit coding, coach the line, "
            "and make uncoded stops visible in the daily meeting until the rate drops."
        )
    if short_rate >= 0.15:
        return (
            "Short Stops are high enough to require a micro-stop study. Separate true mechanical interruptions "
            "from operator coding behavior before launching a full CI project."
        )
    return "The event coding is serviceable. Use the top repeat equipment and shift patterns to choose the next CI target."


def _top_codes(events: list[DowntimeEvent]) -> list[tuple[str, int, float, float]]:
    counts = Counter(event.equipment_raw_name or "Unknown" for event in events)
    hours: dict[str, float] = defaultdict(float)
    for event in events:
        hours[event.equipment_raw_name or "Unknown"] += event.duration_seconds / 3600.0
    total_events = len(events)
    return [
        (code, count, hours[code], count / max(total_events, 1))
        for code, count in counts.most_common()
    ]


def _monthly_metrics(events: list[DowntimeEvent], oee: list[OEEInterval]) -> list[MonthlyLineMetric]:
    months = sorted({_month_label(event.start_time) for event in events})
    rows: list[MonthlyLineMetric] = []
    for month in months:
        month_events = [event for event in events if _month_label(event.start_time) == month]
        month_oee = [row.oee for row in oee if _month_label(row.timestamp) == month and row.oee is not None]
        short = [event for event in month_events if _is_short_stop(event)]
        unassigned = [event for event in month_events if _is_unassigned(event)]
        avg_oee = sum(month_oee) / len(month_oee) if month_oee else None
        rows.append(MonthlyLineMetric(
            month=month,
            event_count=len(month_events),
            downtime_hours=_sum_hours(month_events),
            short_stop_events=len(short),
            short_stop_hours=_sum_hours(short),
            unassigned_events=len(unassigned),
            unassigned_hours=_sum_hours(unassigned),
            avg_oee=avg_oee,
        ))
    return rows


def _shift_visibility(events: list[DowntimeEvent]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for shift in ("1st", "2nd", "3rd"):
        shift_events = [event for event in events if _shift_for(event.start_time) == shift]
        short = [event for event in shift_events if _is_short_stop(event)]
        unassigned = [event for event in shift_events if _is_unassigned(event)]
        out[shift] = {
            "events": float(len(shift_events)),
            "short_stop_rate": len(short) / max(len(shift_events), 1),
            "unassigned_rate": len(unassigned) / max(len(shift_events), 1),
            "downtime_hours": _sum_hours(shift_events),
        }
    return out


def _role_briefs(review: LineReview) -> list[RoleBrief]:
    combined_hours = review.short_stop_hours + review.unassigned_hours
    top_real = review.actionable_constraints[0].name if review.actionable_constraints else next(
        (code for code, _, _, _ in review.top_codes if not _looks_like_visibility_code(code)),
        review.top_codes[0][0] if review.top_codes else "unknown",
    )
    worst_shift = max(
        review.shift_visibility.items(),
        key=lambda item: item[1]["short_stop_rate"] + item[1]["unassigned_rate"],
    )[0]

    evidence = [
        f"{review.short_stop_events:,} Short Stop events and {review.unassigned_events:,} Unassigned events.",
        f"{combined_hours:.1f} hours are tied to weak diagnostic categories.",
        review.masking_summary,
        f"Worst shift visibility: {worst_shift}.",
    ]
    visibility_is_weak = review.visibility_score < 75

    return [
        RoleBrief(
            role="Production Supervisor",
            focus="Current-shift event discipline and passdown quality.",
            verdict=(
                "The supervisor job is to make the next stop diagnosable. If Short Stops and Unassigned stay loose, "
                "the next shift inherits noise instead of a fixable problem."
                if visibility_is_weak else
                "The event coding is usable. The supervisor job is to keep passdown specific enough that repeat conditions do not blur into generic downtime."
            ),
            actions=[
                (
                    "Audit every Unassigned stop over the local threshold before end-of-shift passdown."
                    if visibility_is_weak else
                    "Keep auditing exceptions so Unassigned does not become an accepted escape code."
                ),
                (
                    "Require operators to attach machine/area and condition language to repeat Short Stops."
                    if visibility_is_weak else
                    "Keep operator notes tied to machine area, condition, and recovery action."
                ),
                f"Watch {top_real} first, but do not let it absorb generic Short Stop coding.",
                "Pass down the top recurring condition, not only total downtime.",
            ],
            evidence=evidence,
        ),
        RoleBrief(
            role="Production Manager",
            focus="Daily control, accountability, and schedule risk.",
            verdict=(
                "The production management issue is control-loop weakness. The line is losing management attention "
                "because too many events are not being converted into accountable causes."
                if visibility_is_weak else
                "The production management issue can move from data discipline to performance control. The line has enough cause detail to review schedule risk and repeat constraints."
            ),
            actions=[
                (
                    "Make Short Stop and Unassigned rates daily meeting metrics for two weeks."
                    if visibility_is_weak else
                    "Keep Short Stop and Unassigned rates visible as control metrics, not primary projects."
                ),
                (
                    "Set a supervisor standard: uncoded downtime must be explained before the shift closes."
                    if visibility_is_weak else
                    "Use the existing event fidelity to challenge repeat losses in the daily direction setting."
                ),
                "Review the worst-shift pattern with supervisors before launching equipment work orders.",
                "Separate schedule loss from data loss so the line does not chase the wrong Pareto.",
            ],
            evidence=evidence,
        ),
        RoleBrief(
            role="CI Manager",
            focus="Recurring loss conversion into RCA and verified countermeasures.",
            verdict=(
                "The first CI project is event-fidelity recovery. The second project is the constraint that appears "
                "only after Short Stops and Unassigned are tied to validated cause classes."
                if visibility_is_weak else
                "The line has enough event fidelity to start a targeted RCA on the top repeat constraint while keeping coding compliance on the control plan."
            ),
            actions=[
                (
                    "Run a 14-day event-fidelity sprint with clear coding rules and daily audit."
                    if visibility_is_weak else
                    "Start the RCA on the top repeat constraint and keep event fidelity as a control metric."
                ),
                (
                    "Create a Pareto before and after the sprint to expose the validated cause-class split."
                    if visibility_is_weak else
                    "Use monthly trend and shift pattern evidence to decide whether the issue is equipment, startup, product, or staffing related."
                ),
                f"Prepare an RCA starter for {top_real}, but mark confidence as provisional until coding improves.",
                "Schedule 7/30/90-day verification on both coding compliance and downtime reduction.",
            ],
            evidence=evidence,
        ),
    ]


def _looks_like_visibility_code(code: str) -> bool:
    lower = code.lower()
    return any(term in lower for term in SHORT_STOP_TERMS + UNASSIGNED_TERMS)


def _looks_like_non_actionable_code(code: str) -> bool:
    lower = code.lower()
    return any(term in lower for term in SHORT_STOP_TERMS + UNASSIGNED_TERMS + SCHEDULE_LOSS_TERMS)


def _actionable_constraints(events: list[DowntimeEvent]) -> list[ActionableConstraint]:
    groups: dict[str, list[DowntimeEvent]] = defaultdict(list)
    for event in events:
        if _looks_like_non_actionable_code(event.equipment_raw_name):
            continue
        groups[_equipment_family(event.equipment_raw_name)].append(event)

    constraints = [
        _constraint_from_events(name, grouped)
        for name, grouped in groups.items()
        if grouped
    ]
    constraints.sort(key=lambda item: (item.downtime_hours, item.events, item.repeat_failure_rate), reverse=True)
    return constraints


def _constraint_from_events(name: str, events: list[DowntimeEvent]) -> ActionableConstraint:
    sorted_events = sorted(events, key=lambda event: event.start_time)
    total_seconds = sum(event.duration_seconds for event in sorted_events)
    gaps: list[float] = []
    repeats = 0
    for previous, current in zip(sorted_events, sorted_events[1:]):
        gap = (current.start_time - previous.end_time).total_seconds() / 60.0
        if gap >= 0:
            gaps.append(gap)
        if 0 <= gap <= 30:
            repeats += 1
    by_shift: dict[str, dict[str, float]] = {}
    for shift in ("1st", "2nd", "3rd"):
        shift_events = [event for event in sorted_events if _shift_for(event.start_time) == shift]
        by_shift[shift] = {
            "events": float(len(shift_events)),
            "hours": _sum_hours(shift_events),
        }
    by_month: dict[str, dict[str, float]] = {}
    for month in sorted({_month_label(event.start_time) for event in sorted_events}):
        month_events = [event for event in sorted_events if _month_label(event.start_time) == month]
        by_month[month] = {
            "events": float(len(month_events)),
            "hours": _sum_hours(month_events),
        }
    members = [code for code, _ in Counter(event.equipment_raw_name for event in sorted_events).most_common()]
    downtime_hours = total_seconds / 3600.0
    return ActionableConstraint(
        name=name,
        events=len(sorted_events),
        downtime_hours=downtime_hours,
        avg_duration_minutes=(total_seconds / 60.0 / len(sorted_events)) if sorted_events else 0.0,
        mtbf_minutes=median(gaps) if gaps else None,
        repeat_failure_rate=repeats / max(len(sorted_events) - 1, 1) if len(sorted_events) > 1 else 0.0,
        members=members,
        by_shift=by_shift,
        by_month=by_month,
        maintenance_questions=_constraint_questions(name, members, by_shift),
    )


def _equipment_family(name: str) -> str:
    text = name.lower()
    if "caser" in text:
        return "Caser family"
    if "conveyor" in text:
        return "Conveyor family"
    if "wrapper" in text or "wrap" in text or "tunnel" in text:
        return "Wrapper/Shrink family"
    if "printer" in text or "print" in text or "code" in text or "diagraph" in text or "squid" in text:
        return "Coding/Printer family"
    if "shiner" in text or "xray" in text or "detector" in text or "fil-tech" in text:
        return "Inspection family"
    if "pallet" in text or "sheet" in text or "layer" in text or "chep" in text:
        return "Palletizing/Layer family"
    if "tray" in text or "kayat" in text:
        return "Tray/Kayat family"
    if "depal" in text:
        return "Depal family"
    clean = name.strip()
    return clean or "Unknown"


def _masking_summary(
    short_events: list[DowntimeEvent],
    unassigned_events: list[DowntimeEvent],
    constraints: list[ActionableConstraint],
) -> str:
    generic_hours = _sum_hours(short_events) + _sum_hours(unassigned_events)
    if constraints:
        top = constraints[0]
        return (
            f"Short Stop/Unassigned are symptom buckets ({generic_hours:.1f}h), not root causes. "
            f"The strongest recorded actionable signal is {top.name} at {top.downtime_hours:.1f}h, "
            "but it still requires floor validation before it becomes the true cause."
        )
    return (
        f"Short Stop/Unassigned are symptom buckets ({generic_hours:.1f}h), but no actionable equipment family was visible."
    )


def _operating_model(
    events: list[DowntimeEvent],
    constraints: list[ActionableConstraint],
    short_events: list[DowntimeEvent],
    unassigned_events: list[DowntimeEvent],
    context: str,
) -> OperatingModel:
    """Build a plant-floor operating model around the recorded MES signal."""
    recorded_signal = constraints[0].name if constraints else _best_non_generic_code(events)
    generic_events = short_events + unassigned_events
    generic_rate = len(generic_events) / max(len(events), 1)
    duration_profile = _duration_profile(events)
    duration_bias = _duration_bias(duration_profile, generic_events)
    attribution_risks = _attribution_risks(events, constraints, generic_rate, context)
    flow_hypotheses = _flow_hypotheses(events, context)
    cause_classes = _cause_class_map(events, constraints, generic_events, context)
    evidence_gaps = _evidence_gaps(generic_rate, context)
    leadership_actions = _leadership_actions(recorded_signal, generic_rate, cause_classes)

    interpretation = (
        f"{recorded_signal} is the best recorded signal, not a proven root cause. "
        "Use it as the observation target while separating equipment failure from flow/handoff, "
        "person/process, material, setup/speed, and data-capture effects."
    )
    decision_rule = (
        "Do not approve a mechanical RCA or major work order until the next observed stops connect "
        "the recorded signal to a verified physical cause class. If observations split across flow "
        "states or operator actions, treat the problem as an operating-system issue before treating it "
        "as equipment failure."
    )
    dashboard_gap = (
        "The BI layer can show recorded codes and drilldowns, but it does not by itself preserve "
        "duration threshold, initial Unassigned state, operator recovery action, line-flow state, "
        "or whether the coded area is the source of the interruption or only where it became visible."
    )
    return OperatingModel(
        recorded_signal=recorded_signal,
        interpretation=interpretation,
        duration_profile=duration_profile,
        duration_bias=duration_bias,
        attribution_risks=attribution_risks,
        flow_hypotheses=flow_hypotheses,
        cause_classes=cause_classes,
        evidence_gaps=evidence_gaps,
        leadership_actions=leadership_actions,
        decision_rule=decision_rule,
        dashboard_gap=dashboard_gap,
    )


def _duration_profile(events: list[DowntimeEvent]) -> list[dict[str, Any]]:
    buckets = [
        ("under 2 min", lambda minutes: minutes < 2),
        ("2-3 min", lambda minutes: 2 <= minutes < 3),
        ("3-5 min", lambda minutes: 3 <= minutes < 5),
        ("5+ min", lambda minutes: minutes >= 5),
    ]
    rows: list[dict[str, Any]] = []
    for label, predicate in buckets:
        bucket_events = [event for event in events if predicate(event.duration_seconds / 60.0)]
        generic = [event for event in bucket_events if _looks_like_visibility_code(event.equipment_raw_name)]
        rows.append({
            "bucket": label,
            "events": len(bucket_events),
            "hours": round(_sum_hours(bucket_events), 2),
            "event_share": round(len(bucket_events) / max(len(events), 1), 4),
            "generic_events": len(generic),
            "generic_hours": round(_sum_hours(generic), 2),
        })
    return rows


def _duration_bias(duration_profile: list[dict[str, Any]], generic_events: list[DowntimeEvent]) -> list[str]:
    under_three = sum(
        int(row["events"]) for row in duration_profile
        if row["bucket"] in {"under 2 min", "2-3 min"}
    )
    five_plus_generic = next(
        (int(row["generic_events"]) for row in duration_profile if row["bucket"] == "5+ min"),
        0,
    )
    out = [
        "Stops below the local registration threshold may be missing from the dataset, so chronic micro-loss can be undercounted.",
        "Longer stops are more likely to become named events, so the Pareto can overrepresent losses that last long enough to be classified.",
    ]
    if under_three:
        out.append(f"{under_three:,} recorded events are under 3 minutes; similar unrecorded events may exist below the capture threshold.")
    if five_plus_generic:
        out.append(f"{five_plus_generic:,} generic events are 5+ minutes; these should be audit targets because they lasted long enough to demand attribution.")
    if generic_events:
        out.append("Short Stop and Unassigned should be treated as event-state transitions, not final causes.")
    return out


def _attribution_risks(
    events: list[DowntimeEvent],
    constraints: list[ActionableConstraint],
    generic_rate: float,
    context: str,
) -> list[str]:
    text = _combined_text(events, context)
    top = constraints[0].name if constraints else "the top recorded family"
    risks = [
        f"{top} may be the best recorded signal, but it is not a proven root cause or physical source of the interruption.",
        "The system may assign the visible fault after a delay, while the actual cause occurred upstream, downstream, or during recovery.",
    ]
    if generic_rate >= 0.25:
        risks.append(f"Generic visibility loss is high ({generic_rate:.1%} of events), so code rank is less trustworthy than observed flow state.")
    if any(term in text for term in ("operator", "person", "poorly", "coded", "unassigned")):
        risks.append("Some recorded faults may reflect operator/process response or coding behavior rather than machine failure.")
    if any(term in text for term in ("pallet", "depal", "label", "conveyor", "flow", "outrun", "starv", "block")):
        risks.append("Flow imbalance can make the stop visible at one machine even when the source is product flow, palletizer/depal/labeling, or a handoff.")
    return risks


def _flow_hypotheses(events: list[DowntimeEvent], context: str) -> list[str]:
    text = _combined_text(events, context)
    hypotheses: list[str] = []
    if any(term in text for term in ("pallet", "layer", "sheet")):
        hypotheses.append("Palletizer/layer handling may be blocking, starving, or assigning the final fault after the line has already stopped.")
    if any(term in text for term in ("depal", "depallet")):
        hypotheses.append("Depal interruptions can present as downstream product-flow instability rather than clean depal downtime.")
    if any(term in text for term in ("label", "printer", "print", "code", "diagraph", "squid")):
        hypotheses.append("Labeling/coding issues can interrupt product release and appear as flow stoppage instead of a clean equipment root cause.")
    if any(term in text for term in ("caser", "carton", "flap", "mispick", "prime")):
        hypotheses.append("Caser-area symptoms may involve carton/flap handling, setup, material, or handoff timing; do not assume mechanical failure without observation.")
    if any(term in text for term in ("conveyor", "flow", "outrun", "starv", "block", "jam")):
        hypotheses.append("Line-flow imbalance may be the true operating constraint: one area outruns, starves, or blocks another without a single pinpointable failure.")
    if not hypotheses:
        hypotheses.append("No clear flow-state clue is present yet; require observation notes on where product stopped, where it backed up, and what restarted the line.")
    return hypotheses


def _cause_class_map(
    events: list[DowntimeEvent],
    constraints: list[ActionableConstraint],
    generic_events: list[DowntimeEvent],
    context: str,
) -> list[dict[str, Any]]:
    text = _combined_text(events, context)
    classes = [
        _cause_class(
            "Data/Capture",
            bool(generic_events),
            "The recorded code is an incomplete state, not a cause.",
            [
                f"{len(generic_events):,} Short Stop/Unassigned events",
                "duration thresholds can suppress or delay attribution",
            ],
            "Audit generic stops by duration bucket and require area/flow/recovery notes.",
        ),
        _cause_class(
            "Flow/Handoff",
            any(term in text for term in ("pallet", "depal", "label", "conveyor", "flow", "outrun", "starv", "block", "jam")),
            "The line may be stopping because product flow is blocked, starved, or imbalanced.",
            _evidence_terms(text, {
                "palletizer/layer": ("pallet", "layer", "sheet"),
                "depal": ("depal", "depallet"),
                "labeling/coding": ("label", "printer", "print", "code"),
                "flow/jam": ("flow", "conveyor", "jam", "outrun", "starv", "block"),
            }),
            "Observe where product backs up or disappears before assigning the fault to the visible machine.",
        ),
        _cause_class(
            "Person/Process",
            any(term in text for term in ("operator", "person", "coded", "poorly", "unassigned", "passdown", "clearing")),
            "The loss may be driven by recovery behavior, coding practice, or operator response.",
            _evidence_terms(text, {
                "operator/person": ("operator", "person"),
                "coding/passdown": ("coded", "coding", "unassigned", "passdown"),
                "recovery": ("clearing", "restart", "reset"),
            }),
            "Capture operator action at restart and separate process behavior from equipment condition.",
        ),
        _cause_class(
            "Material/Packaging",
            any(term in text for term in ("flap", "glue", "fiber", "carton", "mispick", "prime", "material")),
            "Packaging or material behavior may be creating the visible stop.",
            _evidence_terms(text, {
                "flap/glue": ("flap", "glue"),
                "fiber/carton": ("fiber", "carton"),
                "mispick/prime": ("mispick", "prime"),
            }),
            "Check carton/fiber/glue condition, lot/SKU pattern, and machine dwell/speed relationship.",
        ),
        _cause_class(
            "Setup/Speed",
            any(term in text for term in ("speed", "dwell", "setup", "centerline", "startup", "timing")),
            "A setting, speed, dwell, or startup condition may be creating repeat interruptions.",
            _evidence_terms(text, {
                "speed/dwell": ("speed", "dwell"),
                "setup/timing": ("setup", "centerline", "startup", "timing"),
            }),
            "Compare settings at good vs bad runs before changing maintenance priority.",
        ),
    ]
    if constraints:
        top = constraints[0]
        classes.append(_cause_class(
            "Equipment/Mechanical",
            True,
            f"{top.name} is the strongest recorded equipment-family signal, but it still needs physical verification.",
            [f"{top.events:,} events", f"{top.downtime_hours:.1f} downtime hours", f"{top.repeat_failure_rate:.1%} repeat rate"],
            "Verify whether the coded family is source, symptom, or recovery point before launching mechanical RCA.",
        ))
    classes.append(_cause_class(
        "Unknown/No Pinpoint",
        len(generic_events) > 0,
        "Some short stops may remain real product-flow interruptions with no pinpointable source from current data.",
        ["generic stop buckets remain present"],
        "Use direct observation and short-interval notes; do not force a false root cause.",
    ))
    classes.sort(key=lambda item: (item["active"], item["weight"]), reverse=True)
    return classes


def _cause_class(
    name: str,
    active: bool,
    read: str,
    evidence: list[str],
    next_check: str,
) -> dict[str, Any]:
    evidence = [item for item in evidence if item]
    return {
        "class": name,
        "active": active,
        "weight": len(evidence) + (2 if active else 0),
        "read": read if active else f"Not enough current evidence for {name.lower()} as a primary cause class.",
        "evidence": evidence or ["no direct evidence yet"],
        "next_check": next_check,
    }


def _evidence_terms(text: str, groups: dict[str, tuple[str, ...]]) -> list[str]:
    return [
        label for label, terms in groups.items()
        if any(term in text for term in terms)
    ]


def _evidence_gaps(generic_rate: float, context: str) -> list[str]:
    gaps = [
        "For each generic stop: actual area, product-flow state, operator action, duration bucket, and restart condition.",
        "Whether the coded area is source of the interruption, visible symptom, or recovery point.",
        "What changed immediately before the stop: speed, dwell/setup, material, SKU, staffing, or upstream/downstream flow.",
    ]
    if generic_rate >= 0.25:
        gaps.append("A daily audit of Short Stop/Unassigned conversion from initial state to final code.")
    if not context.strip():
        gaps.append("Plant-specific event-capture rules from TrakSYS/Incorta/Power BI are missing.")
    return gaps


def _leadership_actions(
    recorded_signal: str,
    generic_rate: float,
    cause_classes: list[dict[str, Any]],
) -> list[dict[str, str]]:
    active_classes = [
        item["class"] for item in cause_classes
        if item.get("active")
    ][:4]
    action_suffix = ", ".join(active_classes) if active_classes else "equipment, flow, person/process, material, setup, unknown"
    actions = [
        {
            "owner": "Supervisor",
            "due": "next shift",
            "action": "Observe and log the next 10 generic stops with area, flow state, operator action, duration bucket, and restart condition.",
        },
        {
            "owner": "Maintenance lead",
            "due": "same day",
            "action": f"Validate whether {recorded_signal} is source, symptom, or recovery point before creating mechanical work scope.",
        },
        {
            "owner": "Production manager",
            "due": "daily meeting",
            "action": f"Review cause-class split ({action_suffix}) before approving RCA priority or speed/flow changes.",
        },
        {
            "owner": "CI manager",
            "due": "14 days",
            "action": "Compare pre/post Pareto after observation notes are added; promote only validated cause classes into RCA.",
        },
    ]
    if generic_rate >= 0.25:
        actions.insert(1, {
            "owner": "Line lead",
            "due": "each shift close",
            "action": "Convert long Unassigned stops into an observed cause class before passdown is accepted.",
        })
    return actions


def _best_non_generic_code(events: list[DowntimeEvent]) -> str:
    for code, _, _, _ in _top_codes(events):
        if not _looks_like_non_actionable_code(code):
            return code
    return "No strong recorded signal"


def _combined_text(events: list[DowntimeEvent], context: str) -> str:
    codes = " ".join(event.equipment_raw_name or "" for event in events)
    notes = " ".join(event.notes or "" for event in events if event.notes)
    return f"{context} {codes} {notes}".lower()


def _decision_cockpit(
    events: list[DowntimeEvent],
    oee: list[OEEInterval],
    constraints: list[ActionableConstraint],
    short_events: list[DowntimeEvent],
    unassigned_events: list[DowntimeEvent],
    operating_model: OperatingModel,
) -> DecisionCockpit:
    top = constraints[0] if constraints else None
    target = _target_attainment(oee)
    job_signals = _job_signals(oee)
    sku_signals = _sku_signals(oee)
    generic_rate = (len(short_events) + len(unassigned_events)) / max(len(events), 1)
    confidence = _cockpit_confidence(top, generic_rate, target, job_signals)
    suspected = top.name if top else "Unknown"
    target_status = _target_status(target)
    sku_status = _sku_status(sku_signals, job_signals)
    decision = (
        f"Verify {suspected} as the best recorded signal; classify whether the true cause is equipment, "
        "flow/handoff, person/process, material, setup/speed, or unknown before opening a mechanical RCA."
        if top else
        "Do not launch equipment RCA yet; first restore event coding and observe where generic stops physically occur."
    )
    next_rule = (
        f"For the next 3-5 shifts, every Short Stop or Unassigned event must record actual area, flow state, "
        f"operator action, duration bucket, and whether it occurred at {suspected}; also flag active SKU/job target status."
        if top else
        "For the next 3-5 shifts, every Short Stop must record actual area, flow state, operator action, active SKU/job, and whether the line was at target."
    )
    proof = [
        f"Observed generic stops physically land at {suspected} more often than any other area and the same cause class repeats."
        if top else
        "Generic Short Stop observations consistently land in one physical area.",
        f"The observed cause class matches the recorded signal: {operating_model.recorded_signal}.",
        "Below-target jobs/SKUs overlap with the suspected constraint more than at-target jobs/SKUs.",
    ]
    disproof = [
        f"Short Stops distribute across several flow states instead of concentrating at {suspected}."
        if top else
        "Short Stops distribute across several areas with no repeatable pattern.",
        "The recorded signal is mostly where flow disruption becomes visible, not where the interruption originates.",
        "Below-target performance tracks product/job mix or startup conditions more strongly than the suspected equipment family.",
    ]
    return DecisionCockpit(
        suspected_constraint=suspected,
        confidence=confidence,
        decision=decision,
        target_status=target_status,
        sku_status=sku_status,
        next_observation_rule=next_rule,
        proof_to_seek=proof,
        disproof_to_watch=disproof,
        target_attainment=target,
        job_signals=job_signals,
        sku_signals=sku_signals,
    )


def _target_attainment(oee: list[OEEInterval]) -> dict[str, Any]:
    rows = [
        row for row in oee
        if row.performance is not None or row.target_units is not None or row.actual_calculation_units is not None
    ]
    if not rows:
        return {
            "intervals": 0,
            "avg_performance": None,
            "below_target_intervals": 0,
            "below_target_rate": None,
            "target_gap_units": None,
            "rate_loss_hours": None,
        }
    perf_rows = [row for row in rows if row.performance is not None]
    below = [row for row in perf_rows if row.performance is not None and row.performance < 0.95]
    actual_units = sum(row.actual_calculation_units or 0.0 for row in rows)
    target_units = sum(row.target_units or 0.0 for row in rows)
    rate_loss_seconds = sum(row.rate_loss_seconds or 0.0 for row in rows)
    target_gap = max(target_units - actual_units, 0.0) if target_units > 0 and actual_units > 0 else None
    return {
        "intervals": len(rows),
        "avg_performance": round(sum(row.performance for row in perf_rows if row.performance is not None) / len(perf_rows), 4)
        if perf_rows else None,
        "below_target_intervals": len(below),
        "below_target_rate": round(len(below) / len(perf_rows), 4) if perf_rows else None,
        "target_gap_units": round(target_gap, 1) if target_gap is not None else None,
        "rate_loss_hours": round(rate_loss_seconds / 3600.0, 2) if rate_loss_seconds else None,
    }


def _job_signals(oee: list[OEEInterval]) -> list[dict[str, Any]]:
    grouped: dict[str, list[OEEInterval]] = defaultdict(list)
    labels: dict[str, str] = {}
    for row in oee:
        if not row.job_id and not row.job_label:
            continue
        if row.job_label and _looks_like_hour_label(row.job_label):
            continue
        key = row.job_id or row.job_label or "unknown"
        grouped[key].append(row)
        labels[key] = row.job_label or key

    out: list[dict[str, Any]] = []
    for key, rows in grouped.items():
        perf = [row.performance for row in rows if row.performance is not None]
        oee_vals = [row.oee for row in rows if row.oee is not None]
        target_units = sum(row.target_units or 0.0 for row in rows)
        actual_units = sum(row.actual_calculation_units or 0.0 for row in rows)
        rate_loss_seconds = sum(row.rate_loss_seconds or 0.0 for row in rows)
        target_gap = max(target_units - actual_units, 0.0) if target_units > 0 and actual_units > 0 else None
        out.append({
            "job_id": key,
            "label": _compact_job_label(labels[key]),
            "sku": _extract_sku(labels[key]),
            "intervals": len(rows),
            "avg_oee": round(sum(oee_vals) / len(oee_vals), 4) if oee_vals else None,
            "avg_performance": round(sum(perf) / len(perf), 4) if perf else None,
            "target_gap_units": round(target_gap, 1) if target_gap is not None else None,
            "rate_loss_hours": round(rate_loss_seconds / 3600.0, 2) if rate_loss_seconds else None,
        })
    out.sort(
        key=lambda row: (
            row["target_gap_units"] or 0,
            row["rate_loss_hours"] or 0,
            -(row["avg_performance"] or 1),
        ),
        reverse=True,
    )
    return out[:10]


def _sku_signals(oee: list[OEEInterval]) -> list[dict[str, Any]]:
    grouped: dict[str, list[OEEInterval]] = defaultdict(list)
    job_ids: dict[str, set[str]] = defaultdict(set)
    for row in oee:
        label = row.job_label or ""
        if not label or _looks_like_hour_label(label):
            continue
        sku = _extract_sku(label)
        if not sku:
            continue
        grouped[sku].append(row)
        if row.job_id:
            job_ids[sku].add(row.job_id)

    out: list[dict[str, Any]] = []
    for sku, rows in grouped.items():
        perf = [row.performance for row in rows if row.performance is not None]
        oee_vals = [row.oee for row in rows if row.oee is not None]
        target_units = sum(row.target_units or 0.0 for row in rows)
        actual_units = sum(row.actual_calculation_units or 0.0 for row in rows)
        rate_loss_seconds = sum(row.rate_loss_seconds or 0.0 for row in rows)
        target_gap = max(target_units - actual_units, 0.0) if target_units > 0 and actual_units > 0 else None
        out.append({
            "sku": sku,
            "jobs": len(job_ids[sku]) or len(rows),
            "intervals": len(rows),
            "avg_oee": round(sum(oee_vals) / len(oee_vals), 4) if oee_vals else None,
            "avg_performance": round(sum(perf) / len(perf), 4) if perf else None,
            "target_gap_units": round(target_gap, 1) if target_gap is not None else None,
            "rate_loss_hours": round(rate_loss_seconds / 3600.0, 2) if rate_loss_seconds else None,
        })
    out.sort(
        key=lambda row: (
            row["target_gap_units"] or 0,
            row["rate_loss_hours"] or 0,
            -(row["avg_performance"] or 1),
        ),
        reverse=True,
    )
    return out[:10]


def _cockpit_confidence(
    top: ActionableConstraint | None,
    generic_rate: float,
    target: dict[str, Any],
    job_signals: list[dict[str, Any]],
) -> str:
    if not top:
        return "low - no actionable equipment family is visible yet"
    reasons = []
    level = "medium"
    if generic_rate >= 0.5:
        level = "provisional"
        reasons.append("generic stop coding is still high")
    if top.repeat_failure_rate >= 0.35:
        reasons.append("repeat signal is strong")
    if job_signals:
        reasons.append("job/SKU target context is available")
    elif target.get("intervals"):
        reasons.append("target context is available but not job/SKU-specific")
    else:
        reasons.append("target/SKU context is missing")
    return f"{level} - " + "; ".join(reasons)


def _target_status(target: dict[str, Any]) -> str:
    intervals = int(target.get("intervals") or 0)
    if intervals == 0:
        return "No target-attainment data was available; add OEE target/rate fields before regression."
    avg = target.get("avg_performance")
    below = target.get("below_target_rate")
    gap = target.get("target_gap_units")
    parts = [f"{intervals} OEE rows include target/performance context"]
    if avg is not None:
        parts.append(f"avg performance {avg:.1%}")
    if below is not None:
        parts.append(f"{below:.1%} below 95% performance")
    if gap is not None:
        parts.append(f"{gap:,.0f} calculation-unit target gap")
    return "; ".join(parts) + "."


def _sku_status(sku_signals: list[dict[str, Any]], job_signals: list[dict[str, Any]]) -> str:
    if sku_signals:
        top = sku_signals[0]
        perf = top.get("avg_performance")
        perf_text = f" at {perf:.1%} performance" if isinstance(perf, float) else ""
        return (
            f"{len(sku_signals)} SKU rollups were detected; largest target gap is "
            f"SKU {top.get('sku')} across {top.get('jobs')} jobs{perf_text}."
        )
    if not job_signals:
        return "No job/SKU labels were available; require job export or schedule join for SKU-level decisions."
    top = job_signals[0]
    label = top.get("label") or top.get("job_id") or "top job"
    perf = top.get("avg_performance")
    perf_text = f" at {perf:.1%} performance" if isinstance(perf, float) else ""
    return f"{len(job_signals)} job/SKU signals were detected; largest target gap is {label}{perf_text}."


def _looks_like_hour_label(label: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", label.strip()))


def _compact_job_label(label: str) -> str:
    clean = " ".join(label.split())
    return clean[:120]


def _extract_sku(label: str) -> str | None:
    match = re.search(r"\((\d{5,})\)", label)
    if match:
        return match.group(1)
    match = re.search(r"\b(\d{5,})\b", label)
    return match.group(1) if match else None


def _maintenance_questions(
    constraints: list[ActionableConstraint],
    short_events: list[DowntimeEvent],
) -> list[str]:
    if not constraints:
        return ["Ask maintenance and operators what equipment usually causes the generic Short Stop bucket on this line."]
    top = constraints[0]
    questions = [
        f"When operators select Short Stop on this line, how often is the interruption sourced in {top.name} versus only visible there?",
        f"For {top.name}, which condition is most common at restart: jam, low prime/material, flap/carton handling, sensor fault, or setup drift?",
        f"Which listed code is most trusted by maintenance: {', '.join(top.members[:4])}?",
        "What changes between shifts: operator setup, material quality, carton/film condition, startup procedure, or maintenance response time?",
        "Which stop can maintenance physically observe and verify during the next shift instead of relying on MES labels?",
    ]
    if short_events:
        questions.append("What exact operator instruction would turn a Short Stop entry into a machine/condition-specific code?")
    return questions


def _constraint_questions(
    name: str,
    members: list[str],
    by_shift: dict[str, dict[str, float]],
) -> list[str]:
    top_shift = max(by_shift.items(), key=lambda row: row[1].get("hours", 0.0))[0] if by_shift else "the worst shift"
    lead_members = ", ".join(members[:3]) if members else name
    return [
        f"Ask maintenance what physical failure mode links {lead_members}.",
        f"Watch {name} on {top_shift}: is the loss setup, material, sensor/timing, jam clearing, or operator recovery?",
        f"Confirm whether {name} is one common fault family or several independent codes sharing a machine.",
    ]