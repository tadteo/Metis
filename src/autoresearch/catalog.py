"""Validated, inert AI behavior artifacts shared by runtime, provenance and interfaces.

Only named, trusted handlers and validators are selectable. Catalog files never
import Python or grant capabilities beyond the runtime's implemented tools.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath
from string import Template
from typing import Any, Literal

from pydantic import Field, ValidationError

from .contracts import AgentOutput, Model
from .typed_decisions import TypedQuestion, validate_answers
from .typed_decisions import output_schema as typed_output_schema

ROOT = Path(__file__).parent / "specs"
PUBLISHED = Path(__file__).parent / "assets" / "scholarpeer"
Validator = Literal[
    "limitations",
    "ideas",
    "novelty_scores",
    "selected_id",
    "plans",
    "experiment_plans",
    "manuscript",
    "score",
    "tool_action",
    "claims",
    "support",
    "checks",
    "structured",
    "attribution",
    "argv",
]
RouteRule = Literal[
    "frontier",
    "heldout",
    "role_panel",
    "original_role_panel",
    "original_role_provider",
    "role_provider",
    "cheap",
    "default",
]
IMPLEMENTED_TOOLS = frozenset(
    {
        "repository.list",
        "repository.read",
        "repository.search",
        "repository.edit",
        "repository.delete",
        "experiment.command",
        "session.history",
        "session.finish",
        "session.abort",
        "paper_orchestra.compose",
        "literature.search",
    }
)


class EscalationPolicy(Model):
    on_disagreement: bool = True
    on_low_confidence: bool = True
    on_invalid_output: bool = True
    unresolved: Literal["refine"] = "refine"


class ExperimentPlan(Model):
    id: str = Field(min_length=1, pattern=r".*\S.*")
    question: str = Field(min_length=1, pattern=r".*\S.*")
    intervention: str = Field(min_length=1, pattern=r".*\S.*")
    expected_evidence: str = Field(min_length=1, pattern=r".*\S.*")
    metric_requirements: list[str] = Field(default_factory=list)
    controls: list[str] = Field(default_factory=list)
    seed_controls: str = ""


class AblationAttribution(Model):
    mechanism: str = Field(min_length=1, pattern=r".*\S.*")
    supported: bool = Field(strict=True)
    generic_controls_only: bool = Field(strict=True)
    rationale: str = Field(min_length=1, pattern=r".*\S.*")
    experiment_ids: list[str] = Field(min_length=1)


class AgentDefinition(Model):
    role: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    inputs: list[str] = Field(min_length=1)
    output_schema: Literal["AgentOutput.v1", "LayaDecision.v1"]
    tools: list[str]
    model_policy: Literal["default", "cheap", "inherit", "heldout", "laya"]
    context_policy: Literal["research", "heldout"]
    handler: Literal["panel", "coding", "inspection", "writer", "review", "typed_decision"]
    panel: Literal["producers", "critics", "single"]
    aggregation: Literal["conservative", "merge_ideas", "artifact_selection", "advisory"]
    prompts: list[str] = Field(min_length=1)
    published_prompt: str | None = None
    validation: list[Validator]
    escalation: EscalationPolicy
    decisions: dict[str, Literal["accept", "refine", "reject"]] = Field(default_factory=dict)
    inspection_dimensions: list[str] = Field(default_factory=list)
    prompt_scope: Literal["local", "upstream_native", "typed_question"] = "local"
    typed_questions: dict[str, TypedQuestion] = Field(default_factory=dict)
    advisory_agent: str | None = None
    material_prompts: list[str] = Field(default_factory=list)
    upstream: dict[str, str] = Field(default_factory=dict)


class TaskTemplate(Model):
    version: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    template: str
    inputs: list[str] = Field(min_length=1)


class AgentDefinitions(Model):
    schema_version: Literal[1]
    id: str
    version: str
    agents: dict[str, AgentDefinition]
    tasks: dict[str, TaskTemplate] = Field(default_factory=dict)


class ModelPolicy(Model):
    schema_version: Literal[1]
    precedence: list[RouteRule]
    perspectives: list[str] = Field(min_length=1)
    upstream_slots: dict[
        Literal["writing_writer", "writing_reflection", "writing_plotting"],
        Literal["paper_orchestra"],
    ] = Field(default_factory=dict)


class ToolDefinition(Model):
    action: str
    permission: Literal["read", "write", "execute", "control"]
    description: str = Field(min_length=1)


class ToolDefinitions(Model):
    schema_version: Literal[1]
    tools: dict[str, ToolDefinition]


def _json(text: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key in AI specification")
            result[key] = value
        return result

    return json.loads(text, object_pairs_hook=pairs)


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class AgentCatalog:
    """One validated snapshot; reload before resume to detect operator edits."""

    def __init__(self, root: Path):
        if root.is_symlink():
            raise ValueError("AI specification directory must not be a symlink")
        self.root = root.resolve(strict=True)
        self._files: dict[str, str] = {}
        document = AgentDefinitions.model_validate(_json(self._read("agents.json")))
        self.id, self.version, self.agents = document.id, document.version, document.agents
        self.tasks = document.tasks
        self.models = ModelPolicy.model_validate(_json(self._read("policies/models.json")))
        self.tools = ToolDefinitions.model_validate(_json(self._read("tools/tools.json"))).tools
        if not self.agents:
            raise ValueError("AI catalog must contain agents")
        if set(self.tools) - IMPLEMENTED_TOOLS:
            raise ValueError("AI catalog names a tool without a trusted runtime implementation")
        for name, tool in self.tools.items():
            expected = (
                "execute"
                if name in {"experiment.command", "paper_orchestra.compose"}
                else "write"
                if name in {"repository.edit", "repository.delete"}
                else "control"
                if name in {"session.finish", "session.abort"}
                else "read"
            )
            if tool.action != name.rsplit(".", 1)[1] or tool.permission != expected:
                raise ValueError("tool declarations must match their trusted runtime actions")
        if len(set(self.models.precedence)) != len(self.models.precedence):
            raise ValueError("model routing rules must be unique")
        if not self.models.precedence or self.models.precedence[-1] != "default":
            raise ValueError("model routing must end with the default provider")
        if set(self.models.precedence) != {
            "frontier",
            "heldout",
            "role_panel",
            "original_role_panel",
            "original_role_provider",
            "role_provider",
            "cheap",
            "default",
        }:
            raise ValueError("model routing must account for all supported configuration overrides")
        for name, task in self.tasks.items():
            if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
                raise ValueError("invalid task template identifier")
            if not task.template.startswith("tasks/") or not task.template.endswith(".md"):
                raise ValueError(f"{name}: tasks must reference Markdown task artifacts")
            template = Template(self._read(task.template))
            if not template.is_valid() or set(template.get_identifiers()) != set(task.inputs):
                raise ValueError(f"{name}: task variables must match its declared inputs")
        self._published: dict[str, str] = {}
        for key, agent in self.agents.items():
            if key != agent.role:
                raise ValueError("agent key must equal its role identifier")
            if set(agent.tools) - set(self.tools):
                raise ValueError(f"{key}: unknown tool reference")
            if agent.handler == "inspection" and not agent.inspection_dimensions:
                raise ValueError(f"{key}: inspection requires explicit dimensions")
            if agent.handler == "inspection" and any(
                self.tools[tool].permission in {"write", "execute"} for tool in agent.tools
            ):
                raise ValueError(f"{key}: inspection cannot use mutating tools")
            if agent.advisory_agent:
                advisor = document.agents.get(agent.advisory_agent)
                if advisor is None or advisor.handler != "typed_decision":
                    raise ValueError(
                        f"{key}: advisory agent must reference a typed decision handler"
                    )
            if agent.handler == "typed_decision":
                if (
                    agent.model_policy != "laya"
                    or agent.output_schema != "LayaDecision.v1"
                    or not agent.typed_questions
                    or agent.prompt_scope != "typed_question"
                    or agent.context_policy != "research"
                    or agent.panel != "single"
                    or agent.aggregation != "advisory"
                    or agent.validation
                    or agent.decisions
                    or agent.advisory_agent
                ):
                    raise ValueError(
                        f"{key}: typed decision requires its transport, schema and question artifacts"
                    )
                if agent.tools:
                    raise ValueError(f"{key}: typed advisory decisions cannot use tools")
                if any(q.prompt not in agent.prompts for q in agent.typed_questions.values()):
                    raise ValueError(f"{key}: typed question prompt is not declared")
            elif (
                agent.output_schema != "AgentOutput.v1"
                or agent.typed_questions
                or agent.model_policy == "laya"
            ):
                raise ValueError(
                    f"{key}: ordinary agents require AgentOutput and generative model policy"
                )
            if agent.handler == "writer" and not agent.material_prompts:
                raise ValueError(f"{key}: writer requires evidence-reporting material prompts")
            for prompt in [*agent.prompts, *agent.material_prompts]:
                if not prompt.startswith("prompts/") or not prompt.endswith(".md"):
                    raise ValueError(f"{key}: prompts must reference Markdown prompt artifacts")
                self._read(prompt)
            if agent.published_prompt:
                self._load_published(agent.published_prompt)
        for name in ("common", "repair", "decision", "schema", "history", "review_adaptation"):
            self._read(f"prompts/{name}.md")

    def _read(self, relative: str) -> str:
        path = PurePosixPath(relative)
        if (
            path.is_absolute()
            or not path.parts
            or any(p in {".", ".."} for p in path.parts)
            or "\\" in relative
        ):
            raise ValueError("AI artifact path must remain inside the specification directory")
        target = self.root.joinpath(*path.parts)
        if any(
            parent.is_symlink()
            for parent in [target, *target.parents]
            if parent != self.root.parent
        ):
            raise ValueError("AI artifacts must not use symlinks")
        if not target.resolve(strict=True).is_relative_to(self.root):
            raise ValueError("AI artifact escapes the specification directory")
        if target.stat().st_size > 2_000_000:
            raise ValueError("AI artifact exceeds the size limit")
        content = target.read_text(encoding="utf-8")
        if not content.strip():
            raise ValueError("AI artifacts cannot be empty")
        self._files[relative] = content
        return content

    def _load_published(self, role: str) -> None:
        manifest_text = (PUBLISHED / "manifest.json").read_text()
        manifest = _json(manifest_text)
        if role not in manifest["prompts"]:
            raise ValueError(f"unknown published prompt: {role}")
        entry = manifest["prompts"][role]
        filename = str(entry["file"])
        if not re.fullmatch(r"[a-z_]+\.txt", filename):
            raise ValueError("invalid published prompt filename")
        content = (PUBLISHED / filename).read_text()
        if _digest(content) != entry["sha256"]:
            raise ValueError(f"published ScholarPeer prompt hash mismatch: {role}")
        self._files["published/scholarpeer/manifest.json"] = manifest_text
        self._files["published/scholarpeer/" + filename] = content
        self._published[role] = content

    def definition(self, role: str) -> AgentDefinition:
        try:
            return self.agents[role]
        except KeyError:
            raise ValueError(f"unknown agent role: {role}") from None

    def text(self, relative: str) -> str:
        """Return only catalogued, hashed content; never read an arbitrary path."""
        try:
            return self._files[relative]
        except KeyError:
            raise ValueError(f"unregistered AI artifact: {relative}") from None

    def prompt(self, role: str) -> str:
        agent = self.definition(role)
        chunks = [self._published[agent.published_prompt]] if agent.published_prompt else []
        return "\n".join([*chunks, *(self.text(p) for p in agent.prompts)])

    def render(self, role: str, override: str = "") -> str:
        agent = self.definition(role)
        if agent.handler == "typed_decision":
            return json.dumps(self.questions(role, override), sort_keys=True)
        common = (
            self.text("prompts/common.md").replace("$ROLE", role).replace("$VERSION", agent.version)
        )
        chunks = [common, override or self.prompt(role)]
        if agent.decisions:
            chunks.append(
                self.text("prompts/decision.md").replace("$DECISIONS", ", ".join(agent.decisions))
            )
        chunks.append(
            self.text("prompts/schema.md").replace("$SCHEMA", json.dumps(self.output_schema(role)))
        )
        return "\n".join(chunks)

    def questions(self, role: str, override: str = "") -> dict[str, dict[str, Any]]:
        agent = self.definition(role)
        if agent.handler != "typed_decision":
            raise ValueError(f"{role}: not a typed decision agent")
        return {
            name: {
                "type": question.type,
                "instructions": override or self.text(question.prompt).strip(),
                **({"criteria": question.criteria} if question.criteria is not None else {}),
            }
            for name, question in agent.typed_questions.items()
        }

    def validate_typed_output(self, role: str, output: dict[str, Any]) -> None:
        agent = self.definition(role)
        if agent.handler != "typed_decision":
            raise ValueError(f"{role}: not a typed decision agent")
        validate_answers(self.questions(role), output)

    def output_schema(self, role: str) -> dict[str, Any]:
        if self.definition(role).handler == "typed_decision":
            return typed_output_schema(self.questions(role))
        schema = AgentOutput.model_json_schema()
        if "experiment_plans" in self.definition(role).validation:
            schema["properties"]["plans"]["items"] = ExperimentPlan.model_json_schema()
        if "attribution" in self.definition(role).validation:
            schema["properties"]["structured"]["properties"] = {
                "attribution": AblationAttribution.model_json_schema()
            }
            # Required only for accepted outputs; refinements/rejections must not
            # fabricate measurements to satisfy the advertised response shape.
        return schema

    def render_task(self, name: str, **values: str) -> str:
        try:
            task = self.tasks[name]
        except KeyError:
            raise ValueError(f"unknown task template: {name}") from None
        if set(values) != set(task.inputs):
            raise ValueError(f"{name}: task values must match declared inputs")
        return Template(self.text(task.template)).substitute(values).strip()

    def manifest(self) -> dict[str, Any]:
        artifacts = {name: _digest(body) for name, body in sorted(self._files.items())}
        return {
            "schema_version": 1,
            "id": self.id,
            "version": self.version,
            "artifacts": artifacts,
            "tasks": {name: task.model_dump() for name, task in self.tasks.items()},
            "sha256": _digest(json.dumps(artifacts, sort_keys=True)),
        }

    @property
    def digest(self) -> str:
        return str(self.manifest()["sha256"])

    def snapshot(self) -> dict[str, str]:
        return dict(self._files)

    def validate_output(
        self, role: str, output: AgentOutput, context: dict[str, Any] | None = None
    ) -> AgentOutput:
        """Enforce accepted-role payloads before caching; rejection remains honest."""
        agent = self.definition(role)
        if not output.summary.strip():
            raise ValueError(f"{role}: output requires a substantive summary")
        # Declined/refinement producer results need no invented success payload.
        checks = (
            agent.validation
            if output.decision == "accept"
            else [v for v in agent.validation if v == "tool_action"]
        )
        for check in checks:
            valid = True
            if check == "limitations":
                valid = bool(output.limitations) and all(
                    item.strip() for item in output.limitations
                )
            elif check == "ideas":
                valid = bool(output.ideas) and all(
                    i.id.strip() and i.title.strip() and i.hypothesis.strip() for i in output.ideas
                )
            elif check == "novelty_scores":
                valid = bool(output.novelty_scores) and all(
                    math.isfinite(v) and 0 <= v <= 10 for v in output.novelty_scores.values()
                )
            elif check == "selected_id":
                valid = bool(output.selected_id and output.selected_id.strip())
            elif check == "plans":
                valid = bool(output.plans) and all(
                    isinstance(p.get("question"), str) and p["question"].strip()
                    for p in output.plans
                )
            elif check == "experiment_plans":
                valid = bool(output.plans)
                for plan in output.plans:
                    try:
                        ExperimentPlan.model_validate(plan)
                    except ValidationError:
                        valid = False
            elif check == "manuscript":
                valid = len(output.manuscript.strip()) >= 100
            elif check == "score":
                valid = output.score is not None
            elif check == "argv":
                valid = bool(output.argv) and all(arg and "\0" not in arg for arg in output.argv)
            elif check == "attribution":
                try:
                    attribution = AblationAttribution.model_validate(
                        output.structured.get("attribution")
                    )
                    valid = all(identifier.strip() for identifier in attribution.experiment_ids)
                except ValidationError:
                    valid = False
            elif check == "structured":
                valid = bool(output.structured)
            elif check in {"claims", "support", "checks"}:
                valid = isinstance(output.structured.get(check), (list, dict)) and bool(
                    output.structured[check]
                )
            elif check == "tool_action":
                permitted = {self.tools[t].action for t in agent.tools}
                original = (context or {}).get("original_role")
                if original and agent.model_policy == "inherit":
                    permitted &= {
                        self.tools[t].action for t in self.definition(str(original)).tools
                    }
                valid = len(output.plans) == 1 and output.plans[0].get("tool") in permitted
                if valid and output.plans[0]["tool"] == "command":
                    argv = output.plans[0].get("argv")
                    valid = (
                        isinstance(argv, list)
                        and bool(argv)
                        and all(isinstance(a, str) and a and "\0" not in a for a in argv)
                    )
            if not valid:
                raise ValueError(f"{role}: output violates {check} contract")
        return output


def load_catalog(root: Path | None = None) -> AgentCatalog:
    return AgentCatalog(root or ROOT)
