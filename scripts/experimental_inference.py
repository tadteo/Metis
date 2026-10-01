"""Run-scoped experimental inference without workload credentials or networking.

Operator tool, deliberately separate from the pinned scientific runtime. Start
with PYTHONPATH=src python scripts/experimental_inference.py RUN_ID. Its source and
fixed model/rate manifest are archived before it accepts requests.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from autoresearch.agents import AgentRunner
from autoresearch.contracts import AgentRequest, Usage
from autoresearch.privacy import redact
from autoresearch.providers import CompatibleProvider, ProviderError, strict_json
from autoresearch.runtime_support import ExecutionError, read_text, write_file
from autoresearch.store import BudgetExceeded, Store

LIMIT = 32768
ROLE = "experimental_decision"


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    model: str = Field(min_length=1, max_length=30)
    sample: str = Field(min_length=1, max_length=200)
    system: str = Field(min_length=1, max_length=4000)
    prompt: str = Field(min_length=1, max_length=20000)
    max_output_tokens: int = Field(default=512, ge=256, le=2048)


def digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


class Service:
    def __init__(self, store: Store, run_id: str) -> None:
        self.store, self.run_id = store, run_id
        self.config = store.get_config(run_id)
        if self.config.mode != "live" or self.config.execution.backend != "docker":
            raise ValueError("Experimental inference requires a live Docker run")
        self.root = store.run_dir(run_id)
        self.journal = self.root / "experimental-inference"
        self.journal.mkdir(mode=0o700, exist_ok=True)
        if self.journal.is_symlink():
            raise ValueError("Service journal must not be a symlink")
        self.providers = {"reference": self.config.provider}
        if self.config.cheap_provider is not None:
            self.providers["cheap"] = self.config.cheap_provider
        self.published: set[str] = set()
        self.manifest = {
            "version": 1,
            "run_id": run_id,
            "providers": {k: v.model_dump(mode="json") for k, v in self.providers.items()},
            "retries": 0,
            "output_limit": 2048,
            "source_sha256": {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (Path(__file__), Path(__file__).with_name("metis_decisions.py"))
            },
        }

    def register(self) -> None:
        """Refuse silent adapter changes; the journal is outside workload mounts."""
        path = self.journal / "manifest.json"
        if path.exists():
            if strict_json(read_text(self.journal, path.name, LIMIT)) != self.manifest:
                raise ValueError("Service configuration changed; reconcile explicitly")
        else:
            write_file(self.journal, path.name, json.dumps(self.manifest))
        self.store.artifact(
            self.run_id,
            "experimental_inference_service",
            "experimental-inference.json",
            json.dumps(self.manifest, sort_keys=True),
        )

        for filename in self.manifest["source_sha256"]:
            self.store.artifact_bytes(
                self.run_id,
                "experimental_inference_source",
                filename,
                Path(__file__).with_name(filename).read_bytes(),
            )

    def execute(self, value: Any) -> dict[str, Any]:
        decision = Decision.model_validate(value)
        if len(json.dumps(value).encode()) > LIMIT:
            raise ValueError("Experimental request exceeds byte limit")
        if decision.model not in self.providers:
            raise ValueError("Model alias is not in the run's saved provider allowlist")
        request_id = digest(value)
        cfg = self.providers[decision.model].model_copy(deep=True)
        cfg.retries = 0  # Each explicit file request is exactly one API attempt.
        cfg.max_output_tokens = min(cfg.max_output_tokens, decision.max_output_tokens)
        identity = digest({"request": value, "provider": cfg.model_dump(mode="json")})
        filename = identity + ".json"
        if (self.journal / filename).exists():
            receipt = strict_json(read_text(self.journal, filename, 2_000_000))
            self.publish_receipt(receipt)
            return receipt
        previous = self.store.call_for_request(self.run_id, ROLE, identity)
        if previous:
            # A crash can leave an unknown remote outcome. Replays never resend it.
            return {
                "request_id": request_id,
                "status": "uncertain",
                "call_id": previous["id"],
                "error": "Prior attempt has no receipt; reconcile before retrying",
            }
        state = self.store.get_run(self.run_id)
        if (
            time.time() - datetime.fromisoformat(state.created_at).timestamp()
            > self.config.budget.wall_seconds
        ):
            return {
                "request_id": request_id,
                "status": "budget_exhausted",
                "error": "Run wall-clock budget exhausted",
            }
        if self.store.is_paused(self.run_id) or state.status in {
            "paused",
            "blocked",
            "failed",
            "stopped",
            "completed",
            "budget_exhausted",
        }:
            return {"request_id": request_id, "status": "paused", "error": "Run is not active"}
        clean = redact(
            {"system": decision.system, "prompt": decision.prompt},
            self.config.privacy.redact_patterns,
        )
        request = AgentRequest(
            run_id=self.run_id,
            stage=state.stage.value,
            role=ROLE,
            system=clean["system"],
            prompt=clean["prompt"],
            temperature=0,
        )
        maximum = AgentRunner._reservation(cfg, request)
        call_id = self.store.reserve(self.run_id, ROLE, maximum, identity, idempotent=True)
        intent = {
            "request": value,
            "outbound": request.model_dump(mode="json"),
            "provider": cfg.model_dump(mode="json"),
            "call_id": call_id,
        }
        self.store.artifact(
            self.run_id,
            "experimental_inference_request",
            identity + "-request.json",
            json.dumps(intent),
        )
        try:
            response = CompatibleProvider(cfg).complete(request)
            usage, data, status = response.usage, response.data, "completed"
        except ProviderError as error:
            usage, data, status = error.usage, {"error": str(error)}, "failed"
        except Exception:
            usage = Usage(cost_usd=maximum, estimated=True)
            data, status = (
                {"error": "Unknown provider outcome; conservatively charged"},
                "uncertain",
            )
        receipt = {
            "request_id": request_id,
            "identity": identity,
            "sample": decision.sample,
            "model": cfg.model,
            "provider": cfg.name,
            "call_id": call_id,
            "status": status,
            "data": redact(data, self.config.privacy.redact_patterns),
            "usage": usage.model_dump(mode="json"),
            "stage": state.stage.value,
        }
        receipt["receipt_sha256"] = digest(receipt)
        # A crash after this write replays settlement, not the remote request.
        write_file(self.journal, filename, json.dumps(receipt))
        self.publish_receipt(receipt)
        return receipt

    def publish_receipt(self, receipt: dict[str, Any]) -> None:
        if receipt["identity"] in self.published:
            return
        self.store.artifact(
            self.run_id,
            "experimental_inference_receipt",
            receipt["identity"] + "-receipt.json",
            json.dumps(receipt),
        )
        self.store.settle(receipt["call_id"], Usage.model_validate(receipt["usage"]))
        self.published.add(receipt["identity"])

    def poll(self) -> None:
        # Only the two existing workload layouts; never source, artifacts or journals.
        for pattern in (
            "coding/*/workspace/metis-inference/*.request.json",
            "experiments/*/metis-inference/*.request.json",
        ):
            for path in self.root.glob(pattern):
                if not re.fullmatch(r"[a-f0-9]{64}\.request\.json", path.name):
                    continue
                relative = str(path.relative_to(self.root))
                response_path = relative.replace(".request.json", ".response.json")
                try:
                    value = strict_json(read_text(self.root, relative, LIMIT))
                    if digest(value) != path.name.removesuffix(".request.json"):
                        raise ValueError("Request filename does not match content")
                    if (self.root / response_path).exists():
                        read_text(self.root, response_path, 2_000_000)
                    receipt = self.execute(value)
                    encoded = json.dumps(receipt)
                    # Always derive replies from the controller journal, never trust sandbox files.
                    target = self.root / response_path
                    if (
                        not target.exists()
                        or read_text(self.root, response_path, 2_000_000) != encoded
                    ):
                        write_file(self.root, response_path, encoded)
                except BudgetExceeded:
                    try:
                        write_file(
                            self.root,
                            response_path,
                            json.dumps(
                                {
                                    "request_id": path.name.removesuffix(".request.json"),
                                    "status": "budget_exhausted",
                                    "error": "Shared run budget exhausted",
                                }
                            ),
                        )
                    except (OSError, ExecutionError):
                        continue
                except (ValueError, OSError, ExecutionError, RecursionError):
                    # Malformed or unsafe paths never reach a provider or escape the workspace.
                    continue


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id")
    parser.add_argument("--state-dir", type=Path)
    args = parser.parse_args()
    service = Service(Store(args.state_dir), args.run_id)
    lock = service.journal / "service.lock"
    import os

    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        service.register()
        print("Experimental inference service ready", args.run_id, flush=True)
        while True:
            service.poll()
            time.sleep(0.5)


if __name__ == "__main__":
    main()
