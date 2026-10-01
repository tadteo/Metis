"""Offline regression checks for the pilot's quality gate and outage accounting."""

from __future__ import annotations

import json
import runpy
import shutil
import sys
from pathlib import Path

import pytest

from autoresearch.config import ResearchConfig
from autoresearch.contracts import AgentOutput, FileEdit, Usage
from autoresearch.execution import Executor
from autoresearch.providers import ProviderError

FIXTURE = Path(__file__).resolve().parents[1] / "evaluations/ponytail"
REFERENCE = """import csv, io, re, statistics, math

def summarize(text):
    rows = csv.reader(io.StringIO(text), strict=True)
    try:
        header = next(rows)
        if [x.strip() for x in header] != ['method','seed','status','score']:
            raise ValueError('header')
        groups, seen = {}, set()
        for row in rows:
            if not row:
                continue
            if len(row) != 4:
                raise ValueError('shape')
            method, seed, status, score = [x.strip() for x in row]
            if not method or not re.fullmatch('[0-9]+', seed) or status not in {'success','failed'}:
                raise ValueError('record')
            identity = method, int(seed)
            if identity in seen:
                raise ValueError('duplicate')
            seen.add(identity)
            entry = groups.setdefault(method, {'attempted':0,'succeeded':0,'failed':0,'values':[]})
            entry['attempted'] += 1
            if status == 'success':
                value = float(score)
                if not math.isfinite(value):
                    raise ValueError('finite')
                entry['values'].append(value)
                entry['succeeded'] += 1
            else:
                if score:
                    raise ValueError('failed score')
                entry['failed'] += 1
        for entry in groups.values():
            values = entry.pop('values')
            entry['mean'] = statistics.mean(values) if values else None
            entry['stdev'] = statistics.stdev(values) if len(values) > 1 else None
        return groups
    except (StopIteration, csv.Error) as exc:
        raise ValueError('CSV') from exc
"""


def prepare(tmp_path, monkeypatch):
    module = runpy.run_path(str(FIXTURE / "run.py"))
    config = ResearchConfig()
    config.project.sota = {"private_metric": 1.0}
    config.references = [{"title": "PRIVATE_SENTINEL"}]
    path = tmp_path / "config.json"
    path.write_text(config.model_dump_json())
    output = tmp_path / "pilot"
    monkeypatch.setattr(
        sys, "argv", ["run.py", "--config", str(path), "--output", str(output), "--pairs", "1"]
    )
    return module["main"].__globals__, output


@pytest.mark.parametrize(
    "code,expected",
    [
        (REFERENCE, True),
        ("raise SystemExit(0)\n", False),
        (REFERENCE.replace("statistics.stdev(values)", "statistics.pstdev(values)"), False),
    ],
)
def test_exported_source_passes_only_after_all_independent_checks(
    tmp_path, monkeypatch, code, expected
):
    module, output = prepare(tmp_path, monkeypatch)
    monkeypatch.setitem(
        module,
        "run_coding",
        lambda *args: AgentOutput(
            summary="Offline fixture", files=[FileEdit(path="summary.py", content=code)]
        ),
    )

    def local_executor(config):
        config = config.model_copy(deep=True)
        config.backend, config.allow_local = "local", True
        return Executor(config)

    monkeypatch.setitem(module, "Executor", local_executor)
    module["main"]()
    results = json.loads((output / "results.json").read_text())
    assert len(results) == 2
    assert all(r["quality_passed"] is expected for r in results)
    protocol = json.loads((output / "protocol.json").read_text())
    assert protocol["config"]["project"]["sota"] != {"private_metric": 1.0}
    assert protocol["config"]["references"] == []
    assert protocol["config"]["execution"]["readonly_mounts"] == {}
    assert protocol["config"]["execution"]["resource_hosts"] == []


def test_provider_failure_stops_even_with_conservative_nonzero_token_estimate(
    tmp_path, monkeypatch
):
    module, output = prepare(tmp_path, monkeypatch)

    def unavailable(*args):
        raise ProviderError(
            "HTTP 503", usage=Usage(output_tokens=3000, cost_usd=0.03, estimated=True)
        )

    monkeypatch.setitem(module, "run_coding", unavailable)
    module["main"]()
    results = json.loads((output / "results.json").read_text())
    assert len(results) == 1
    assert results[0]["provider_failure"] and not results[0]["quality_passed"]
    assert len(json.loads((output / "protocol.json").read_text())["order"]) == 2


def test_opt_in_bundle_preserves_protocol_and_changes_only_coding_policy(tmp_path):
    from autoresearch.catalog import load_catalog

    module = runpy.run_path(str(FIXTURE / "run.py"))
    baseline = load_catalog(module["prepare_specs"](tmp_path / "baseline", False))
    enabled = load_catalog(module["prepare_specs"](tmp_path / "enabled", True))
    assert baseline.render("coding_step") == load_catalog().render("coding_step")
    assert baseline.digest == load_catalog().digest
    assert enabled.digest != baseline.digest
    assert baseline.definition("coding_step").tools == enabled.definition("coding_step").tools
    assert (
        baseline.definition("coding_step").validation
        == enabled.definition("coding_step").validation
    )
    for role in baseline.agents:
        if role != "coding_step":
            assert enabled.render(role) == baseline.render(role)
    assert baseline.prompt("coding_step") in enabled.prompt("coding_step")


def test_acceptance_uses_frozen_fixture_when_source_changes(tmp_path, monkeypatch):
    module, output = prepare(tmp_path, monkeypatch)
    live_fixture = tmp_path / "live-fixture"
    shutil.copytree(FIXTURE, live_fixture, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setitem(module, "FIXTURE", live_fixture)

    def generated(*args):
        (live_fixture / "acceptance.py").write_text("raise SystemExit(1)\n")
        return AgentOutput(
            summary="Offline fixture", files=[FileEdit(path="summary.py", content=REFERENCE)]
        )

    def local_executor(config):
        config = config.model_copy(deep=True)
        config.backend, config.allow_local = "local", True
        return Executor(config)

    monkeypatch.setitem(module, "run_coding", generated)
    monkeypatch.setitem(module, "Executor", local_executor)
    module["main"]()
    assert all(r["quality_passed"] for r in json.loads((output / "results.json").read_text()))
    assert (output / "fixture/acceptance.py").read_text() != (
        live_fixture / "acceptance.py"
    ).read_text()
