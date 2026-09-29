"""Presentation tokens and private preferences, deliberately outside run configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, cast

from .store import Store

ThemeName = Literal["charcoal", "cream"]
PALETTES: dict[str, dict[str, str]] = json.loads(
    (Path(__file__).parent / "assets/interface.json").read_text()
)


def load_theme(store: Store) -> ThemeName:
    with store.connect() as db:
        row = db.execute("SELECT value FROM interface_preferences WHERE name='theme'").fetchone()
    return cast(ThemeName, row[0]) if row and row[0] in PALETTES else "charcoal"


def save_theme(store: Store, theme: str) -> ThemeName:
    if theme not in PALETTES:
        raise ValueError("Choose charcoal or cream")
    with store.connect() as db:
        db.execute(
            "INSERT OR REPLACE INTO interface_preferences(name, value) VALUES('theme', ?)", (theme,)
        )
    return cast(ThemeName, theme)
