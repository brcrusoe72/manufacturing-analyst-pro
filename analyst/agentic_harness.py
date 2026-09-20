"""Agentic manufacturing harness driven by markdown behavior files.

This is the repo-native app shape: markdown behavior, tool calls, run traces,
workspace artifacts, and an optional LLM planner. It is deliberately separate
from the Streamlit analyzer so it can live on GitHub as an agent harness.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .agents.workflow import run_shift_workflow, save_workflow_run
from .line_review import render_markdown_report, run_line_review
from .loader import SUPPORTED_SUFFIXES, load_data
from .path_policy import (
    resolve_behavior_path,
    resolve_behavior_roots,
    resolve_data_roots,
    resolve_read_path,
    resolve_workspace_path,
    resolve_workspace_roots,
    safe_filename,
)
from .security import get_openai_api_key, llm_egress_allowed


@dataclass(slots=True)
class HarnessToolCall:
    name: str
    reason: str
    inputs: dict[str, Any]
    output: dict[str, Any]
    elapsed_seconds: float


@dataclass(slots=True)
class HarnessRun:
    run_id: str
    message: str
    workspace: str
    behavior_files: list[str]
    plan: dict[str, Any]
    tool_calls: list[HarnessToolCall] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    final_answer: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "message": self.message,
            "workspace": self.workspace,
            "behavior_files": self.behavior_files,
            "plan": self.plan,
            "tool_calls": [
                {
                    "name": call.name,
                    "reason": call.reason,
                    "inputs": call.inputs,
                    "output": call.output,
                    "elapsed_seconds": call.elapsed_seconds,
                }
                for call in self.tool_calls
            ],
            "artifacts": self.artifacts,
            "final_answer": self.final_answer,
            "created_at": self.created_at,
        }


class ManufacturingAgenticHarness:
    """Small OpenClaw-like manufacturing harness."""

    ANALYSIS_TOOLS = {"run_line_review", "run_shift_workflow"}
    FOLLOW_ON_TOOLS = {
        "build_decision_cockpit",
        "build_event_fidelity_sprint",
        "build_management_brief",
        "build_operating_model",
    }

    def __init__(
        self,
        *,
        workspace: str | Path = "agent-workspace",
        behavior_dir: str | Path | None = None,
        use_llm: bool = True,
        model: str = "gpt-5-mini",
        data_roots: list[str | Path] | None = None,
        behavior_roots: list[str | Path] | None = None,
        workspace_roots: list[str | Path] | None = None,
    ) -> None:
        root = Path(__file__).resolve().parent.parent
        packaged_behavior = Path(__file__).resolve().parent / "default_harness"
        default_behavior = root / "agent-harness"
        if not default_behavior.is_dir():
            default_behavior = packaged_behavior
        self.repo_root = root
        self.data_roots = resolve_data_roots(data_roots)
        self.behavior_roots = resolve_behavior_roots(behavior_roots)
        self.workspace_roots = resolve_workspace_roots(workspace_roots)
        self.behavior_dir = self._resolve_behavior_path(behavior_dir, default=default_behavior, purpose="behavior_dir")
        self.workspace = self._resolve_workspace_path(workspace)
        self.inbox_dir = self.workspace / "inbox"
        self.artifacts_dir = self.workspace / "artifacts"
        self.runs_dir = self.workspace / "runs"
        self.memory_file = self.workspace / "MEMORY.md"
        self.use_llm = use_llm
        self.model = model
        self._ensure_workspace()

    def run(
        self,
        message: str,
        *,
        data_path: str | Path | None = None,
        line: str | None = None,
        photo_name: str | None = None,
    ) -> HarnessRun:
        """Run one agent turn."""
        behavior = self._load_behavior()
        run = HarnessRun(
            run_id=_run_id(),
            message=message,
            workspace=str(self.workspace),
            behavior_files=list(behavior.keys()),
            plan={},
        )

        staged_data = self._stage_data(data_path) if data_path else None
        plan = self._plan(message, behavior, staged_data=staged_data, line=line)
        run.plan = plan

        outputs: dict[str, Any] = {}
        if staged_data:
            outputs["inspect_data"] = self._call_tool(
                run,
                "inspect_data",
                "Understand the data files before deciding what to build.",
                {"data_path": str(staged_data)},
                lambda: self._inspect_data(staged_data),
            )

        for step in plan.get("steps", []):
            tool = step.get("tool")
            reason = step.get("reason", "")
            if tool not in self.ANALYSIS_TOOLS:
                continue
            if tool == "run_line_review" and staged_data:
                outputs["run_line_review"] = self._call_tool(
                    run,
                    "run_line_review",
                    reason or "Build long-horizon management intelligence from line history.",
                    {"data_path": str(staged_data), "line": line, "photo_name": photo_name},
                    lambda: self._run_line_review(
                        staged_data,
                        message,
                        artifact_run_id=run.run_id,
                        line=line,
                        photo_name=photo_name,
                    ),
                )
            elif tool == "run_shift_workflow" and staged_data:
                outputs["run_shift_workflow"] = self._call_tool(
                    run,
                    "run_shift_workflow",
                    reason or "Build shift-level passdown, RCA, watchlist, and verification outputs.",
                    {"data_path": str(staged_data), "scenario": message},
                    lambda: self._run_shift_workflow(staged_data, message),
                )

        self._build_follow_on_artifacts(run, message, outputs, plan)
        self._build_plan_authored_artifacts(run, message, outputs, plan)
        artifact = self._build_operating_artifact(message, outputs, plan)
        artifact_path = self._write_artifact(run.run_id, "operating-brief.md", artifact)
        run.artifacts.append(str(artifact_path))
        self._append_memory(run, outputs)
        run.final_answer = self._final_answer(run, outputs)
        self._save_run(run)
        return run

    def interactive(self) -> None:
        """Simple terminal loop for engaging with the harness."""
        print("Manufacturing Management Agent Harness")
        print("Type a request. Commands: /data <path>, /line <line>, /tools, /memory, /runs, /quit.")
        data_path: str | None = None
        line: str | None = None
        while True:
            prompt = f"mfg-agent[data={data_path or '-'} line={line or '-'}]> "
            try:
                text = input(prompt).strip()
            except EOFError:
                return
            if not text:
                continue
            if text in {"/quit", "/exit"}:
                return
            if text == "/tools":
                print("\n".join(f"- {tool}" for tool in self.available_tools()))
                continue
            if text == "/memory":
                print(self.memory_file.read_text())
                continue
            if text == "/runs":
                for path in sorted(self.runs_dir.glob("*.json"))[-10:]:
                    print(path)
                continue
            if text.startswith("/data "):
                data_path = text.split(" ", 1)[1].strip()
                continue
            if text.startswith("/line "):
                line = text.split(" ", 1)[1].strip()
                continue
            run = self.run(text, data_path=data_path, line=line)
            print(run.final_answer)
            for artifact in run.artifacts:
                print(f"artifact: {artifact}")

    def available_tools(self) -> list[str]:
        """Return harness tool names exposed to the planner/user."""
        return [
            "inspect_data",
            "run_line_review",
            "run_shift_workflow",
            "build_decision_cockpit",
            "build_event_fidelity_sprint",
            "build_management_brief",
            "build_plan_artifact",
        ]

    def _resolve_read_path(self, path: str | Path | None, *, default: Path, purpose: str) -> Path:
        return resolve_read_path(path or default, purpose=purpose, roots=self.data_roots)

    def _resolve_behavior_path(self, path: str | Path | None, *, default: Path, purpose: str) -> Path:
        return resolve_behavior_path(path or default, purpose=purpose, roots=self.behavior_roots)

    def _resolve_workspace_path(self, path: str | Path) -> Path:
        return resolve_workspace_path(path, purpose="workspace", roots=self.workspace_roots)

    def _ensure_workspace(self) -> None:
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        if not self.memory_file.exists():
            _atomic_write_text(self.memory_file, "# Harness Memory\n\n")

    def _load_behavior(self) -> dict[str, str]:
        files = [
            self.behavior_dir / "AGENT.md",
            self.behavior_dir / "TOOLS.md",
            self.behavior_dir / "roles" / "PRODUCTION_SUPERVISOR.md",
            self.behavior_dir / "roles" / "PRODUCTION_MANAGER.md",
            self.behavior_dir / "roles" / "CI_MANAGER.md",
        ]
        return {str(path.relative_to(self.behavior_dir)): path.read_text() for path in files if path.is_file()}

    def _stage_data(self, data_path: str | Path | None) -> Path | None:
        if data_path is None:
            return None
        source = self._resolve_read_path(data_path, default=self.repo_root, purpose="data_path")
        if not source.exists():
            raise FileNotFoundError(f"Data path not found: {source}")
        target = self.inbox_dir / f"{int(time.time() * 1000)}-{safe_filename(source.name)}"
        if source.resolve() == target.resolve():
            return target
        if source.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return target

    def _plan(
        self,
        message: str,
        behavior: dict[str, str],
        *,
        staged_data: Path | None,
        line: str | None,
    ) -> dict[str, Any]:
        if self.use_llm and llm_egress_allowed("planner") and get_openai_api_key("planner"):
            planned = self._llm_plan(message, behavior, staged_data=staged_data, line=line)
            if planned:
                return planned
        return self._fallback_plan(message, staged_data=staged_data)

    def _llm_plan(
        self,
        message: str,
        behavior: dict[str, str],
        *,
        staged_data: Path | None,
        line: str | None,
    ) -> dict[str, Any] | None:
        try:
            from openai import OpenAI
            api_key = get_openai_api_key("planner")
            if not api_key:
                raise RuntimeError("LLM planner egress is disabled")
            client = OpenAI(api_key=api_key)
            behavior_text = "\n\n".join(f"# {name}\n{body}" for name, body in behavior.items())
            prompt = {
                "message": message,
                "has_data": staged_data is not None,
                "data_path": str(staged_data) if staged_data else None,
                "line": line,
                "tools": self.available_tools(),
                "behavior": behavior_text[:12000],
                "instruction": (
                    "Return only JSON with keys: role_focus, objective, workflow, steps, artifacts. "
                    "workflow is {name, rationale}. "
                    "steps is a list of {tool, reason}. Choose at most two analysis tools. "
                    "artifacts is a list of {filename, title, purpose, sections}; sections is a short list of markdown section names. "
                    "Use run_line_review for long-horizon/Short Stop/Unassigned/line history work. "
                    "Use run_shift_workflow for passdown/RCA/escalation/watchlist/verification work. "
                    "The harness will build follow-on and plan-authored artifacts after tool results."
                ),
            }
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": json.dumps(prompt)}],
                temperature=0,
            )
            text = response.choices[0].message.content or ""
            return self._validate_plan(json.loads(_strip_fences(text)), planner="llm")
        except Exception as exc:
            fallback = self._fallback_plan(message, staged_data=staged_data)
            fallback["planner_error"] = str(exc)
            return fallback

    def _fallback_plan(self, message: str, *, staged_data: Path | None) -> dict[str, Any]:
        text = message.lower()
        steps: list[dict[str, str]] = []
        if staged_data:
            if any(term in text for term in ("month", "short stop", "unassigned", "line review", "pareto", "visibility")):
                steps.append({
                    "tool": "run_line_review",
                    "reason": "The request is about long-horizon line behavior and visibility loss.",
                })
            if any(term in text for term in ("passdown", "rca", "root cause", "escalat", "watchlist", "verify", "7/30/90")):
                steps.append({
                    "tool": "run_shift_workflow",
                    "reason": "The request asks for shift execution, RCA, escalation, recurrence, or verification.",
                })
            if not steps:
                steps.append({
                    "tool": "run_line_review",
                    "reason": "Data is present; build the most useful management artifact first.",
                })
        authored_artifacts = []
        if staged_data and any(term in text for term in ("build", "workflow", "package", "artifact", "manager", "supervisor", "ci")):
            authored_artifacts.append({
                "filename": "agent-authored-workflow.md",
                "title": "Agent-Authored Manufacturing Workflow",
                "purpose": "Turn the selected tool outputs into an operating workflow for supervisor, production manager, and CI follow-through.",
                "sections": ["Operating Judgment", "Supervisor Routine", "Manager Control", "CI Experiment", "Verification"],
            })
        return self._validate_plan({
            "role_focus": _role_focus(text),
            "objective": "Use plant data to build the next useful operating artifact.",
            "workflow": {
                "name": "Manufacturing management review",
                "rationale": "Select trusted plant-data tools, then build role-specific operating artifacts from their results.",
            },
            "steps": steps,
            "artifacts": authored_artifacts,
            "planner": "fallback",
        }, planner="fallback")

    def _validate_plan(self, plan: Any, *, planner: str) -> dict[str, Any]:
        if not isinstance(plan, dict):
            raise ValueError("planner returned a non-object plan")
        steps: list[dict[str, str]] = []
        for raw in plan.get("steps") or []:
            if not isinstance(raw, dict):
                continue
            tool = str(raw.get("tool") or "")
            if tool not in self.ANALYSIS_TOOLS:
                continue
            if any(step["tool"] == tool for step in steps):
                continue
            steps.append({
                "tool": tool,
                "reason": str(raw.get("reason") or f"Run {tool}.")[:500],
            })
            if len(steps) >= 2:
                break
        normalized = {
            "role_focus": str(plan.get("role_focus") or "mixed")[:120],
            "objective": str(plan.get("objective") or "Use plant data to build the next useful operating artifact.")[:500],
            "workflow": _validate_workflow(plan.get("workflow")),
            "steps": steps,
            "artifacts": _validate_artifact_specs(plan.get("artifacts")),
            "planner": str(plan.get("planner") or planner)[:80],
            "allowed_tools": sorted(self.ANALYSIS_TOOLS),
            "follow_on_tools": sorted(self.FOLLOW_ON_TOOLS),
        }
        if plan.get("planner_error"):
            normalized["planner_error"] = str(plan["planner_error"])[:500]
        return normalized

    def _inspect_data(self, data_path: Path) -> dict[str, Any]:
        files = []
        if data_path.is_file():
            candidates = [data_path]
        else:
            candidates = [path for path in sorted(data_path.rglob("*")) if path.is_file()]
        for path in candidates:
            files.append({
                "path": str(path),
                "name": path.name,
                "suffix": path.suffix.lower(),
                "supported": path.suffix.lower() in SUPPORTED_SUFFIXES,
                "size_bytes": path.stat().st_size,
            })
        parsed = {"events": 0, "oee_intervals": 0, "error": None}
        try:
            events, oee = load_data(data_path if data_path.is_dir() else data_path.parent)
            parsed = {"events": len(events), "oee_intervals": len(oee), "error": None}
        except Exception as exc:
            parsed["error"] = str(exc)
        return {"files": files, "parsed": parsed}

    def _run_line_review(
        self,
        data_path: Path,
        message: str,
        *,
        artifact_run_id: str,
        line: str | None,
        photo_name: str | None,
    ) -> dict[str, Any]:
        events, oee = load_data(data_path if data_path.is_dir() else data_path.parent)
        review = run_line_review(events, oee, line_hint=line, context=message, photo_name=photo_name)
        markdown = render_markdown_report(review)
        path = self._write_artifact(artifact_run_id, "line-review.md", markdown)
        payload = review.to_dict()
        payload["artifact_path"] = str(path)
        return payload

    def _run_shift_workflow(self, data_path: Path, message: str) -> dict[str, Any]:
        run = run_shift_workflow(data_path if data_path.is_dir() else data_path.parent, scenario=message)
        path = save_workflow_run(run, self.artifacts_dir / f"{run.run_id}.json")
        payload = run.to_dict()
        payload["artifact_path"] = str(path)
        return payload

    def _call_tool(
        self,
        run: HarnessRun,
        name: str,
        reason: str,
        inputs: dict[str, Any],
        fn: Callable[[], dict[str, Any]],
    ) -> dict[str, Any]:
        t0 = time.time()
        try:
            output = fn()
        except Exception as exc:
            run.tool_calls.append(HarnessToolCall(
                name=name,
                reason=reason,
                inputs=inputs,
                output={"status": "error", "error": str(exc)},
                elapsed_seconds=round(time.time() - t0, 3),
            ))
            raise
        run.tool_calls.append(HarnessToolCall(
            name=name,
            reason=reason,
            inputs=inputs,
            output=_compact_output(output),
            elapsed_seconds=round(time.time() - t0, 3),
        ))
        artifact_path = output.get("artifact_path") if isinstance(output, dict) else None
        if artifact_path:
            run.artifacts.append(str(artifact_path))
        return output

    def _build_follow_on_artifacts(
        self,
        run: HarnessRun,
        message: str,
        outputs: dict[str, Any],
        plan: dict[str, Any],
    ) -> None:
        """Let the harness build next artifacts from tool outputs."""
        if "run_line_review" in outputs:
            review = outputs["run_line_review"]
            outputs["build_operating_model"] = self._call_tool(
                run,
                "build_operating_model",
                "Convert recorded event signals into a floor-valid operating model.",
                {"source": "run_line_review"},
                lambda: self._build_operating_model(run.run_id, review),
            )
            outputs["build_decision_cockpit"] = self._call_tool(
                run,
                "build_decision_cockpit",
                "Convert line review evidence into an operating decision cockpit.",
                {"source": "run_line_review"},
                lambda: self._build_decision_cockpit(run.run_id, review),
            )
            outputs["build_management_brief"] = self._call_tool(
                run,
                "build_management_brief",
                "Convert line review output into a role-based operating artifact.",
                {"source": "run_line_review"},
                lambda: self._build_management_brief(run.run_id, message, review, plan),
            )
            if review.get("visibility_score", 100) < 75:
                outputs["build_event_fidelity_sprint"] = self._call_tool(
                    run,
                    "build_event_fidelity_sprint",
                    "Visibility loss is high enough that the agent should build the next CI/control artifact.",
                    {"source": "run_line_review", "visibility_score": review.get("visibility_score")},
                    lambda: self._build_event_fidelity_sprint(run.run_id, review),
                )

    def _build_plan_authored_artifacts(
        self,
        run: HarnessRun,
        message: str,
        outputs: dict[str, Any],
        plan: dict[str, Any],
    ) -> None:
        """Build bounded artifacts requested by an authored workflow plan."""
        for spec in plan.get("artifacts", []):
            text = self._render_plan_artifact(message, outputs, plan, spec)
            result = self._call_tool(
                run,
                "build_plan_artifact",
                spec.get("purpose") or "Build a plan-authored artifact from trusted tool outputs.",
                {"filename": spec["filename"], "sections": spec.get("sections", [])},
                lambda text=text, filename=spec["filename"]: {
                    "artifact_path": str(self._write_artifact(run.run_id, filename, text)),
                    "title": spec.get("title"),
                },
            )
            outputs.setdefault("build_plan_artifacts", []).append(result)

    def _render_plan_artifact(
        self,
        message: str,
        outputs: dict[str, Any],
        plan: dict[str, Any],
        spec: dict[str, Any],
    ) -> str:
        workflow = plan.get("workflow", {})
        lines = [
            f"# {spec.get('title') or 'Plan Artifact'}",
            "",
            f"**Workflow:** {workflow.get('name', 'Manufacturing agent workflow')}",
            f"**Purpose:** {spec.get('purpose', '')}",
            f"**Request:** {message}",
            "",
        ]
        for section in spec.get("sections", []):
            lines.extend([f"## {section}", ""])
            lines.extend(_artifact_section_lines(section, outputs))
            lines.append("")
        lines.extend([
            "## Source Trace",
            "",
            f"- Planner: {plan.get('planner')}",
            f"- Analysis tools: {', '.join(step.get('tool', '') for step in plan.get('steps', [])) or 'none'}",
            f"- Follow-on tools: {', '.join(plan.get('follow_on_tools', []))}",
        ])
        return "\n".join(lines).strip() + "\n"

    def _build_operating_artifact(self, message: str, outputs: dict[str, Any], plan: dict[str, Any]) -> str:
        lines = [
            "# Manufacturing Agent Operating Brief",
            "",
            f"**Request:** {message}",
            f"**Role focus:** {plan.get('role_focus', 'mixed')}",
            f"**Objective:** {plan.get('objective', '')}",
            "",
            "## Tool Results",
            "",
        ]
        if "inspect_data" in outputs:
            parsed = outputs["inspect_data"].get("parsed", {})
            lines.extend([
                "### inspect_data",
                f"- Events parsed: {parsed.get('events')}",
                f"- OEE intervals parsed: {parsed.get('oee_intervals')}",
                f"- Error: {parsed.get('error') or 'none'}",
                "",
            ])
        if "run_line_review" in outputs:
            review = outputs["run_line_review"]
            lines.extend([
                "### run_line_review",
                f"- Line: {review.get('line_id')}",
                f"- Months covered: {review.get('months_covered')}",
                f"- Visibility score: {review.get('visibility_score')}/100",
                f"- Management signal: {review.get('management_signal')}",
                f"- Masking read: {review.get('masking_summary')}",
                f"- Artifact: {review.get('artifact_path')}",
                "",
            ])
        if "run_shift_workflow" in outputs:
            wf = outputs["run_shift_workflow"]
            answer = wf.get("agent_report", {}).get("final_answer", {})
            decision = answer.get("decision", {})
            lines.extend([
                "### run_shift_workflow",
                f"- Constraint: {decision.get('constraint')}",
                f"- Risk: {decision.get('risk_level')} ({decision.get('risk_score')}/100)",
                f"- Approval required: {decision.get('approval_required')}",
                f"- Artifact: {wf.get('artifact_path')}",
                "",
            ])
        if "build_management_brief" in outputs:
            lines.extend([
                "### build_management_brief",
                f"- Artifact: {outputs['build_management_brief'].get('artifact_path')}",
                "",
            ])
        if "build_operating_model" in outputs:
            model = outputs["build_operating_model"]
            lines.extend([
                "### build_operating_model",
                f"- Recorded signal: {model.get('recorded_signal')}",
                f"- Artifact: {model.get('artifact_path')}",
                "",
            ])
        if "build_decision_cockpit" in outputs:
            cockpit = outputs["build_decision_cockpit"]
            lines.extend([
                "### build_decision_cockpit",
                f"- Suspected constraint: {cockpit.get('suspected_constraint')}",
                f"- Confidence: {cockpit.get('confidence')}",
                f"- Artifact: {cockpit.get('artifact_path')}",
                "",
            ])
        if "build_event_fidelity_sprint" in outputs:
            lines.extend([
                "### build_event_fidelity_sprint",
                f"- Artifact: {outputs['build_event_fidelity_sprint'].get('artifact_path')}",
                "",
            ])
        if "build_plan_artifacts" in outputs:
            lines.append("### build_plan_artifacts")
            for artifact in outputs["build_plan_artifacts"]:
                lines.append(f"- Artifact: {artifact.get('artifact_path')}")
            lines.append("")
        lines.extend([
            "## Next Useful Action",
            "",
            _next_action(outputs),
        ])
        return "\n".join(lines).strip() + "\n"

    def _build_management_brief(
        self,
        run_id: str,
        message: str,
        review: dict[str, Any],
        plan: dict[str, Any],
    ) -> dict[str, Any]:
        lines = [
            "# Management Agent Brief",
            "",
            f"**Request:** {message}",
            f"**Line:** {review.get('line_id')}",
            f"**Visibility score:** {review.get('visibility_score')}/100",
            "",
            "## Agent Judgment",
            "",
            review.get("management_signal", ""),
            "",
            "## Operating Model",
            "",
            review.get("operating_model", {}).get("interpretation", "No operating model available."),
            "",
            f"Decision rule: {review.get('operating_model', {}).get('decision_rule', 'No decision rule available.')}",
            "",
            "## Role Outputs",
            "",
        ]
        for brief in review.get("role_briefs", []):
            lines.extend([
                f"### {brief.get('role')}",
                "",
                brief.get("verdict", ""),
                "",
                "Actions:",
            ])
            for action in brief.get("actions", []):
                lines.append(f"- {action}")
            lines.extend(["", "Evidence:"])
            for item in brief.get("evidence", []):
                lines.append(f"- {item}")
            lines.append("")
        lines.extend([
            "## Agent Next Move",
            "",
            _next_action({"run_line_review": review}),
        ])
        path = self._write_artifact(run_id, "management-brief.md", "\n".join(lines).strip() + "\n")
        return {
            "artifact_path": str(path),
            "roles": [brief.get("role") for brief in review.get("role_briefs", [])],
            "visibility_score": review.get("visibility_score"),
        }

    def _build_operating_model(self, run_id: str, review: dict[str, Any]) -> dict[str, Any]:
        model = review.get("operating_model", {})
        lines = [
            f"# Operating Model - {review.get('line_id', 'line')}",
            "",
            "## What The Data Can And Cannot Say",
            "",
            f"- Best recorded signal: {model.get('recorded_signal', 'unknown')}",
            f"- Interpretation: {model.get('interpretation', 'unknown')}",
            f"- Decision rule: {model.get('decision_rule', 'unknown')}",
            "",
            "## Duration / Capture Bias",
            "",
        ]
        for bucket in model.get("duration_profile", []):
            lines.append(
                f"- {bucket.get('bucket')}: {bucket.get('events', 0):,} events, "
                f"{bucket.get('hours', 0):.1f}h, {bucket.get('generic_events', 0):,} generic events"
            )
        lines.extend(["", "Bias reads:"])
        for item in model.get("duration_bias", []):
            lines.append(f"- {item}")
        lines.extend(["", "## Attribution Risks", ""])
        for item in model.get("attribution_risks", []):
            lines.append(f"- {item}")
        lines.extend(["", "## Flow Hypotheses", ""])
        for item in model.get("flow_hypotheses", []):
            lines.append(f"- {item}")
        lines.extend(["", "## Cause-Class Map", ""])
        for item in model.get("cause_classes", []):
            lines.append(f"### {item.get('class')}")
            lines.append("")
            lines.append(item.get("read", "No read available."))
            lines.append("")
            lines.append("Evidence:")
            for evidence in item.get("evidence", []):
                lines.append(f"- {evidence}")
            lines.append("")
            lines.append(f"Next check: {item.get('next_check', 'unknown')}")
            lines.append("")
        lines.extend(["## Evidence Gaps", ""])
        for item in model.get("evidence_gaps", []):
            lines.append(f"- {item}")
        lines.extend(["", "## Leadership Actions", ""])
        for action in model.get("leadership_actions", []):
            lines.append(f"- {action.get('owner')} / {action.get('due')}: {action.get('action')}")
        lines.extend(["", "## Dashboard Gap", "", model.get("dashboard_gap", "")])
        path = self._write_artifact(run_id, "operating-model.md", "\n".join(lines).strip() + "\n")
        return {
            "artifact_path": str(path),
            "recorded_signal": model.get("recorded_signal"),
            "decision_rule": model.get("decision_rule"),
            "cause_classes": [
                item.get("class") for item in model.get("cause_classes", [])
                if item.get("active")
            ],
        }

    def _build_decision_cockpit(self, run_id: str, review: dict[str, Any]) -> dict[str, Any]:
        cockpit = review.get("decision_cockpit", {})
        target = cockpit.get("target_attainment", {})
        model = review.get("operating_model", {})
        lines = [
            f"# Decision Cockpit - {review.get('line_id', 'line')}",
            "",
            "## Current Decision",
            "",
            f"- Suspected constraint: {cockpit.get('suspected_constraint', 'unknown')}",
            f"- Confidence: {cockpit.get('confidence', 'unknown')}",
            f"- Decision: {cockpit.get('decision', 'No decision available.')}",
            f"- Target status: {cockpit.get('target_status', 'unknown')}",
            f"- SKU/job status: {cockpit.get('sku_status', 'unknown')}",
            "",
            "## Operating Guardrail",
            "",
            f"- Best recorded signal: {model.get('recorded_signal', cockpit.get('suspected_constraint', 'unknown'))}",
            f"- Cause-class rule: {model.get('decision_rule', 'Classify the true cause before approving RCA.')}",
            "",
            "## Next Supervisor Rule",
            "",
            cockpit.get(
                "next_observation_rule",
                "Record actual area, condition, active SKU/job, and target status for each generic stop.",
            ),
            "",
            "## What Would Prove It",
            "",
        ]
        for item in cockpit.get("proof_to_seek", []):
            lines.append(f"- {item}")
        lines.extend(["", "## What Would Disprove It", ""])
        for item in cockpit.get("disproof_to_watch", []):
            lines.append(f"- {item}")
        lines.extend([
            "",
            "## Target / Rate Context",
            "",
            f"- Rows with target/performance context: {target.get('intervals', 0)}",
            f"- Average performance: {_pct(target.get('avg_performance'))}",
            f"- Below-target rate: {_pct(target.get('below_target_rate'))}",
            f"- Target gap: {_number(target.get('target_gap_units'))} calculation units",
            f"- Rate loss: {_number(target.get('rate_loss_hours'))} hours",
            "",
            "## Top Job / SKU Signals",
            "",
        ])
        if cockpit.get("sku_signals"):
            lines.append("SKU rollups:")
            for item in cockpit.get("sku_signals", [])[:8]:
                lines.append(
                    f"- SKU {item.get('sku')}: {item.get('jobs')} jobs, "
                    f"performance {_pct(item.get('avg_performance'))}, "
                    f"OEE {_pct(item.get('avg_oee'))}, target gap {_number(item.get('target_gap_units'))}"
                )
            lines.append("")
            lines.append("Job rows:")
        for item in cockpit.get("job_signals", [])[:8]:
            label = item.get("label") or item.get("job_id") or "unknown job"
            lines.append(
                f"- {label}: performance {_pct(item.get('avg_performance'))}, "
                f"OEE {_pct(item.get('avg_oee'))}, target gap {_number(item.get('target_gap_units'))}"
            )
        if not cockpit.get("job_signals"):
            lines.append("- No job/SKU signals available. Add job export or schedule join before SKU regression.")
        lines.extend(["", "## Maintenance Questions", ""])
        for question in review.get("maintenance_questions", [])[:6]:
            lines.append(f"- {question}")

        path = self._write_artifact(run_id, "decision-cockpit.md", "\n".join(lines).strip() + "\n")
        return {
            "artifact_path": str(path),
            "suspected_constraint": cockpit.get("suspected_constraint"),
            "confidence": cockpit.get("confidence"),
            "target_status": cockpit.get("target_status"),
            "sku_status": cockpit.get("sku_status"),
        }

    def _build_event_fidelity_sprint(self, run_id: str, review: dict[str, Any]) -> dict[str, Any]:
        top_codes = review.get("top_codes", [])
        actionable = review.get("actionable_constraints", [])
        line_id = review.get("line_id", "line")
        short_events = review.get("short_stop_events", 0)
        unassigned_events = review.get("unassigned_events", 0)
        hidden_constraint = actionable[0]["name"] if actionable else next(
            (code["code"] for code in top_codes if code.get("code", "").lower() not in {"short stop", "unassigned", "unknown", "other"}),
            "top non-generic constraint",
        )
        hidden_hours = actionable[0].get("downtime_hours") if actionable else None
        questions = review.get("maintenance_questions", [])
        text = f"""# 14-Day Event Fidelity Sprint - {line_id}

## Why This Exists

The agent found {short_events:,} Short Stop events and {unassigned_events:,} Unassigned events.
That means the line has enough visibility loss to distort the Pareto.

The goal is not to punish operators for bad coding. The goal is to make the next
CI decision trustworthy.

## Sprint Objective

Reduce vague event coding and expose the validated cause class behind repeat interruptions.

## Daily Standard

- Every Unassigned stop over the local threshold must be corrected before shift close.
- Every repeat Short Stop must include machine/area and condition language.
- Supervisors review uncoded stops in the daily meeting.
- Maintenance and CI review the emerging non-generic signal and its observed cause class.

## Operating Hypothesis

{hidden_constraint} is the best recorded signal, not a proven physical cause.
Confidence is provisional until Short Stop and Unassigned are tied to observed
flow state, operator action, duration bucket, and restart condition.
{f"Current actionable-family signal: {hidden_hours:.1f} downtime hours." if isinstance(hidden_hours, (int, float)) else ""}

## Maintenance Questions

{chr(10).join(f"- {question}" for question in questions[:6]) or "- Ask maintenance what physical condition usually sits behind the generic Short Stop bucket."}

## Measures

- Short Stop event share
- Unassigned event share
- top non-generic downtime code
- top actionable equipment family hours
- observed cause-class split: equipment, flow/handoff, person/process, material, setup/speed, unknown
- repeat event count
- supervisor audit completion
- post-sprint Pareto shift

## 7 / 30 / 90 Verification

- 7 days: coding compliance improved and vague-code share is falling.
- 30 days: the validated cause class is clear enough for RCA.
- 90 days: the selected countermeasure reduced recurrence, not just renamed it.
"""
        path = self._write_artifact(run_id, "event-fidelity-sprint.md", text)
        return {
            "artifact_path": str(path),
            "line_id": line_id,
            "hidden_constraint_candidate": hidden_constraint,
            "short_stop_events": short_events,
            "unassigned_events": unassigned_events,
        }

    def _write_artifact(self, run_id: str, filename: str, text: str) -> Path:
        path = self.artifacts_dir / safe_filename(run_id) / safe_filename(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_text(path, text)
        return path

    def _append_memory(self, run: HarnessRun, outputs: dict[str, Any]) -> None:
        note = f"- {run.created_at}: {run.message} -> tools {[call.name for call in run.tool_calls]}\n"
        existing = self.memory_file.read_text() if self.memory_file.exists() else "# Harness Memory\n\n"
        _atomic_write_text(self.memory_file, existing + note)

    def _save_run(self, run: HarnessRun) -> Path:
        path = self.runs_dir / f"{run.run_id}.json"
        _atomic_write_text(path, json.dumps(run.to_dict(), indent=2, default=str))
        return path

    def _final_answer(self, run: HarnessRun, outputs: dict[str, Any]) -> str:
        parts = [f"Run {run.run_id} complete."]
        if "run_line_review" in outputs:
            review = outputs["run_line_review"]
            parts.append(
                f"Line review built for {review.get('line_id')}: visibility "
                f"{review.get('visibility_score')}/100."
            )
        if "run_shift_workflow" in outputs:
            wf = outputs["run_shift_workflow"]
            decision = wf.get("agent_report", {}).get("final_answer", {}).get("decision", {})
            parts.append(
                f"Shift workflow built around {decision.get('constraint')} as the best recorded signal "
                f"with {decision.get('risk_level')} risk."
            )
        parts.append(f"Artifacts: {', '.join(run.artifacts)}")
        return " ".join(parts)


def _run_id() -> str:
    return "mfg-agent-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else stripped[3:]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
    return stripped.strip()


def _validate_workflow(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {
            "name": "Manufacturing agent workflow",
            "rationale": "Run trusted manufacturing tools and build the next useful operating artifacts.",
        }
    return {
        "name": str(raw.get("name") or "Manufacturing agent workflow")[:120],
        "rationale": str(raw.get("rationale") or "Run trusted manufacturing tools and build the next useful operating artifacts.")[:500],
    }


def _validate_artifact_specs(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    specs: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        filename = safe_filename(str(item.get("filename") or "agent-artifact.md"))
        if not filename.endswith(".md"):
            filename += ".md"
        sections = [str(section)[:80] for section in item.get("sections", []) if str(section).strip()]
        specs.append({
            "filename": filename,
            "title": str(item.get("title") or filename.removesuffix(".md").replace("-", " ").title())[:120],
            "purpose": str(item.get("purpose") or "Build a workflow artifact from tool evidence.")[:500],
            "sections": sections[:8] or ["Operating Judgment", "Next Actions", "Verification"],
        })
        if len(specs) >= 3:
            break
    return specs


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(text)
        tmp_name = handle.name
    os.replace(tmp_name, path)


def _role_focus(text: str) -> str:
    if "supervisor" in text or "passdown" in text:
        return "Production Supervisor"
    if "ci" in text or "rca" in text or "continuous improvement" in text:
        return "CI Manager"
    if "production manager" in text or "schedule" in text:
        return "Production Manager"
    return "mixed"


def _compact_output(output: dict[str, Any]) -> dict[str, Any]:
    """Keep run traces useful without duplicating full artifacts."""
    compact = dict(output)
    if "monthly_metrics" in compact:
        compact["monthly_metrics"] = compact["monthly_metrics"][:3]
    if "role_briefs" in compact:
        compact["role_briefs"] = compact["role_briefs"][:3]
    if "tool_calls" in compact:
        compact["tool_calls"] = compact["tool_calls"][:5]
    return compact


def _artifact_section_lines(section: str, outputs: dict[str, Any]) -> list[str]:
    lower = section.lower()
    review = outputs.get("run_line_review", {})
    workflow = outputs.get("run_shift_workflow", {})
    decision = workflow.get("agent_report", {}).get("final_answer", {}).get("decision", {}) if workflow else {}
    if "judgment" in lower:
        return [
            review.get("management_signal") or "Use the parsed plant evidence before making an operating call.",
            f"Visibility score: {review.get('visibility_score', 'n/a')}/100",
        ]
    if "supervisor" in lower or "routine" in lower:
        actions = workflow.get("agent_report", {}).get("final_answer", {}).get("supervisor_actions", [])
        if actions:
            return [f"- {action}" for action in actions[:8]]
        return [
            "- Review Short Stop and Unassigned coding before shift close.",
            "- Correct vague events while the context is still fresh.",
            "- Escalate repeat constraints with evidence, not anecdotes.",
        ]
    if "manager" in lower or "control" in lower:
        return [
            f"- Line: {review.get('line_id', 'n/a')}",
            f"- Months covered: {review.get('months_covered', 'n/a')}",
            f"- Current constraint: {decision.get('constraint', 'not established')}",
            "- Hold supervisors accountable to event fidelity and follow-through cadence.",
        ]
    if "ci" in lower or "experiment" in lower:
        top_codes = review.get("top_codes", [])
        code = top_codes[0].get("code") if top_codes else "top recurring code"
        return [
            f"- Treat {code} as the first improvement hypothesis, unless visibility loss is masking the real constraint.",
            "- Run a time-boxed event-fidelity sprint before locking a capital or engineering fix.",
            "- Re-run the Pareto after coding improves.",
        ]
    if "verify" in lower or "verification" in lower:
        return [
            "- 7 days: confirm action completion and coding discipline.",
            "- 30 days: verify recurrence and Pareto movement.",
            "- 90 days: confirm the countermeasure changed performance, not only labels.",
        ]
    return [
        "- Built from trusted harness tool outputs.",
        f"- Available outputs: {', '.join(outputs.keys()) or 'none'}",
    ]


def _next_action(outputs: dict[str, Any]) -> str:
    review = outputs.get("run_line_review")
    if review and review.get("visibility_score", 100) < 75:
        return "Use the decision cockpit to run the next observation cycle, then re-run the Pareto after coding improves."
    if "run_shift_workflow" in outputs:
        return "Review the generated passdown and verification follow-ups with the responsible supervisor."
    if "inspect_data" in outputs:
        return "Run a line review or shift workflow once the target role and line are clear."
    return "Add plant data to the harness workspace and run the first tool pass."


def _pct(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value:.1%}"
    return "n/a"


def _number(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value:,.1f}"
    return "n/a"