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
EXTENTS = (
    (min(b.x - b.width / 2 for b in SCENE.blocks), max(b.x + b.width / 2 for b in SCENE.blocks)),
    (min(b.y - b.height / 2 for b in SCENE.blocks), max(b.y + b.height / 2 for b in SCENE.blocks)),
    (min(b.z - b.depth / 2 for b in SCENE.blocks), max(b.z + b.depth / 2 for b in SCENE.blocks)),
)
Point = tuple[float, float, float]
FACES = (
    ((0, 4, 6, 2), (-1, 0, 0)),
    ((1, 3, 7, 5), (1, 0, 0)),
    ((0, 1, 5, 4), (0, -1, 0)),
    ((2, 6, 7, 3), (0, 1, 0)),
    ((0, 2, 3, 1), (0, 0, -1)),
    ((4, 5, 7, 6), (0, 0, 1)),
)


def lift_at(block: Block, elapsed: float) -> float | None:
    """None before release, then a straight, steady fall that ends exactly at the course."""
    if elapsed < block.start:
        return None
    t = min(1.0, max(0.0, (elapsed - block.start) / SCENE.fall_seconds))
    return SCENE.fall_height * (1 - t)


def render_ascii(width: int, height: int, elapsed: float, yaw: float, pitch: float) -> str:
    """Rasterize visible block faces with a depth buffer and terminal cell proportions."""
    if width < 1 or height < 1:
        return ""
    cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)

    # Fit only the completed scene; falling stones must not move the camera.
    bounds = [
        (x * cy + z * sy, -y * cp + (-x * sy + z * cy) * sp)
        for x in EXTENTS[0]
        for y in EXTENTS[1]
        for z in EXTENTS[2]
    ]
    left, right = min(p[0] for p in bounds), max(p[0] for p in bounds)
    top, bottom = min(p[1] for p in bounds), max(p[1] for p in bounds)
    scale = min(max(1, width - 2) / (right - left), max(1, height - 2) * 2 / (bottom - top))
    center_y = height / 2 - (top + bottom) * scale / 4

    def project(x: float, y: float, z: float) -> Point:
        depth = -x * sy + z * cy
        return (
            width / 2 + (x * cy + z * sy) * scale,
            center_y + (-y * cp + depth * sp) * scale / 2,
            y * sp + depth * cp,
        )

    visible_faces = [
        (indices, 1.0 if normal[1] else 0.55 if normal[0] else 0.8)
        for indices, normal in FACES
        if normal[1] * sp + (-normal[0] * sy + normal[2] * cy) * cp > 0
    ]
    pixels = [" "] * (width * height)
    depths = [-math.inf] * (width * height)

    def triangle(a: Point, b: Point, c: Point, shade: float, falling: bool) -> None:
        denominator = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(denominator) < 1e-8:
            return
        for row in range(
            max(0, math.floor(min(a[1], b[1], c[1]))), min(height, math.ceil(max(a[1], b[1], c[1])))
        ):
            for column in range(
                max(0, math.floor(min(a[0], b[0], c[0]))),
                min(width, math.ceil(max(a[0], b[0], c[0]))),
            ):
                x, y = column + 0.5, row + 0.5
                u = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / denominator
                v = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / denominator
                w = 1 - u - v
                if min(u, v, w) < -1e-6:
                    continue
                depth = u * a[2] + v * b[2] + w * c[2]
                index = row * width + column
                if depth > depths[index]:
                    brightness = shade * max(0.25, min(1.0, (depth + 11) / 23))
                    glyph = "*" if falling else " .:-=+*#%@"[max(1, min(9, round(brightness * 9)))]
                    depths[index], pixels[index] = depth, glyph

    for block in SCENE.blocks:
        lift = lift_at(block, elapsed)
        if lift is None:
            continue
        vertices = [
            project(
                block.x + (block.width if i & 1 else -block.width) / 2,
                block.y + lift + (block.height if i & 2 else -block.height) / 2,
                block.z + (block.depth if i & 4 else -block.depth) / 2,
            )
            for i in range(8)
        ]
        for indices, shade in visible_faces:
            a, b, c, d = (vertices[i] for i in indices)
            triangle(a, b, c, shade, lift > 0)
            triangle(a, c, d, shade, lift > 0)
    return "\n".join("".join(pixels[row * width : (row + 1) * width]) for row in range(height))
