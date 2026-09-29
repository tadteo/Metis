"""Quiet terminal presentation; machine output remains plain JSON."""

from __future__ import annotations

import os
import re
from typing import Any

from rich.console import Console
from rich.table import Table
from rich.text import Text

from .appearance import PALETTES

WELCOME = """Metis welcomes you.
What question brings you here?

01  Prepare    metis setup       Set up your project, models and limits
02  Explore    metis tui         Open the terminal workspace
               metis serve       Open the browser workspace
03  Try it     metis demo        Run an offline synthetic demonstration

Settings       metis settings --help
All commands   metis --help

Prepare an inquiry, review its setup, then choose when to begin.
We follow the evidence, and leave room to revise.
"""


def clean(value: Any) -> Text:
    return Text(re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]", "", str(value)))


def print_status(value: Any, theme: str) -> None:
    palette = PALETTES[theme]
    console = Console(no_color="NO_COLOR" in os.environ or os.environ.get("TERM") == "dumb")
    console.print(Text("METIS  /  RESEARCH", style=palette["accent"]))
    console.print()
    if isinstance(value, list):
        if not value:
            console.print("No research yet. Begin with metis setup, or try metis demo.")
            return
        table = Table(box=None, padding=(0, 2, 1, 0), header_style=palette["accent"])
        for label in ("Run", "Title", "Stage", "Status"):
            table.add_column(label)
        for row in value:
            table.add_row(*(clean(row[key]) for key in ("id", "title", "stage", "status")))
        console.print(table)
        console.print("Inspect: metis status RUN_ID   ·   Full data: metis status --json")
    else:
        run = value["run"]
        console.print(clean(run["title"]))
        console.print(clean(f"{run['id']}  /  {run['stage']}  /  {run['status']}"))
        console.print()
        console.print(clean(run["objective"]))
        console.print()
        console.print(clean(f"Usage: {value['usage']}"))
        console.print(
            "Workspace: metis tui --run RUN_ID   ·   Full data: metis status RUN_ID --json"
        )
