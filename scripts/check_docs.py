"""Check public guide links and the CLI reference without network or model calls."""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterator
from functools import partial
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt
from markdown_it.token import Token

from autoresearch.cli import _parser

ROOT = Path(__file__).resolve().parents[1]


class HTMLTargets(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.anchors: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if value is None:
                continue
            if name in {"href", "src"}:
                self.links.append(value)
            elif name == "srcset":
                self.links.extend(
                    item.strip().split()[0] for item in value.split(",") if item.strip()
                )
            elif name == "id" or (tag == "a" and name == "name"):
                self.anchors.add(value)


def walk(tokens: list[Token]) -> Iterator[Token]:
    for token in tokens:
        yield token
        yield from walk(token.children or [])


def markdown_targets(content: str) -> tuple[list[str], set[str]]:
    tokens = MarkdownIt("commonmark").parse(content)
    links: list[str] = []
    anchors: set[str] = set()
    html = HTMLTargets()
    for token in walk(tokens):
        if token.type == "link_open":
            links.append(token.attrGet("href") or "")
        elif token.type == "image":
            links.append(token.attrGet("src") or "")
        elif token.type in {"html_block", "html_inline"}:
            html.feed(token.content)
    for index, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        text = "".join(
            item.content
            for item in walk(tokens[index + 1].children or [])
            if item.type in {"text", "code_inline"}
        )
        slug = re.sub(r"[^\w\- ]", "", text.lower()).replace(" ", "-")
        candidate, suffix = slug, 0
        while candidate in anchors:
            suffix += 1
            candidate = f"{slug}-{suffix}"
        anchors.add(candidate)
    return links + html.links, anchors | html.anchors


def guide_paths(root: Path) -> list[Path]:
    # Historical plans/reviews and verbatim upstream skills are provenance, not current guides.
    paths = list(root.glob("*.md")) + list((root / "docs").glob("*.md"))
    for directory in ("examples", "evaluations"):
        paths.extend((root / directory).rglob("*.md"))
    return sorted(paths)


def check_links(root: Path) -> list[str]:
    root = root.resolve()
    parsed = {
        path: markdown_targets(path.read_text(encoding="utf-8")) for path in guide_paths(root)
    }
    errors: list[str] = []
    for source, (links, _) in list(parsed.items()):
        for link in links:
            url = urlsplit(link)
            if url.scheme or url.netloc:
                continue
            target = (source.parent / unquote(url.path)).resolve() if url.path else source
            label = f"{source.relative_to(root)}: {link}"
            if not target.is_relative_to(root) or not target.exists():
                errors.append(f"{label}: missing or outside repository")
            elif url.fragment and target.suffix == ".md":
                if target not in parsed:
                    parsed[target] = markdown_targets(target.read_text(encoding="utf-8"))
                if unquote(url.fragment) not in parsed[target][1]:
                    errors.append(f"{label}: missing heading/anchor")
    return errors


def command_parsers(parser: argparse.ArgumentParser) -> Iterator[argparse.ArgumentParser]:
    yield parser
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for child in action.choices.values():
                yield from command_parsers(child)


def cli_reference() -> str:
    parsers = list(command_parsers(_parser()))
    parts = [
        "# Metis CLI reference\n\n",
        "[Documentation](README.md) · [Getting started](getting-started.md) · [User guide](usage.md)\n\n",
        "Generated from the argument parser by `scripts/check_docs.py --write-cli`. "
        "Do not edit command help here; CI checks it against the source.\n\n",
        "Run commands from the checkout as `uv run --no-sync metis …`. "
        "Place global `--state-dir` and `--db-dir` options before the command. "
        "`autoresearch` is a compatibility alias.\n\n",
        "Creating a run does not execute it. `demo` runs the synthetic fixture immediately; "
        "`run` and `resume` start research and can incur charges. "
        "See the [user guide](usage.md) for settings recipes, control semantics and privacy.\n\n",
        "## Commands\n\n",
    ]
    for parser in parsers:
        parts.append(f"- [{parser.prog}](#{parser.prog.replace(' ', '-')})\n")
    for parser in parsers:
        parser.formatter_class = partial(parser.formatter_class, width=88)
        parts.append(f"\n## {parser.prog}\n\n```text\n{parser.format_help()}```\n")
    return "".join(parts)


def check_cli(root: Path) -> list[str]:
    path = root / "docs/cli.md"
    if not path.exists() or path.read_text(encoding="utf-8") != cli_reference():
        return [
            "docs/cli.md is stale; run uv run --no-sync python scripts/check_docs.py --write-cli"
        ]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-cli", action="store_true", help="Regenerate docs/cli.md")
    args = parser.parse_args()
    if args.write_cli:
        (ROOT / "docs/cli.md").write_text(cli_reference(), encoding="utf-8")
    errors = check_links(ROOT) + check_cli(ROOT)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Documentation links, images, anchors and generated CLI reference passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
