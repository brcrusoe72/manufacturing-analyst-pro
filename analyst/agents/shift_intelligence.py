"""Shift Intelligence Agent.

This is a tool-using agent layer over the deterministic analyzer. It is not a
chatbot wrapper: it queries structured OEE/downtime facts, searches prior RCA
memory, scores risk, applies approval gates, and emits a trace.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..engine import AnalysisResult
from .tools import (
    AgentTrace,
    build_recurrence_watchlist,
    classify_agent_intent,
    create_action_plan,
    draft_shift_passdown,
    find_constraint_area,
    find_prior_rcas,
    human_approval_required,
    query_oee_data,
    recommend_escalation_path,
    risk_score_event,
    schedule_verification_followups,
)


@dataclass(slots=True)
class ShiftIntelligenceReport:
    scenario: str
    summary: str
    intent: dict[str, Any]
    current_facts: dict[str, Any]
    constraint: dict[str, Any]
    prior_rcas: dict[str, Any]
    risk: dict[str, Any]
    approval_gate: dict[str, Any]
    escalation: dict[str, Any]
    action_plan: dict[str, Any]
    passdown: dict[str, Any]
    recurrence_watchlist: dict[str, Any]
    verification_followups: dict[str, Any]
    final_answer: dict[str, Any]
    trace: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "summary": self.summary,
            "intent": self.intent,
            "current_facts": self.current_facts,
            "constraint": self.constraint,
            "prior_rcas": self.prior_rcas,
            "risk": self.risk,
            "approval_gate": self.approval_gate,
            "escalation": self.escalation,
            "action_plan": self.action_plan,
            "passdown": self.passdown,
            "recurrence_watchlist": self.recurrence_watchlist,
            "verification_followups": self.verification_followups,
            "final_answer": self.final_answer,
            "trace": self.trace,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, default=str)


class ShiftIntelligenceAgent:
    """Operational agent that selects and runs analysis tools in a fixed order."""

    def __init__(self, *, kb: dict[str, Any] | None = None) -> None:
        self.kb = kb

    def run(self, result: AnalysisResult, scenario: str = "General shift intelligence") -> ShiftIntelligenceReport:
        trace = AgentTrace()

        intent = classify_agent_intent(scenario, trace=trace)
        facts = query_oee_data(result, trace=trace)
        constraint = find_constraint_area(result, trace=trace)
        prior = find_prior_rcas(self.kb, constraint["constraint"], trace=trace)
        risk = risk_score_event(result, constraint, trace=trace)
        approval = human_approval_required(
            risk,
            "maintenance_escalation" if risk["risk_level"] == "high" else "supervisor_followup",
            trace=trace,
        )
        escalation = recommend_escalation_path(constraint, risk, approval, trace=trace)
        plan = create_action_plan(constraint, prior, risk, approval, trace=trace)
        passdown = draft_shift_passdown(result, constraint, plan, trace=trace)
        watchlist = build_recurrence_watchlist(result, prior, trace=trace)
        followups = schedule_verification_followups(constraint, risk, watchlist, trace=trace)

        final_answer = _build_final_answer(scenario, intent, constraint, risk, approval, plan, passdown, watchlist, followups)
        summary = _build_summary(constraint, risk, approval, prior)
        return ShiftIntelligenceReport(
            scenario=scenario,
            summary=summary,
            intent=intent,
            current_facts=facts,
            constraint=constraint,
            prior_rcas=prior,
            risk=risk,
            approval_gate=approval,
            escalation=escalation,
            action_plan=plan,
            passdown=passdown,
            recurrence_watchlist=watchlist,
            verification_followups=followups,
            final_answer=final_answer,
            trace=trace.to_dict(),
        )


def _build_summary(
    constraint: dict[str, Any],
    risk: dict[str, Any],
    approval: dict[str, Any],
    prior: dict[str, Any],
) -> str:
    equipment = constraint.get("constraint", "unknown")
    prior_text = "with prior passdown/RCA context" if prior.get("has_prior_context") else "without prior passdown/RCA context"
    gate = "requires approval" if approval.get("required") else "does not require approval"
    return (
        f"{equipment} is the best recorded signal. Risk is {risk.get('risk_level')} "
        f"({risk.get('risk_score')}/100), {prior_text}, and the next action {gate}."
    )


def _build_final_answer(
    scenario: str,
    intent: dict[str, Any],
    constraint: dict[str, Any],
    risk: dict[str, Any],
    approval: dict[str, Any],
    plan: dict[str, Any],
    passdown: dict[str, Any],
    watchlist: dict[str, Any],
    followups: dict[str, Any],
) -> dict[str, Any]:
    """Assemble the agent's supervisor-facing answer from tool outputs."""
    top_actions = [
        {
            "owner": item.get("owner"),
            "due": item.get("due"),
            "action": item.get("action"),
        }
        for item in plan.get("actions", [])[:5]
    ]
    return {
        "answer_type": intent.get("primary_intent", "constraint_triage"),
        "scenario": scenario,
        "decision": {
            "constraint": constraint.get("constraint"),
            "interpretation": constraint.get("interpretation"),
            "validation_required": constraint.get("validation_required"),
            "cause_classes_to_separate": constraint.get("cause_classes_to_separate", []),
            "risk_level": risk.get("risk_level"),
            "risk_score": risk.get("risk_score"),
            "approval_required": approval.get("required"),
            "approvers": approval.get("approvers", []),
        },
        "evidence": constraint.get("evidence", []),
        "supervisor_actions": top_actions,
        "passdown": passdown,
        "watchlist": watchlist.get("items", [])[:5],
        "verification": followups,
        "guardrails": [
            "Treat the top recorded signal as an observation target until a human verifies physical conditions.",
            "Separate equipment/mechanical, flow/handoff, person/process, material/packaging, setup/speed, and unknown/no-pinpoint causes before RCA.",
            "Use plant source systems for official downtime, QA, maintenance, and staffing records.",
        ],
    }