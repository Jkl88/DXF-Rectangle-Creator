from __future__ import annotations

import math
from dataclasses import dataclass

from app.models.base import ShutterLayoutParams

SHUTTER_WIDE_W = 11.4
SHUTTER_THIN_W = 0.6
SHUTTER_W = SHUTTER_WIDE_W + SHUTTER_THIN_W
SHUTTER_H = 80.0
GAP_HORIZONTAL = 20.0
GAP_VERTICAL = 6.5

SHUTTER_ANGLES = (0, 90, 180, 270)


@dataclass
class ShutterPart:
    cx: float
    cy: float
    width: float
    height: float
    angle: float
    thin: bool


def part_corners(part: ShutterPart) -> list[tuple[float, float]]:
    hw, hh = part.width / 2, part.height / 2
    rad = math.radians(part.angle)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    local = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
    return [
        (part.cx + lx * cos_a - ly * sin_a, part.cy + lx * sin_a + ly * cos_a)
        for lx, ly in local
    ]


def normalize_shutter_angle(angle: float) -> int:
    return int(round(angle / 90.0)) * 90 % 360


def _count_fit(span: float, unit: float, gap: float) -> int:
    if span < unit - 1e-9:
        return 0
    n = 1
    while True:
        total = n * unit + max(0, n - 1) * gap
        if total > span + 1e-9:
            return max(0, n - 1)
        n += 1


def region_bounds(cx: float, cy: float, width: float, height: float) -> tuple[float, float, float, float]:
    return cx - width / 2, cy - height / 2, cx + width / 2, cy + height / 2


def _layout_params(
    vertical_base: bool, params: ShutterLayoutParams,
) -> tuple[float, float, float, float, float, float, float, float]:
    """Return unit_w, unit_h, gap_x, gap_y, wide_w, wide_h, thin_w, thin_h."""
    unit_w = params.cell_width
    unit_h = params.cell_height
    gap_x = params.gap_vertical if vertical_base else params.gap_horizontal
    gap_y = params.gap_horizontal if vertical_base else params.gap_vertical
    if vertical_base:
        return (
            unit_w, unit_h, gap_x, gap_y,
            params.wide_width, params.cell_height,
            params.thin_width, params.cell_height,
        )
    return (
        unit_h, unit_w, gap_x, gap_y,
        params.cell_height, params.wide_width,
        params.cell_height, params.thin_width,
    )


def _rotate_point(x: float, y: float, rcx: float, rcy: float, deg: float) -> tuple[float, float]:
    if abs(deg) < 1e-9:
        return x, y
    rad = math.radians(deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    dx, dy = x - rcx, y - rcy
    return rcx + dx * cos_a - dy * sin_a, rcy + dx * sin_a + dy * cos_a


def _make_part(
    x: float, y: float, w: float, h: float, thin: bool,
    rcx: float, rcy: float, angle: float,
) -> ShutterPart:
    pcx, pcy = x + w / 2, y + h / 2
    ncx, ncy = _rotate_point(pcx, pcy, rcx, rcy, angle)
    return ShutterPart(ncx, ncy, w, h, angle, thin)


def layout_shutters(
    cx: float, cy: float, width: float, height: float,
    angle: float = 0,
    params: ShutterLayoutParams | None = None,
) -> list[ShutterPart]:
    """Symmetrically fill region with shutter elements."""
    if params is None:
        params = ShutterLayoutParams.defaults()
    angle = normalize_shutter_angle(angle)
    vertical_base = angle in (90, 270)
    rot = 180.0 if angle in (180, 270) else 0.0
    unit_w, unit_h, gap_x, gap_y, wide_w, wide_h, thin_w, thin_h = _layout_params(
        vertical_base, params,
    )
    nx = _count_fit(width, unit_w, gap_x)
    ny = _count_fit(height, unit_h, gap_y)
    if nx <= 0 or ny <= 0:
        return []
    pitch_x = unit_w + gap_x
    pitch_y = unit_h + gap_y
    total_w = nx * unit_w + max(0, nx - 1) * gap_x
    total_h = ny * unit_h + max(0, ny - 1) * gap_y
    left = cx - total_w / 2
    top = cy - total_h / 2
    parts: list[ShutterPart] = []
    for j in range(ny):
        for i in range(nx):
            sx = left + i * pitch_x
            sy = top + j * pitch_y
            if vertical_base:
                parts.append(_make_part(sx, sy, wide_w, wide_h, False, cx, cy, rot))
                parts.append(_make_part(sx + wide_w, sy, thin_w, thin_h, True, cx, cy, rot))
            else:
                parts.append(_make_part(sx, sy, wide_w, wide_h, False, cx, cy, rot))
                parts.append(_make_part(sx, sy + wide_h, thin_w, thin_h, True, cx, cy, rot))
    return parts


def thin_slats_for_export(
    cx: float, cy: float, width: float, height: float,
    angle: float = 0,
    params: ShutterLayoutParams | None = None,
) -> list[list[tuple[float, float]]]:
    return [
        part_corners(p)
        for p in layout_shutters(cx, cy, width, height, angle, params)
        if p.thin
    ]
