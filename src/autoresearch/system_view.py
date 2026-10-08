"""Human-readable projections of the same recorded AI system used by the runtime."""

from __future__ import annotations

import json
import re
from typing import Any


def mermaid(workflow: dict[str, Any]) -> str:
    lines = ["flowchart TD"]
    for name, node in workflow.get("nodes", {}).items():
        if not re.fullmatch(r"[a-z_]+", name):
            raise ValueError("invalid workflow node identifier")
        lines.append(f'  {name}["{name.replace("_", " ")}"]')
        for edge in node["transitions"]:
            target = edge["target"]
            if not re.fullmatch(r"[a-z_]+", target):
                raise ValueError("invalid workflow target identifier")
            lines.append(f"  {name} --> {target}")
    return "\n".join(lines)


def _plan_lines(plan: dict[str, Any] | None) -> list[str]:
    """The run's frozen model plan, shown before the workflow so it is easy to find."""
    lines: list[str] = []
    if plan and plan.get("routes"):
        router = plan.get("router") or {}
        source = (
            "model router, validated" if plan["status"] == "applied" else "deterministic planner"
        )
        detail = router.get("reason") or "; ".join(router.get("violations", []))
        lines.extend(["MODEL PLAN", plan["summary"]])
        lines.append(
            f"Routes from the {source}"
            + (f" (router {router['status']}: {detail})" if router.get("status") and detail else "")
        )
        for row in plan["routes"]:
            fallbacks = ", ".join(row["fallbacks"]) or "none"
            lines.append(f"{row['role']} ({row['class']}) → {row['model']}; then {fallbacks}")
            lines.append(f"  {row['why']}")
        for role, reason in plan.get("fixed_roles", {}).items():
            lines.append(f"{role} → fixed route: {reason}")
    elif plan and plan.get("error"):
        lines.extend(["MODEL PLAN", f"The recorded plan is unreadable: {plan['error']}"])
    return lines + [""] if lines else []


def system_text(info: dict[str, Any]) -> str:
    identity = info.get("identity") or {}
    lines = [
        "AI SYSTEM",
        f"Behavior bundle: {identity.get('bundle_sha256', 'not pinned')}",
        "",
        *_plan_lines(info.get("model_plan")),
        "WORKFLOW",
    ]
    for role, node in info.get("workflow", {}).get("nodes", {}).items():
        targets = ", ".join(edge["target"] for edge in node["transitions"])
        lines.append(f"{role} → {targets or '(terminal)'}")
        lines.append(f"  Agents: {', '.join(node['agents'])}; handler: {node['handler']}")
        lines.append(
            f"  Limits: {node['limits']}; inputs: {node['inputs']}; outputs: {node['outputs']}"
        )
        for edge in node["transitions"]:
            lines.append(f"  → {edge['target']}: {edge['condition']}; guards: {edge['guards']}")
        if node.get("instructions"):
            lines.append(f"  Tasks: {node['instructions']}")
    if info.get("extensions") or info.get("external_adapters"):
        lines.extend(
            [
                "",
                "CONFIGURED ADAPTERS",
                json.dumps(
                    {
                        "injected": info.get("extensions", {}),
                        "commands": info.get("external_adapters", {}),
                    },
                    indent=2,
                ),
            ]
        )
    lines.extend(["", "AGENTS"])
    for role, agent in info.get("agents", {}).items():
        lines.extend(
            [
                f"{role} · {agent.get('resolved_provider')} / {agent.get('resolved_model')} ({agent.get('routing_reason')})",
                f"  {agent['purpose']}",
                f"  Tools: {', '.join(agent['tools']) or 'none'}; handler: {agent['handler']}",
                f"  Inputs: {agent['inputs']}; output: {agent['output_schema']}",
                f"  Prompts: {agent['prompts']}; scope: {agent['prompt_scope']}; SHA-256: {agent['prompt_sha256']}",
                f"  Validation: {agent['validation']}; escalation: {agent['escalation']}",
                "",
            ]
        )
    return "\n".join(lines)


def prompt_text(info: dict[str, Any], role: str) -> str:
    agent = info.get("agents", {}).get(role)
    if agent is None:
        return "Original agent instructions are unavailable."
    scope = (
        "Local adapter/demo instructions; official writer prompts come from pinned upstream."
        if agent["prompt_scope"] == "upstream_native"
        else "Recorded resolved instructions"
    )
    return f"{role} · version {agent['version']}\n{scope}\n\n{info.get('prompts', {}).get(role, 'Not recorded')}"
