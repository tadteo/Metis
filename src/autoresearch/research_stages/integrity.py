"""Focused scientific stage handlers; the workflow owns dispatch and legal edges."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

from ..contracts import RunState, Stage
from ..integrity import Claim, attempt_summary, verify_claims
from ..literature import Literature
from ..references import audit_references

if TYPE_CHECKING:
    from ..agents import AgentRunner
    from ..config import ResearchConfig
    from ..engine import Engine


def finalize(engine: Engine, s: RunState, c: ResearchConfig, agents: AgentRunner) -> None:
    best = engine._idea(s, s.selected_idea)
    if not s.manuscript or not best.workspace or not best.metrics:
        raise ValueError("finalization requires manuscript, measured best result and code")
    # Every seed in the selected full benchmark must reproduce. Pending work is
    # recovered before allocating a new workspace, and failures remain evidence.
    if not engine._reproduce_selected(s, c, best):
        return
    if c.mode == "live":
        source = engine._pristine_input(s, best.workspace)
        if c.integrity.require_claim_ledger:
            extracted = agents.run(s, "claim_extraction")
            raw_claims = extracted.structured.get("claims")
            if not isinstance(raw_claims, list):
                raise ValueError("claim extractor did not return a complete claim ledger")
            claims = [Claim.model_validate(item) for item in raw_claims]
            report = verify_claims(s, claims, source)
            for role in ("claim_coverage", "citation_entailment", "method_alignment"):
                audit = agents.run(s, role, {"claim_report": report, "source_dir": str(source)})
                report[role] = audit.model_dump()
                if audit.decision != "accept":
                    report["issues"].append(f"{role}: {audit.feedback or audit.summary}")
            report["passed"] = not report["issues"]
            report["coverage_verified"] = report["claim_coverage"]["decision"] == "accept"
            engine.store.artifact(
                s.id, "claim_audit", f"claim-audit-v{s.version}.json", json.dumps(report, indent=2)
            )
            engine.store.event(
                s.id,
                "claim_audit",
                s.stage,
                {
                    "passed": report["passed"],
                    "issues": report["issues"],
                    "claims_checked": len(claims),
                },
            )
            s.memory.append(
                {
                    "kind": "claim_audit",
                    "passed": report["passed"],
                    "issues": report["issues"],
                    "version": s.version,
                }
            )
            if report["issues"]:
                s.feedback = (
                    "Repair unsupported claims or conduct missing experiments: "
                    + "\n".join(report["issues"])
                )
                s.counters["integrity_repairs"] = s.counters.get("integrity_repairs", 0) + 1
                if s.counters["integrity_repairs"] > c.integrity.citation_repair_rounds:
                    raise ValueError(
                        "claim integrity repair budget exhausted; audit remains unresolved"
                    )
                s.stage = Stage.DRAFT
                return
        citations = audit_references(s.manuscript, s.evidence, engine.literature or Literature(c))
        engine.store.event(
            s.id,
            "reference_audit",
            s.stage,
            {"verified": citations.verified, "issues": citations.issues},
        )
        s.memory.append(
            {
                "kind": "reference_audit",
                "verified": citations.verified,
                "issues": citations.issues,
                "version": s.version,
            }
        )
        if citations.issues:
            s.counters["citation_repairs"] = s.counters.get("citation_repairs", 0) + 1
            if s.counters["citation_repairs"] > c.integrity.citation_repair_rounds:
                raise ValueError(
                    "citation verification repair budget exhausted; inspect reference audit"
                )
            s.feedback = (
                "Correct the bibliography using independently retrieved evidence: "
                + "\n".join(citations.issues)
            )
            s.stage = Stage.DRAFT
            return
    out = engine._judge(
        s,
        agents,
        {
            "source_dir": str(engine._pristine_input(s, best.workspace)),
            "selected_source": engine._source_context(Path(best.workspace))
            if c.mode == "demo"
            else {},
        },
    )
    if out.decision == "accept":
        if c.mode == "live" and (c.heldout_provider or "heldout_review" in c.role_commands):
            frozen = hashlib.sha256(s.manuscript.encode()).hexdigest()
            heldout = agents.run(
                s, "heldout_review", {"frozen_manuscript_sha256": frozen, "evaluation_only": True}
            )
            s.reviews.append(
                {
                    "kind": "heldout",
                    "manuscript_sha256": frozen,
                    "review": heldout.model_dump(),
                    "optimization_feedback": False,
                }
            )
            engine.store.artifact(
                s.id,
                "heldout_review",
                f"heldout-{frozen[:12]}.json",
                heldout.model_dump_json(indent=2),
            )
        s.status, s.stage = "completed", Stage.COMPLETE
        s.outcome = s.outcome or "completed_without_simulated_acceptance"
        engine.store.artifact(s.id, "final_manuscript", f"final-v{s.version}.md", s.manuscript)
        engine.store.artifact(
            s.id,
            "reproducibility",
            f"reproducibility-v{s.version}.json",
            json.dumps(
                {
                    "selected": best.model_dump(),
                    "experiments": [e.model_dump() for e in s.experiments],
                    "config": c.model_dump(),
                    "attempts": attempt_summary(s),
                    "usage": engine.store.usage(s.id),
                },
                indent=2,
            ),
        )
    elif out.decision == "refine":
        allowed = {Stage.FULL_ENGINEER, Stage.ABLATION_PLAN, Stage.DRAFT, Stage.PEER_REVIEW}
        target = Stage(out.return_stage or Stage.DRAFT)
        if target not in allowed:
            raise ValueError("integrity verifier returned unsupported repair stage")
        s.stage = target
        s.counters["reproduced_final"] = 0
    else:
        engine._stop(s, "integrity_rejected", failed=True)
