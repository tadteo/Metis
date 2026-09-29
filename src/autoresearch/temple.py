"""Shared decorative temple scene and terminal projection; independent of research state."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Block:
    x: float
    y: float
    z: float
    width: float
    height: float
    depth: float
    start: float


@dataclass(frozen=True)
class Scene:
    duration: float
    fall_seconds: float
    fall_height: float
    yaw: float
    pitch: float
    blocks: tuple[Block, ...]


def load_scene() -> Scene:
    data = json.loads((Path(__file__).parent / "static/temple.json").read_text())
    return Scene(
        data["duration"],
        data["fall_seconds"],
        data["fall_height"],
        data["yaw"],
        data["pitch"],
        tuple(Block(*block) for block in data["blocks"]),
    )


SCENE = load_scene()
Point = tuple[float, float, float]
FACES = ((0, 4, 6, 2), (1, 3, 7, 5), (0, 1, 5, 4), (2, 6, 7, 3), (0, 2, 3, 1), (4, 5, 7, 6))


@dataclass(frozen=True)
class OutlinePart:
    vertices: tuple[Point, ...]
    faces: tuple[tuple[int, ...], ...]
    start: float


def _outline_parts() -> tuple[OutlinePart, ...]:
    """Large structural pieces keep the colonnade legible in a few terminal rows."""
    parts = []

    def stone(x: float, y: float, z: float, w: float, h: float, d: float, start: float) -> None:
        vertices = tuple(
            (
                x + (w if i & 1 else -w) / 2,
                y + (h if i & 2 else -h) / 2,
                z + (d if i & 4 else -d) / 2,
            )
            for i in range(8)
        )
        parts.append(OutlinePart(vertices, FACES, start))

    stone(0, 0.2, 0, 8.4, 0.4, 12.4, 0.1)
    stone(0, 0.6, 0, 7.6, 0.4, 11.6, 1.4)
    columns = [(x, z) for z in (5.0, -5.0) for x in (-3.0, -1.0, 1.0, 3.0)]
    columns += [(x, z) for x in (-3.0, 3.0) for z in (0.0,)]
    for i, (x, z) in enumerate(columns):
        start = 2.8 + i * 1.0
        stone(x, 3.0, z, 0.65, 4.4, 0.65, start)
        stone(x, 5.35, z, 0.95, 0.3, 0.95, start + 1.4)
    for i, z in enumerate((-5.0, 5.0)):
        stone(0, 5.8, z, 7.3, 0.6, 1.0, 14.2 + i * 1.3)
    for i, x in enumerate((-3.15, 3.15)):
        stone(x, 5.8, 0, 1.0, 0.6, 9.0, 16.8 + i * 0.8)
    # A single pediment and pitched roof replace hundreds of tiny roof bricks.
    parts.append(
        OutlinePart(
            (
                (-3.8, 6.1, -5.7),
                (3.8, 6.1, -5.7),
                (0.0, 8.0, -5.7),
                (-3.8, 6.1, 5.7),
                (3.8, 6.1, 5.7),
                (0.0, 8.0, 5.7),
            ),
            ((0, 2, 1), (3, 4, 5), (0, 1, 4, 3), (0, 3, 5, 2), (1, 2, 5, 4)),
            SCENE.duration - SCENE.fall_seconds - 0.4,
        )
    )
    return tuple(parts)


OUTLINE_PARTS = _outline_parts()


def lift_at(block: Block, elapsed: float) -> float | None:
    """None before release, then a straight, steady fall that ends exactly at the course."""
    if elapsed < block.start:
        return None
    t = min(1.0, max(0.0, (elapsed - block.start) / SCENE.fall_seconds))
    return SCENE.fall_height * (1 - t)


def render_ascii(width: int, height: int, elapsed: float, yaw: float, pitch: float) -> str:
    """Hidden-line architecture in braille cells, with no dense surface shading.

    Each cell holds a 2-by-4 dot grid. Its square subpixels give diagonals and columns
    enough resolution even in a small terminal. Faces only occlude edges behind them.
    """
    if width < 1 or height < 1:
        return ""
    cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
    bounds = [
        (x * cy + z * sy, -y * cp + (-x * sy + z * cy) * sp)
        for x in (-4.2, 4.2)
        for y in (0.0, 8.0)
        for z in (-6.2, 6.2)
    ]
    left, right = min(p[0] for p in bounds), max(p[0] for p in bounds)
    top, bottom = min(p[1] for p in bounds), max(p[1] for p in bounds)
    pw, ph = width * 2, height * 4
    scale = min(max(1, pw - 12) / (right - left), max(1, ph - 12) / (bottom - top))
    center_y = ph / 2 - (top + bottom) * scale / 2

    def project(point: Point, lift: float) -> Point:
        x, y, z = point
        y += lift
        depth = -x * sy + z * cy
        return (
            pw / 2 + (x * cy + z * sy) * scale,
            center_y + (-y * cp + depth * sp) * scale,
            y * sp + depth * cp,
        )

    depths = [-math.inf] * (pw * ph)
    edges: list[tuple[Point, Point]] = []

    def triangle(a: Point, b: Point, c: Point) -> None:
        denominator = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(denominator) < 1e-8:
            return
        for row in range(
            max(0, math.floor(min(a[1], b[1], c[1]))), min(ph, math.ceil(max(a[1], b[1], c[1])))
        ):
            for column in range(
                max(0, math.floor(min(a[0], b[0], c[0]))), min(pw, math.ceil(max(a[0], b[0], c[0])))
            ):
                x, y = column + 0.5, row + 0.5
                u = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / denominator
                v = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / denominator
                w = 1 - u - v
                if min(u, v, w) >= -1e-6:
                    index = row * pw + column
                    depths[index] = max(depths[index], u * a[2] + v * b[2] + w * c[2])

    for part in OUTLINE_PARTS:
        if elapsed < part.start:
            continue
        lift = SCENE.fall_height * (1 - min(1.0, (elapsed - part.start) / SCENE.fall_seconds))
        vertices = [project(p, lift) for p in part.vertices]
        for face in part.faces:
            points = [vertices[i] for i in face]
            for i in range(1, len(points) - 1):
                triangle(points[0], points[i], points[i + 1])
        facing: dict[tuple[int, int], list[bool]] = {}
        for face in part.faces:
            a, b, c = (part.vertices[i] for i in face[:3])
            u, v = tuple(b[i] - a[i] for i in range(3)), tuple(c[i] - a[i] for i in range(3))
            nx, ny, nz = (
                u[1] * v[2] - u[2] * v[1],
                u[2] * v[0] - u[0] * v[2],
                u[0] * v[1] - u[1] * v[0],
            )
            front = ny * sp + (-nx * sy + nz * cy) * cp > 0
            for edge_a, edge_b in zip(face, (*face[1:], face[0]), strict=True):
                edge = (min(edge_a, edge_b), max(edge_a, edge_b))
                facing.setdefault(edge, []).append(front)
        for (edge_a, edge_b), sides in facing.items():
            # Structural stones need only their silhouette; keep the roof's ridge.
            if any(sides) and (not all(sides) or len(part.vertices) == 6):
                edges.append((vertices[edge_a], vertices[edge_b]))

    cells = [0] * (width * height)
    dots = ((1, 8), (2, 16), (4, 32), (64, 128))
    for a, b in edges:
        steps = max(1, math.ceil(max(abs(b[0] - a[0]), abs(b[1] - a[1])) * 2))
        for step in range(steps + 1):
            t = step / steps
            x, y = math.floor(a[0] + (b[0] - a[0]) * t), math.floor(a[1] + (b[1] - a[1]) * t)
            depth = a[2] + (b[2] - a[2]) * t
            if 0 <= x < pw and 0 <= y < ph and depth >= depths[y * pw + x] - 0.16:
                cells[(y // 4) * width + x // 2] |= dots[y % 4][x % 2]
    return "\n".join(
        "".join(
            chr(0x2800 + cell) if cell else " " for cell in cells[row * width : (row + 1) * width]
        )
        for row in range(height)
    )
