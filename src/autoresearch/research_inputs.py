"""Private paper inputs and versioned research discoveries, separate from pinned settings."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, model_validator

from .contracts import Evidence, Model, RunState
from .runtime_support import file_identity, read_text, write_file

if TYPE_CHECKING:
    from .config import ResearchConfig
    from .store import Store


class PaperInput(Model):
    name: str = Field(default="paper", min_length=1, max_length=200)
    locator: str = Field(default="", max_length=2000)
    text: str = Field(default="", max_length=500000)
    content_base64: str = Field(default="", max_length=14000000)

    @model_validator(mode="after")
    def has_content(self) -> PaperInput:
        if not (self.locator.strip() or self.text.strip() or self.content_base64):
            raise ValueError("Supply a paper identifier, text or PDF")
        if self.content_base64:
            raw = base64.b64decode(self.content_base64, validate=True)
            if len(raw) > 10000000:
                raise ValueError("Paper exceeds 10 MB")
        return self


class ResearchBrief(Model):
    outcome: Literal["grounded", "needs_input", "needs_access", "unresolved"]
    problem: str = ""
    reference_method: str = ""
    sources: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    implementation_needs: list[str] = Field(default_factory=list)
    question: str = ""

    @model_validator(mode="after")
    def usable(self) -> ResearchBrief:
        if self.outcome == "grounded":
            if not self.problem.strip() or not self.reference_method.strip() or not self.sources:
                raise ValueError("Grounded intake needs a problem, reference method and sources")
        elif not self.question.strip():
            raise ValueError("Unresolved intake must explain what information or access is missing")
        return self


def _extract_pdf(target: Path) -> list[dict[str, Any]]:
    """Drain output while enforcing time and macOS resident-memory bounds."""
    import time

    environment = {"PATH": os.defpath, "LANG": "C.UTF-8"}
    command = [sys.executable, "-m", "autoresearch.paper_input_worker", str(target)]
    started = time.monotonic()
    with subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environment
    ) as process:
        try:
            while True:
                try:
                    stdout, _ = process.communicate(timeout=0.25)
                    if process.returncode:
                        raise ValueError("PDF extraction worker failed")
                    pages: list[dict[str, Any]] = json.loads(stdout)
                    return pages
                except subprocess.TimeoutExpired:
                    if time.monotonic() - started > 30:
                        raise ValueError("PDF extraction exceeded its time limit") from None
                    if sys.platform == "darwin":
                        usage = subprocess.run(
                            ["/bin/ps", "-o", "rss=", "-p", str(process.pid)],
                            capture_output=True,
                            text=True,
                            timeout=2,
                            env=environment,
                            check=False,
                        )
                        if usage.returncode and process.poll() is None:
                            raise ValueError("Cannot verify PDF worker memory usage") from None
                        if usage.stdout.strip() and int(usage.stdout) > 512 * 1024:
                            raise ValueError("PDF extraction exceeded its memory limit") from None
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()


def admit_papers(store: Store, state: RunState, papers: list[PaperInput]) -> None:
    """Copy inputs without network/model calls; extracted text has page provenance."""
    if len(papers) > 20:
        raise ValueError("At most 20 associated papers per inquiry")
    directory = store.run_dir(state.id) / "papers"
    directory.mkdir(mode=0o700, exist_ok=True)
    for paper in papers:
        raw = (
            base64.b64decode(paper.content_base64, validate=True)
            if paper.content_base64
            else paper.text.encode()
        )
        if len(raw) > 10000000:
            raise ValueError("Paper exceeds 10 MB")
        digest = hashlib.sha256(raw or paper.locator.encode()).hexdigest()
        pages: list[dict[str, Any]] = []
        failure = ""
        filename = ""
        if raw:
            pdf = raw.startswith(b"%PDF-")
            filename = digest + (".pdf" if pdf else ".txt")
            target = directory / filename
            if not target.exists():
                target.write_bytes(raw)
                target.chmod(0o600)
            if pdf:
                try:
                    pages = _extract_pdf(target)
                except (subprocess.SubprocessError, ValueError):
                    failure = "PDF text extraction failed or exceeded limits; supply readable text."
            else:
                try:
                    pages = [{"page": 1, "text": raw.decode("utf-8")}]
                except UnicodeDecodeError:
                    failure = "Only PDF or UTF-8 text attachments are supported."
        content = "\n\n".join(f"[page {p['page']}]\n{p['text']}" for p in pages)
        if raw and not content.strip():
            failure = failure or "No readable text extracted; scanned PDFs need text or OCR."
        arxiv = re.search(
            r"(?:arxiv:|arxiv.org/(?:abs|pdf)/)?(\d{4}\.\d{4,5}(?:v\d+)?)(?:\.pdf)?$", paper.locator
        )
        evidence = Evidence(
            id=f"input-{digest[:20]}",
            title=paper.name,
            url=paper.locator,
            full_text=content[:500000],
            content_hash=digest,
            provider="user_attachment",
            identifiers={"arxiv": arxiv.group(1)} if arxiv else {},
            retrieval={
                "supplied": True,
                "original_sha256": digest,
                "pages": pages,
                "extraction_error": failure,
                "content_level": "full_text" if content else "identifier",
            },
        )
        state.evidence.append(evidence)
        state.materials.append(
            {
                "name": paper.name,
                "locator": paper.locator,
                "sha256": digest,
                "file": filename,
                "evidence_id": evidence.id,
                "extraction_error": failure,
            }
        )
    store.artifact(state.id, "research_inputs", "research-inputs.json", json.dumps(state.materials))


def resolved_config(config: ResearchConfig, state: RunState, store: Store) -> ResearchConfig:
    """Produce an ephemeral execution view; never write discovered facts into settings."""
    if not state.research_protocol:
        return config
    from .protocol import ResearchProtocol

    reference = state.research_protocol
    data = read_text(store.run_dir(state.id), reference["path"], 2000000)
    if hashlib.sha256(data.encode()).hexdigest() != reference["sha256"]:
        raise ValueError("Sealed research protocol changed")
    protocol = ResearchProtocol.model_validate_json(data)
    for path, digest in {
        **reference["protected_sha256"],
        **reference.get("measurement_sha256", {}),
    }.items():
        if (
            file_identity(store.run_dir(state.id) / reference["source_path"], path)["sha256"]
            != digest
        ):
            raise ValueError("Sealed measurement assets changed")
    result = config.model_copy(deep=True)
    project = result.project.model_dump()
    project.update(protocol.project_fields())
    if config.project.result_preference == "pareto":
        project["primary_metric"] = config.project.primary_metric
    from .config import ProjectConfig

    result.project = ProjectConfig.model_validate(project)
    return result


def save_brief(store: Store, state: RunState, brief: ResearchBrief) -> None:
    state.research_brief = {**brief.model_dump(), "input_revision": state.input_revision}
    state.intake_outcome = brief.outcome
    store.artifact(
        state.id,
        "research_brief",
        f"brief-{state.input_revision}-{state.version}.json",
        json.dumps(state.research_brief, indent=2),
    )
    write_file(
        store.run_dir(state.id),
        f"briefs/revision-{state.input_revision}.json",
        json.dumps(state.research_brief, indent=2),
    )


def paper_arguments(values: list[str]) -> list[dict[str, str]]:
    """CLI/TUI files are read on their controller; browser uploads carry bytes instead."""
    result = []
    for value in values:
        path = Path(value).expanduser()
        if not value.startswith(("https://", "http://")) and path.is_file():
            if path.is_symlink() or path.stat().st_size > 10000000:
                raise ValueError("Paper must be a regular file of at most 10 MB")
            result.append(
                {"name": path.name, "content_base64": base64.b64encode(path.read_bytes()).decode()}
            )
        else:
            result.append({"name": value[:200], "locator": value})
    return result
