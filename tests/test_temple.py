"""Decorative animation must stay local, bounded and optional."""

from __future__ import annotations

import asyncio
import math
from pathlib import Path

import pytest
from textual.widgets import Button, TextArea

from autoresearch.store import Store
from autoresearch.temple import SCENE, lift_at, render_ascii
from autoresearch.tui import ResearchApp
from autoresearch.tui_temple import TempleWidget


def test_temple_finishes_every_stone_and_preserves_silhouette_when_rotated() -> None:
    assert all(lift_at(block, SCENE.duration) == 0 for block in SCENE.blocks)
    assert all(lift_at(block, 0) is None for block in SCENE.blocks)
    block = SCENE.blocks[0]
    heights = [lift_at(block, block.start + step * SCENE.fall_seconds / 10) for step in range(11)]
    assert heights == sorted(heights, reverse=True)
    views = [
        render_ascii(78, 20, SCENE.duration, yaw, SCENE.pitch) for yaw in (0, 0.7, math.pi / 2)
    ]
    assert len(set(views)) == 3
    for drawing in views:
        assert len(drawing.splitlines()) == 20
        assert all(len(line) == 78 for line in drawing.splitlines())
        assert len(drawing.replace(" ", "").replace("\n", "")) > 100
    assert render_ascii(0, 0, 0, 0, 0) == ""


@pytest.mark.parametrize("size", [(72, 15), (85, 19)])
def test_whole_temple_stays_in_frame_at_extreme_angles(size: tuple[int, int]) -> None:
    for yaw in (0, 0.7, math.pi / 2, math.pi, 4.5):
        for pitch in (0.15, 0.8):
            drawing = render_ascii(*size, SCENE.duration, yaw, pitch).splitlines()
            assert not drawing[0].strip() and not drawing[-1].strip()
            assert all(line[0] == line[-1] == " " for line in drawing)
            assert any(line.strip() for line in drawing)


@pytest.mark.parametrize("size", [(80, 24), (120, 40)])
def test_temple_keyboard_navigation_and_reduced_motion(
    tmp_path: Path, size: tuple[int, int]
) -> None:
    async def scenario() -> None:
        app = ResearchApp(Store(tmp_path))
        app.animation_level = "none"
        async with app.run_test(size=size) as pilot:
            temple = app.query_one(TempleWidget)
            assert temple.elapsed == SCENE.duration
            inquiry = app.query_one("#begin-inquiry", Button)
            assert 0 < inquiry.region.bottom < size[1]
            temple.focus()
            await pilot.pause()
            assert temple.region.bottom < size[1]
            before = temple.yaw
            await pilot.press("right", "up", "r")
            assert temple.yaw != before and temple.pitch > SCENE.pitch
            assert temple.elapsed == SCENE.duration
            await pilot.press("home")
            assert (temple.yaw, temple.pitch) == (SCENE.yaw, SCENE.pitch)
            app.action_welcome()
            app.query_one("#home-question", TextArea).focus()
            await pilot.press("r", "space", "x")
            assert app.query_one("#home-question", TextArea).text == "r x"
            assert temple.elapsed == SCENE.duration
            assert app.store.list_runs() == []
        app.controller.join()

    asyncio.run(scenario())


@pytest.mark.parametrize("size", [(80, 24), (120, 40)])
def test_temple_pauses_away_from_home_and_can_resume(tmp_path: Path, size: tuple[int, int]) -> None:
    async def scenario() -> None:
        app = ResearchApp(Store(tmp_path))
        async with app.run_test(size=size) as pilot:
            temple = app.query_one(TempleWidget)
            if size == (80, 24):
                await pilot.pause(0.3)
                assert temple.elapsed == 0
            temple.focus()
            await pilot.press("r")
            await pilot.pause(0.3)
            assert 0 < temple.elapsed < SCENE.duration
            await pilot.press("space")
            elapsed = temple.elapsed
            await pilot.pause(0.2)
            assert temple.elapsed == elapsed
            app._navigate("settings")
            await pilot.pause(0.2)
            assert not temple.active and temple.elapsed == elapsed
            app.action_welcome()
            temple.focus()
            await pilot.press("space")
            await pilot.pause(0.2)
            assert temple.elapsed > elapsed
            assert app.store.list_runs() == []
        app.controller.join()

    asyncio.run(scenario())
