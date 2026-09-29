"""Offline scripted agents with real deterministic polynomial regression experiments.

This is an integration fixture, not evidence of autonomous research capability.
"""

from __future__ import annotations

import json
from typing import Any

from .contracts import AgentRequest, AgentResponse, Usage

BENCHMARK = r"""import argparse, json, math, os, random
p = argparse.ArgumentParser()
p.add_argument('--degree', type=int, default=1)
p.add_argument('--split', choices=['subset','full'], default='subset')
p.add_argument('--ridge', type=float, default=0.01)
a = p.parse_args()
rng = random.Random(int(os.environ.get('AUTORESEARCH_SEED', '0')))
n = 64 if a.split == 'subset' else 256
train = [(rng.uniform(-2, 2), rng.gauss(0, 0.15)) for _ in range(n)]
test = [(rng.uniform(-2, 2), rng.gauss(0, 0.15)) for _ in range(n)]
d = a.degree + 1
matrix = [[sum(x**(i+j) for x,e in train) + (a.ridge if i == j else 0) for j in range(d)] + [sum(x**i*(1.5*x+0.8*x*x+e) for x,e in train)] for i in range(d)]
for i in range(d):
    pivot = max(range(i,d), key=lambda j: abs(matrix[j][i]))
    matrix[i], matrix[pivot] = matrix[pivot], matrix[i]
    scale = matrix[i][i]
    matrix[i] = [v/scale for v in matrix[i]]
    for j in range(d):
        if i != j:
            scale = matrix[j][i]
            matrix[j] = [v-scale*w for v,w in zip(matrix[j], matrix[i])]
w = [row[-1] for row in matrix]
mse = sum((sum(v*x**i for i,v in enumerate(w))-(1.5*x+0.8*x*x+e))**2 for x,e in test)/n
metrics = {'score': 1/(1+mse), 'mse': mse}
with open('metrics.json','w') as f: json.dump(metrics, f)
print(json.dumps({'metrics': metrics, 'n_train': n, 'n_test': n, 'degree': a.degree}))
"""


class DemoProvider:
    def complete(self, request: AgentRequest) -> AgentResponse:
        ctx = json.loads(request.prompt)
        state, role = ctx["state"], request.role
        result: dict[str, Any] = {
            "summary": f"Offline fixture: {role}",
            "decision": "accept",
            "confidence": 1.0,
        }
        if role == "limitations":
            result["limitations"] = [
                "A linear predictor cannot represent quadratic curvature.",
                "Generalization must be measured on held-out samples.",
            ]
        elif role in {"generate_ideas", "evolve"}:
            count = ctx.get("requested_ideas", 1)
            offset = len(state["ideas"]) if role == "generate_ideas" else 0
            result["ideas"] = [
                {
                    "id": f"{'seed' if role == 'generate_ideas' else 'evolved'}-{state['round']}-{offset + i}",
                    "title": f"Polynomial hypothesis {state['round']}.{offset + i}",
                    "hypothesis": f"Fit quadratic features with regularization variant {state['round']}.{offset + i} and measure held-out error.",
                    "parents": [state["ideas"][0]["id"]]
                    if role == "evolve" and state["ideas"]
                    else [],
                }
                for i in range(count)
            ]
        elif role == "novelty":
            result["novelty_scores"] = {
                idea["id"]: 8.0 - i * 0.1 for i, idea in enumerate(state["ideas"])
            }
            result["evidence_ids"] = [e["id"] for e in state["evidence"]]
        elif role in {
            "baseline",
            "subset",
            "subset_engineer",
            "full",
            "full_engineer",
            "ablation",
            "ablation_refine",
            "rebuttal",
            "meta_refine",
        }:
            degree = 1 if role in {"baseline", "ablation"} else 2
            split = "subset" if role in {"baseline", "subset", "subset_engineer"} else "full"
            result.update(
                files=[{"path": "benchmark.py", "content": BENCHMARK}],
                argv=["python3", "benchmark.py", "--degree", str(degree), "--split", split],
            )
        elif (
            role == "subset_critic"
            and state["current_idea"] == "seed-0-0"
            and state["counters"].get("subset_engineering", 0) == 0
        ):
            result.update(
                decision="refine",
                feedback="Demonstrate the engineering loop with a repeated controlled fit.",
            )
        elif role == "select":
            result["selected_id"] = next(i["id"] for i in state["ideas"] if i["status"] == "good")
        elif role in {"ablation_plan", "rebuttal_plan"}:
            result["plans"] = [
                {
                    "id": "component-control" if role == "ablation_plan" else "replicate-control",
                    "question": "Does the measured gain reproduce?",
                    "intervention": "Remove quadratic features"
                    if role == "ablation_plan"
                    else "Repeat selected regression",
                }
            ]
        elif role == "ablation_critic" and state["counters"].get("ablation_refinements", 0) == 0:
            result.update(
                decision="refine",
                feedback="Test whether another engineering pass improves the measured result.",
            )
        elif role in {"draft", "revise"}:
            result["manuscript"] = (
                "# Offline polynomial regression demonstration\n\nThis manuscript is a scripted integration fixture, not an autonomous scientific discovery.\n\n## Method\nFit polynomial features by ridge normal equations; compare held-out synthetic regression data.\n\n## Results\n"
                + "\n".join(
                    f"- Experiment `{e['id']}`: {json.dumps(e['metrics'])}"
                    for e in state["experiments"]
                )
                + "\n\n## Limitations\nSynthetic data and scripted reviewers cannot validate research capability or novelty.\n"
            )
        elif role == "peer_review":
            result["score"] = 6 if state["counters"].get("peer_revisions", 0) == 0 else 8
            result["feedback"] = (
                "Repeat an experiment before revision. This is a scripted review score."
            )
        elif role == "meta_review":
            result.update(
                decision="refine",
                feedback="Exercise strict comparison and preservation of previous best outputs.",
            )
        return AgentResponse(
            data=result, usage=Usage(), model="offline-scripted-fixture", provider="demo"
        )
