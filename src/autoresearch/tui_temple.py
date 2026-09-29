"""Focusable, finite Home animation with local mouse/keyboard controls."""

from __future__ import annotations

import math
import time

from rich.text import Text
from textual import events
from textual.binding import Binding
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Static

from .temple import SCENE, render_ascii


class TempleWidget(Static, can_focus=True):
    DEFAULT_CSS = """
    TempleWidget { height: 21; color: $text-muted; padding: 1; }
    TempleWidget:focus { color: $accent; }
    """
    BINDINGS = [
        Binding("left", "turn(-0.15)", "Turn left", show=False),
        Binding("right", "turn(0.15)", "Turn right", show=False),
        Binding("up", "tilt(0.06)", "Tilt up", show=False),
        Binding("down", "tilt(-0.06)", "Tilt down", show=False),
        Binding("space", "toggle_motion", "Pause temple", show=False),
        Binding("r", "rebuild", "Rebuild temple", show=True),
        Binding("home", "reset_view", "Reset view", show=False),
    ]

    def __init__(self, *, id: str = "home-temple") -> None:
        super().__init__(id=id, markup=False)
        self.elapsed = 0.0
        self.yaw, self.pitch = SCENE.yaw, SCENE.pitch
        self.paused = False
        self.active = False
        self._last = 0.0
        self._timer: Timer | None = None
        self._drag: tuple[int, int] | None = None
        self._cache: tuple[int, int, float, float, float] | None = None
        self._drawing = ""

    def on_mount(self) -> None:
        if self.app.animation_level == "none":
            self.elapsed = SCENE.duration
        self._timer = self.set_interval(1 / 10, self._tick, pause=True)
        self.set_active(self.active)

    def set_active(self, active: bool) -> None:
        self.active = active
        self._last = time.monotonic()
        if not active:
            self._drag = None
            self.release_mouse()
        if self._timer:
            if active and not self.paused and self.elapsed < SCENE.duration:
                self._timer.resume()
            else:
                self._timer.pause()

    def _tick(self) -> None:
        now = time.monotonic()
        # A scrolled-out or covered Home must not consume rendering work/time.
        in_view = (
            self.visible
            and self.screen is self.app.screen
            and self.content_region.overlaps(self.screen.content_region)
        )
        for ancestor in self.ancestors:
            if isinstance(ancestor, Widget):
                in_view = (
                    in_view
                    and ancestor.display
                    and self.content_region.overlaps(ancestor.content_region)
                )
        if self.active and in_view and not self.paused:
            self.elapsed = min(SCENE.duration, self.elapsed + min(now - self._last, 0.2))
            self.refresh()
        self._last = now
        if self.elapsed >= SCENE.duration and self._timer:
            self._timer.pause()

    def action_turn(self, amount: float) -> None:
        self.yaw = (self.yaw + amount) % math.tau
        self.refresh()

    def action_tilt(self, amount: float) -> None:
        self.pitch = max(0.15, min(0.8, self.pitch + amount))
        self.refresh()

    def action_toggle_motion(self) -> None:
        if self.elapsed < SCENE.duration:
            self.paused = not self.paused
            self.set_active(self.active)
            self.refresh()

    def action_rebuild(self) -> None:
        self.elapsed = SCENE.duration if self.app.animation_level == "none" else 0.0
        self.paused = False
        self.set_active(self.active)
        self.refresh()

    def action_reset_view(self) -> None:
        self.yaw, self.pitch = SCENE.yaw, SCENE.pitch
        self.refresh()

    def on_mouse_down(self, event: events.MouseDown) -> None:
        if event.button == 1:
            self.focus()
            self._drag = (event.screen_x, event.screen_y)
            self.capture_mouse()
            event.stop()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self._drag is not None:
            x, y = self._drag
            self.action_turn((event.screen_x - x) * 0.05)
            self.action_tilt((event.screen_y - y) * 0.03)
            self._drag = (event.screen_x, event.screen_y)
            event.stop()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        self._drag = None
        self.release_mouse()

    def on_leave(self) -> None:
        if self._drag is None:
            self.release_mouse()

    def on_unmount(self) -> None:
        if self._timer:
            self._timer.stop()
        self.release_mouse()

    def render(self) -> Text:
        width = max(1, min(100, self.content_size.width))
        height = max(1, self.content_size.height)
        key = (width, height, self.elapsed, self.yaw, self.pitch)
        if self._cache != key:
            self._drawing = render_ascii(*key)
            self._cache = key
        return Text(self._drawing, justify="center", no_wrap=True)
