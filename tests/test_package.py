"""Release check: execute the installed wheel outside the source checkout.

CI builds a wheel then sets AUTORESEARCH_TEST_WHEEL to its directory. Ordinary
unit runs do not need build tooling or network access.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


def test_wheel_contains_and_loads_all_behavior_and_program_assets(tmp_path: Path) -> None:
    wheel_directory = os.environ.get("AUTORESEARCH_TEST_WHEEL")
    if not wheel_directory:
        pytest.skip("release check requires AUTORESEARCH_TEST_WHEEL=dist after uv build --wheel")
    wheels = list(Path(wheel_directory).resolve().glob("*.whl"))
    assert len(wheels) == 1, "Build exactly one current wheel for the release check"
    installed = tmp_path / "installed"
    with zipfile.ZipFile(wheels[0]) as wheel:
        for member in wheel.namelist():
            assert not Path(member).is_absolute() and ".." not in Path(member).parts
        wheel.extractall(installed)
    environment = {
        **os.environ,
        "PYTHONPATH": str(installed),
        "AUTORESEARCH_WHEEL_ROOT": str(installed),
        "AUTORESEARCH_HOME": str(tmp_path / "state"),
    }
    script = """
import json
import os
from pathlib import Path
import autoresearch
assert Path(autoresearch.__file__).resolve().is_relative_to(Path(os.environ["AUTORESEARCH_WHEEL_ROOT"]).resolve())
from autoresearch.behavior import describe
from autoresearch.config import ResearchConfig
from autoresearch.engine import Engine
from autoresearch.runtime_support import program_source
from autoresearch.runtime_support.programs import PROGRAM_NAMES
from autoresearch.store import Store
info = describe(ResearchConfig())
assert 'meta_refine' in info['workflow']['nodes']
assert info['agents']['subset']['handler'] == 'coding'
for name in PROGRAM_NAMES:
    compile(program_source(name), name + ".py", "exec")
engine = Engine(Store())
state = engine.create('Installed wheel fixture', 'Verify packaged definitions', demo=True)
result = engine.run(state.id)
assert result.status == 'completed', result.error
print(json.dumps({'agents': len(info['agents']), 'bundle': result.behavior.bundle_sha256}))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads(result.stdout)
    assert report["agents"] >= 28 and len(report["bundle"]) == 64
