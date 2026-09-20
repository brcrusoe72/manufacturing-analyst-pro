"""Deterministic tools for the Shift Intelligence Agent.

These tools are intentionally boring: they operate on typed analysis output and
known passdown/RCA memory. The agent can reason over their outputs without
inventing plant-floor facts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..engine import AnalysisResult, EquipmentProfile, ShiftProfile


@dataclass(slots=True)
class ToolCall:
    name: str
    inputs: dict[str, Any]
    output: dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(slots=True)
class AgentTrace:
    calls: list[ToolCall] = field(default_factory=list)

    def record(self, name: str, inputs: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(ToolCall(name=name, inputs=inputs, output=output))
        return output

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_calls": [
                {
                    "name": call.name,
                    "inputs": call.inputs,
                    "output": call.output,
                    "timestamp": call.timestamp,
                }
                for call in self.calls
            ]
        }


def query_oee_data(result: AnalysisResult, *, trace: AgentTrace | None = None) -> dict[str, Any]:
    """Return line-level OEE, downtime, equipment, shift, and trend facts."""
    top_equipment = [
        {
            "equipment": ep.equipment_raw_name,
            "events": ep.event_count,
            "downtime_hours": round(ep.total_downtime_hours, 2),
            "mtbf_minutes": round(ep.mtbf_minutes, 1) if ep.mtbf_minutes is not None else None,
            "repeat_failure_rate": round(ep.repeat_failure_rate, 3),
            "by_shift": ep.by_shift,
        }
        for ep in result.equipment_profiles[:8]
    ]
    shifts = [_shift_to_dict(sp) for sp in result.shift_profiles]
    output = {
        "line_id": result.line_id,
        "date_range": [result.date_range[0].date().isoformat(), result.date_range[1].date().isoformat()],
        "total_events": result.total_events,
        "total_downtime_hours": round(result.total_downtime_hours, 2),
        "avg_oee": round(result.avg_oee, 4) if result.avg_oee is not None else None,
        "top_loss_driver": result.top_loss_driver,
        "top_equipment": top_equipment,
        "shifts": shifts,
        "trends": [
            {
                "metric": t.metric_name,
                "direction": t.direction,
                "magnitude": t.magnitude,
                "monthly_values": t.monthly_values,
            }
            for t in result.trends
        ],
    }
    return trace.record("query_oee_data", {}, output) if trace else output


def classify_agent_intent(scenario: str, *, trace: AgentTrace | None = None) -> dict[str, Any]:
    """Classify the requested workflow so the agent can choose the right tools."""
    text = scenario.lower()
    intents: list[str] = []

    if any(term in text for term in ("passdown", "handoff", "next shift", "open item")):
        intents.append("passdown")
    if any(term in text for term in ("rca", "root cause", "why", "failure", "fix")):
        intents.append("rca")
    if any(term in text for term in ("recurrence", "recurring", "watchlist", "repeat", "keeps happening")):
        intents.append("recurrence")
    if any(term in text for term in ("escalate", "approval", "manager", "qa", "maintenance")):
        intents.append("escalation")
    if any(term in text for term in ("verify", "7 day", "30 day", "90 day", "follow up", "follow-up")):
        intents.append("verification")

    if not intents:
        intents = ["constraint_triage", "passdown", "verification"]

    output = {
        "scenario": scenario,
        "intents": intents,
        "primary_intent": intents[0],
        "tool_policy": {
            "always": ["query_oee_data", "find_constraint_area", "risk_score_event"],
            "conditional": {
                "rca": ["find_prior_rcas", "create_action_plan"],
                "passdown": ["draft_shift_passdown"],
                "recurrence": ["build_recurrence_watchlist"],
                "verification": ["schedule_verification_followups"],
                "escalation": ["recommend_escalation_path", "human_approval_required"],
            },
        },
    }
    return trace.record("classify_agent_intent", {"scenario": scenario}, output) if trace else output


def find_constraint_area(result: AnalysisResult, *, trace: AgentTrace | None = None) -> dict[str, Any]:
    """Identify the strongest current constraint from downtime and repeat behavior."""
    candidates = _constraint_candidates(result)
    if not candidates:
        output = {
            "constraint": "unknown",
            "reason": "No equipment profiles were available.",
            "evidence": [],
        }
        return trace.record("find_constraint_area", {}, output) if trace else output

    top = candidates[0]
    shift_signal = top.get("shift_signal")
    evidence = [
        f"{top['name']} is the best recorded actionable signal with {top['events']} events and {top['hours']:.1f} downtime hours.",
        f"Repeat failure rate is {top['repeat']:.0%}.",
    ]
    if top.get("mtbf") is not None:
        evidence.append(f"Median MTBF is {top['mtbf']:.1f} minutes.")
    if shift_signal:
        evidence.append(shift_signal["summary"])
    if top.get("members"):
        evidence.append("Rolled-up codes: " + ", ".join(top["members"][:5]) + ".")

    output = {
        "constraint": top["name"],
        "equipment_id": top.get("equipment_id"),
        "reason": "Highest recorded actionable downtime concentration after generic stop buckets are excluded and related codes are rolled up.",
        "interpretation": (
            "Treat this as an observation target, not a proven root cause. Validate whether the signal is "
            "equipment source, flow/handoff symptom, person/process behavior, material/setup issue, or recovery point."
        ),
        "validation_required": True,
        "cause_classes_to_separate": [
            "equipment/mechanical",
            "flow/handoff",
            "person/process",
            "material/packaging",
            "setup/speed",
            "unknown/no pinpoint",
        ],
        "evidence": evidence,
        "shift_signal": shift_signal,
        "events": top["events"],
        "downtime_hours": round(top["hours"], 2),
        "repeat_failure_rate": round(top["repeat"], 3),
        "mtbf_minutes": round(top["mtbf"], 1) if top.get("mtbf") is not None else None,
        "members": top.get("members", []),
    }
    return trace.record("find_constraint_area", {}, output) if trace else output


def find_prior_rcas(
    kb: dict[str, Any] | None,
    equipment_name: str,
    *,
    trace: AgentTrace | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Search historical passdown/RCA memory for similar equipment issues."""
    matches: list[dict[str, Any]] = []
    if kb:
        equipment = kb.get("equipment", [])
        query_terms = _terms(equipment_name)
        for item in equipment:
            area = str(item.get("area", ""))
            score = _term_score(query_terms, area)
            if score == 0:
                for issue in item.get("recurring_issues", []):
                    score = max(score, _term_score(query_terms, str(issue.get("issue", ""))))
            if score > 0:
                matches.append({
                    "area": area,
                    "score": score,
                    "event_count": item.get("event_count", 0),
                    "total_minutes": item.get("total_minutes", 0),
                    "resolution_rate": item.get("resolution_rate"),
                    "recurring_issues": item.get("recurring_issues", [])[:3],
                    "known_fixes": item.get("known_fixes", [])[:3],
                    "by_shift": item.get("by_shift", {}),
                    "by_line": item.get("by_line", {}),
                })

    matches.sort(key=lambda x: (x["score"], x.get("event_count", 0)), reverse=True)
    output = {
        "equipment": equipment_name,
        "matches": matches[:limit],
        "has_prior_context": bool(matches),
    }
    inputs = {"equipment_name": equipment_name, "limit": limit}
    return trace.record("find_prior_rcas", inputs, output) if trace else output


def build_recurrence_watchlist(
    result: AnalysisResult,
    prior_rcas: dict[str, Any],
    *,
    trace: AgentTrace | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Build a ranked recurrence watchlist from repeat failures and prior memory."""
    watch: list[dict[str, Any]] = []
    prior_names = {
        str(match.get("area", "")).lower(): match
        for match in prior_rcas.get("matches", [])
    }

    for item in _constraint_candidates(result)[:12]:
        recurrence_score = 0
        reasons: list[str] = []
        repeat = float(item.get("repeat") or 0.0)
        mtbf = item.get("mtbf")
        hours = float(item.get("hours") or 0.0)
        name = str(item.get("name") or "unknown")
        if repeat >= 0.75:
            recurrence_score += 35
            reasons.append(f"repeat failure rate is {repeat:.0%}")
        elif repeat >= 0.5:
            recurrence_score += 25
            reasons.append(f"repeat failure rate is {repeat:.0%}")

        if mtbf is not None and mtbf <= 20:
            recurrence_score += 25
            reasons.append(f"MTBF is {mtbf:.1f} minutes")

        if hours >= 8:
            recurrence_score += 20
            reasons.append(f"{hours:.1f} downtime hours")

        matched_prior = None
        ep_name = name.lower()
        for prior_name, match in prior_names.items():
            if prior_name and (prior_name in ep_name or ep_name in prior_name):
                matched_prior = match
                recurrence_score += 20
                reasons.append("prior passdown/RCA context exists")
                break

        if recurrence_score > 0:
            watch.append({
                "equipment": name,
                "score": min(recurrence_score, 100),
                "risk": "high" if recurrence_score >= 70 else "medium" if recurrence_score >= 40 else "low",
                "reasons": reasons,
                "prior_context": bool(matched_prior),
                "last_known_issue": (matched_prior.get("recurring_issues") or [{}])[0].get("issue") if matched_prior else None,
            })

    watch.sort(key=lambda item: item["score"], reverse=True)
    output = {
        "items": watch[:limit],
        "verification_rule": "Keep item open until event count, downtime hours, and repeat rate improve for 7 days and remain improved at 30/90 days.",
    }
    return trace.record("build_recurrence_watchlist", {"limit": limit}, output) if trace else output


def risk_score_event(
    result: AnalysisResult,
    constraint: dict[str, Any],
    *,
    trace: AgentTrace | None = None,
) -> dict[str, Any]:
    """Score escalation risk using downtime, repeat rate, MTBF, OEE, and shift spread."""
    top = _find_equipment(result, constraint.get("constraint", ""))
    score = 0
    reasons: list[str] = []

    downtime_hours = float(constraint.get("downtime_hours") or (top.total_downtime_hours if top else 0.0))
    repeat_rate = float(constraint.get("repeat_failure_rate") or (top.repeat_failure_rate if top else 0.0))
    mtbf_minutes = constraint.get("mtbf_minutes")
    if mtbf_minutes is None and top:
        mtbf_minutes = top.mtbf_minutes
    name = str(constraint.get("constraint") or (top.equipment_raw_name if top else "constraint"))

    if downtime_hours:
        if downtime_hours >= 24:
            score += 30
            reasons.append(f"{name} has {downtime_hours:.1f} downtime hours.")
        elif downtime_hours >= 8:
            score += 20
            reasons.append(f"{name} has {downtime_hours:.1f} downtime hours.")

        if repeat_rate >= 0.5:
            score += 25
            reasons.append(f"Repeat failure rate is {repeat_rate:.0%}.")

        if mtbf_minutes is not None and mtbf_minutes <= 20:
            score += 20
            reasons.append(f"MTBF is only {mtbf_minutes:.1f} minutes.")

    if result.avg_oee is not None and result.avg_oee < 0.45:
        score += 15
        reasons.append(f"Average OEE is {result.avg_oee:.1%}.")

    oee_values = [sp.avg_oee for sp in result.shift_profiles if sp.avg_oee is not None]
    if len(oee_values) >= 2 and max(oee_values) - min(oee_values) >= 0.10:
        score += 10
        reasons.append(f"Shift OEE spread is {(max(oee_values) - min(oee_values)):.1%}.")

    score = min(score, 100)
    level = "high" if score >= 70 else "medium" if score >= 40 else "low"
    output = {
        "risk_score": score,
        "risk_level": level,
        "reasons": reasons,
        "requires_human_approval": level == "high",
    }
    return trace.record("risk_score_event", {"constraint": constraint.get("constraint")}, output) if trace else output


def human_approval_required(
    risk: dict[str, Any],
    action_type: str,
    *,
    trace: AgentTrace | None = None,
) -> dict[str, Any]:
    """Decide whether the next action needs a manager/QA/maintenance gate."""
    sensitive_actions = {"schedule_change", "qa_hold", "staffing_change", "maintenance_escalation"}
    required = risk.get("requires_human_approval", False) or action_type in sensitive_actions
    approvers: list[str] = []
    if required:
        approvers.append("production_manager")
    if action_type in {"qa_hold", "sanitation_change"}:
        approvers.append("quality")
    if action_type == "maintenance_escalation" or risk.get("risk_level") == "high":
        approvers.append("maintenance_lead")

    output = {
        "required": required,
        "approvers": sorted(set(approvers)),
        "reason": "High-risk or sensitive operational action." if required else "Informational action only.",
    }
    inputs = {"risk_level": risk.get("risk_level"), "action_type": action_type}
    return trace.record("human_approval_required", inputs, output) if trace else output


def recommend_escalation_path(
    constraint: dict[str, Any],
    risk: dict[str, Any],
    approval: dict[str, Any],
    *,
    trace: AgentTrace | None = None,
) -> dict[str, Any]:
    """Recommend who should act next and what should not be done autonomously."""
    equipment = constraint.get("constraint", "unknown")
    level = risk.get("risk_level", "low")

    if level == "high":
        path = ["supervisor", "maintenance_lead", "production_manager"]
        if approval.get("required"):
            path.append("human_approval_gate")
        next_step = f"Escalate {equipment} as a chronic constraint before the next shift release."
    elif level == "medium":
        path = ["supervisor", "maintenance"]
        next_step = f"Assign focused follow-up for {equipment} and review after the next shift."
    else:
        path = ["supervisor"]
        next_step = f"Track {equipment}; no manager escalation unless the repeat signal worsens."

    output = {
        "path": path,
        "next_step": next_step,
        "autonomous_limits": [
            "Do not change staffing, QA hold status, sanitation rules, or maintenance priority without human approval.",
            "Do not claim root cause as proven until a supervisor or maintenance lead confirms the condition.",
        ],
    }
    return trace.record("recommend_escalation_path", {"risk_level": level}, output) if trace else output


def create_action_plan(
    constraint: dict[str, Any],
    prior_rcas: dict[str, Any],
    risk: dict[str, Any],
    approval: dict[str, Any],
    *,
    trace: AgentTrace | None = None,
) -> dict[str, Any]:
    """Create supervisor-ready actions grounded in current data and prior RCA memory."""
    equipment = constraint.get("constraint", "unknown")
    actions = [
        {
            "owner": "supervisor",
            "due": "next shift start",
            "action": f"Observe the next {equipment} signal and record whether it is source, symptom, or recovery point.",
        },
        {
            "owner": "maintenance",
            "due": "same shift",
            "action": f"Validate the physical cause class behind {equipment}: equipment, flow/handoff, person/process, material, setup/speed, or unknown.",
        },
        {
            "owner": "lead/operator",
            "due": "next 24 hours",
            "action": f"For every {equipment} or generic stop, capture flow state, operator action, duration bucket, and restart condition.",
        },
    ]

    matches = prior_rcas.get("matches", [])
    if matches:
        first = matches[0]
        fixes = first.get("known_fixes") or []
        issues = first.get("recurring_issues") or []
        if fixes:
            fix_text = fixes[0].get("fix") or fixes[0].get("action") or str(fixes[0])
            actions.append({
                "owner": "supervisor",
                "due": "next 48 hours",
                "action": f"Compare current countermeasure against prior fix pattern: {fix_text[:180]}",
            })
        if issues:
            issue_text = issues[0].get("issue", "")
            actions.append({
                "owner": "maintenance",
                "due": "next 48 hours",
                "action": f"Check whether recurring issue is still present: {issue_text[:180]}",
            })

    if risk.get("risk_level") == "high":
        actions.insert(0, {
            "owner": "production_manager",
            "due": "today",
            "action": f"Treat {equipment} as an escalation item until repeat failures are contained.",
        })

    output = {
        "constraint": equipment,
        "risk_level": risk.get("risk_level"),
        "approval_gate": approval,
        "actions": actions,
        "verification": [
            "Track event count and downtime hours by shift for 7 days.",
            "Recheck recurrence at 30/90 days before closing the issue.",
            "Confirm coding quality improved; unassigned/generic stop rate should fall.",
        ],
    }
    return trace.record("create_action_plan", {"constraint": equipment}, output) if trace else output


def draft_shift_passdown(
    result: AnalysisResult,
    constraint: dict[str, Any],
    action_plan: dict[str, Any],
    *,
    trace: AgentTrace | None = None,
) -> dict[str, Any]:
    """Draft a concise passdown note for supervisors."""
    equipment = constraint.get("constraint", "unknown")
    top = _find_equipment(result, equipment)
    if constraint.get("downtime_hours"):
        headline = (
            f"{equipment} is the best recorded actionable signal: {constraint.get('events')} events, "
            f"{float(constraint.get('downtime_hours')):.1f} downtime hours, "
            f"{float(constraint.get('repeat_failure_rate') or 0):.0%} repeat rate. "
            "Validate the true cause class before treating it as an equipment constraint."
        )
    elif top:
        headline = (
            f"{equipment} is the best recorded signal: {top.event_count} events, "
            f"{top.total_downtime_hours:.1f} downtime hours, {top.repeat_failure_rate:.0%} repeat rate. "
            "Validate source vs symptom before RCA."
        )
    else:
        headline = f"{equipment} is the best recorded signal; validate source vs symptom before RCA."

    next_actions = [a["action"] for a in action_plan.get("actions", [])[:4]]
    output = {
        "headline": headline,
        "open_items": next_actions,
        "watchlist": [
            equipment,
            "unassigned/generic downtime coding",
            "flow-state and operator-action observations",
            "shift-to-shift recurrence",
        ],
        "verification": action_plan.get("verification", []),
    }
    return trace.record("draft_shift_passdown", {"constraint": equipment}, output) if trace else output


def schedule_verification_followups(
    constraint: dict[str, Any],
    risk: dict[str, Any],
    watchlist: dict[str, Any],
    *,
    trace: AgentTrace | None = None,
) -> dict[str, Any]:
    """Create 7/30/90-day checks so countermeasures are not forgotten."""
    equipment = constraint.get("constraint", "unknown")
    high_risk_items = [
        item["equipment"] for item in watchlist.get("items", [])
        if item.get("risk") in {"high", "medium"}
    ]
    metrics = [
        "event count by shift",
        "downtime hours by shift",
        "repeat failure rate",
        "MTBF minutes",
        "unassigned/generic coding rate",
    ]
    output = {
        "cadence": [
            {
                "when": "7 days",
                "owner": "supervisor",
                "check": f"Did {equipment} event count and repeat rate fall versus the baseline?",
            },
            {
                "when": "30 days",
                "owner": "maintenance_lead",
                "check": f"Did the countermeasure hold without the same {equipment} issue returning?",
            },
            {
                "when": "90 days",
                "owner": "production_manager",
                "check": "Close the watchlist item only if recurrence stayed down across shifts.",
            },
        ],
        "metrics": metrics,
        "watchlist_items": high_risk_items[:5] or [equipment],
        "priority": "high" if risk.get("risk_level") == "high" else "normal",
    }
    return trace.record("schedule_verification_followups", {"constraint": equipment}, output) if trace else output


def _shift_to_dict(sp: ShiftProfile) -> dict[str, Any]:
    return {
        "shift": sp.shift,
        "avg_oee": round(sp.avg_oee, 4) if sp.avg_oee is not None else None,
        "event_count": sp.event_count,
        "downtime_hours": round(sp.total_downtime_hours, 2),
        "unassigned_rate": round(sp.unassigned_rate, 3),
        "startup_penalty_points": round(sp.startup_penalty_points, 4) if sp.startup_penalty_points is not None else None,
        "avg_recovery_minutes": round(sp.avg_recovery_minutes, 2),
        "notable_patterns": sp.notable_patterns,
    }


def _find_equipment(result: AnalysisResult, equipment_name: str) -> EquipmentProfile | None:
    target = equipment_name.lower().strip()
    for ep in result.equipment_profiles:
        name = ep.equipment_raw_name.lower().strip()
        if name == target or target in name or name in target:
            return ep
    return None


def _constraint_candidates(result: AnalysisResult) -> list[dict[str, Any]]:
    """Return actionable raw/family constraints, excluding generic symptom buckets."""
    raw_items: list[dict[str, Any]] = []
    family_groups: dict[str, list[EquipmentProfile]] = {}

    for ep in result.equipment_profiles:
        if _is_generic_constraint(ep.equipment_raw_name):
            continue
        raw_items.append(_candidate_from_profiles(ep.equipment_raw_name, [ep], equipment_id=ep.equipment_id))
        family_name = _equipment_family(ep.equipment_raw_name)
        family_groups.setdefault(family_name, []).append(ep)

    family_items = [
        _candidate_from_profiles(name, members, equipment_id=None)
        for name, members in family_groups.items()
        if len(members) > 1
    ]
    candidates = raw_items + family_items
    candidates.sort(key=lambda item: (item["hours"], item["events"], item["repeat"]), reverse=True)
    return candidates


def _candidate_from_profiles(name: str, profiles: list[EquipmentProfile], *, equipment_id: str | None) -> dict[str, Any]:
    events = sum(ep.event_count for ep in profiles)
    hours = sum(ep.total_downtime_hours for ep in profiles)
    repeat = sum(ep.repeat_failure_rate * ep.event_count for ep in profiles) / max(events, 1)
    mtbf_values = [ep.mtbf_minutes for ep in profiles if ep.mtbf_minutes is not None]
    mtbf = min(mtbf_values) if mtbf_values else None
    shift_counts: dict[str, dict[str, float]] = {
        "1st": {"count": 0, "hours": 0.0},
        "2nd": {"count": 0, "hours": 0.0},
        "3rd": {"count": 0, "hours": 0.0},
    }
    for ep in profiles:
        for shift, vals in ep.by_shift.items():
            shift_counts.setdefault(shift, {"count": 0, "hours": 0.0})
            shift_counts[shift]["count"] += int(vals.get("count", 0))
            shift_counts[shift]["hours"] += float(vals.get("hours", 0.0))
    return {
        "name": name,
        "equipment_id": equipment_id,
        "events": events,
        "hours": hours,
        "repeat": repeat,
        "mtbf": mtbf,
        "members": [ep.equipment_raw_name for ep in profiles],
        "shift_signal": _largest_shift_signal_from_counts(shift_counts),
    }


def _is_generic_constraint(name: str) -> bool:
    text = name.lower().strip()
    return any(term in text for term in ("short stop", "shortstop", "micro stop", "micro-stop", "unassigned", "unknown", "not scheduled"))


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
    return name


def _largest_shift_signal(ep: EquipmentProfile) -> dict[str, Any] | None:
    counts = [(shift, data.get("count", 0), data.get("hours", 0.0)) for shift, data in ep.by_shift.items()]
    counts = [(shift, count, hours) for shift, count, hours in counts if count > 0]
    if len(counts) < 2:
        return None
    counts.sort(key=lambda item: item[1])
    low_shift, low_count, _ = counts[0]
    high_shift, high_count, high_hours = counts[-1]
    if low_count <= 0:
        return None
    ratio = high_count / low_count
    if ratio < 2:
        return None
    return {
        "high_shift": high_shift,
        "low_shift": low_shift,
        "ratio": round(ratio, 2),
        "summary": f"{high_shift} shift has {high_count} events ({high_hours:.1f}h) vs {low_shift} shift's {low_count} ({ratio:.1f}x).",
    }


def _largest_shift_signal_from_counts(counts_by_shift: dict[str, dict[str, float]]) -> dict[str, Any] | None:
    counts = [
        (shift, int(data.get("count", 0)), float(data.get("hours", 0.0)))
        for shift, data in counts_by_shift.items()
        if int(data.get("count", 0)) > 0
    ]
    if len(counts) < 2:
        return None
    counts.sort(key=lambda item: item[1])
    low_shift, low_count, _ = counts[0]
    high_shift, high_count, high_hours = counts[-1]
    ratio = high_count / max(low_count, 1)
    if ratio < 2:
        return None
    return {
        "high_shift": high_shift,
        "low_shift": low_shift,
        "ratio": round(ratio, 2),
        "summary": f"{high_shift} shift has {high_count} events ({high_hours:.1f}h) vs {low_shift} shift's {low_count} ({ratio:.1f}x).",
    }


def _terms(text: str) -> set[str]:
    stop = {"the", "and", "for", "with", "line", "machine"}
    return {part for part in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split() if len(part) > 2 and part not in stop}


def _term_score(query_terms: set[str], text: str) -> int:
    text_terms = _terms(text)
    if not query_terms or not text_terms:
        return 0
    return len(query_terms & text_terms)