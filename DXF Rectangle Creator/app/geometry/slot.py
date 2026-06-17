"""Slot (oblong) hole geometry — two semicircular ends connected by straight edges.

For OVAL holes, ``width`` = distance between arc centers (local X),
``height`` = cap diameter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QPainterPath


@dataclass(frozen=True)
class SlotGeom:
    span: float
    cap: float
    long_outer: float
    arc_offset: float


def slot_geom(span: float, cap: float) -> SlotGeom:
    """span = distance between arc centers; cap = diameter of semicircular ends."""
    cap = max(0.0, cap)
    span = max(0.0, span)
    long_outer = span + cap if cap > 1e-9 else span
    return SlotGeom(span, cap, long_outer, span / 2.0)


def slot_is_round(span: float, cap: float, tol: float = 1e-9) -> bool:
    return span < tol


def slot_arc_centers_local(span: float, cap: float) -> tuple[tuple[float, float], tuple[float, float]]:
    g = slot_geom(span, cap)
    if g.arc_offset < 1e-9:
        return ((0.0, 0.0), (0.0, 0.0))
    o = g.arc_offset
    return ((-o, 0.0), (o, 0.0))


def to_world(cx: float, cy: float, angle_deg: float, lx: float, ly: float) -> tuple[float, float]:
    rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    return cx + lx * cos_a - ly * sin_a, cy + lx * sin_a + ly * cos_a


def slot_arc_centers_world(
    cx: float, cy: float, span: float, cap: float, angle_deg: float,
) -> tuple[tuple[float, float], tuple[float, float]]:
    c1, c2 = slot_arc_centers_local(span, cap)
    return (
        to_world(cx, cy, angle_deg, c1[0], c1[1]),
        to_world(cx, cy, angle_deg, c2[0], c2[1]),
    )


def slot_cap_dim_points(
    cx: float, cy: float, span: float, cap: float, angle_deg: float,
) -> tuple[tuple[float, float], tuple[float, float]]:
    ac1, _ = slot_arc_centers_local(span, cap)
    half = cap / 2.0
    p1 = to_world(cx, cy, angle_deg, ac1[0], -half)
    p2 = to_world(cx, cy, angle_deg, ac1[0], half)
    return p1, p2


def add_slot_path(path: QPainterPath, span: float, cap: float) -> None:
    """Slot outline in local coords; long axis along X."""
    if cap < 1e-9:
        return
    r = cap / 2.0
    if slot_is_round(span, cap):
        path.addEllipse(QRectF(-r, -r, cap, cap))
        return
    d = span / 2.0
    steps = 24
    path.moveTo(-d, -r)
    path.lineTo(d, -r)
    for i in range(1, steps):
        a = math.radians(-90.0 + 180.0 * i / steps)
        path.lineTo(d + r * math.cos(a), r * math.sin(a))
    path.lineTo(-d, r)
    for i in range(1, steps):
        a = math.radians(90.0 + 180.0 * i / steps)
        path.lineTo(-d + r * math.cos(a), r * math.sin(a))
    path.closeSubpath()


def slot_outline_path(span: float, cap: float) -> QPainterPath:
    path = QPainterPath()
    add_slot_path(path, span, cap)
    return path


def iter_slot_dxf_primitives(span: float, cap: float) -> list[tuple[str, tuple]]:
    if slot_is_round(span, cap):
        return [("circle", (0.0, 0.0, cap / 2.0))]
    r = cap / 2.0
    d = span / 2.0
    return [
        ("line", (-d, -r, d, -r)),
        ("arc", (d, 0.0, r, -90.0, 90.0)),
        ("line", (d, r, -d, r)),
        ("arc", (-d, 0.0, r, 90.0, 270.0)),
    ]


def slot_straight_edges_world(
    cx: float, cy: float, span: float, cap: float, angle_deg: float,
) -> tuple[tuple[tuple[float, float], tuple[float, float]],
           tuple[tuple[float, float], tuple[float, float]]]:
    """Top and bottom flat segments between semicircular ends (world coords)."""
    d = span / 2.0
    half = cap / 2.0
    top = (
        to_world(cx, cy, angle_deg, -d, -half),
        to_world(cx, cy, angle_deg, d, -half),
    )
    bottom = (
        to_world(cx, cy, angle_deg, -d, half),
        to_world(cx, cy, angle_deg, d, half),
    )
    return top, bottom


def slot_center_axes_world(
    cx: float, cy: float, span: float, cap: float, angle_deg: float,
) -> tuple[
    tuple[tuple[float, float], tuple[float, float]],
    tuple[tuple[float, float], tuple[float, float]],
    tuple[tuple[float, float], tuple[float, float]],
]:
    """Long axis + vertical axes through each semicircle center (world coords)."""
    g = slot_geom(span, cap)
    half_lo = g.long_outer / 2.0
    half_sh = g.cap / 2.0
    o = g.arc_offset
    horiz = (
        to_world(cx, cy, angle_deg, -half_lo, 0.0),
        to_world(cx, cy, angle_deg, half_lo, 0.0),
    )
    vert_left = (
        to_world(cx, cy, angle_deg, -o, -half_sh),
        to_world(cx, cy, angle_deg, -o, half_sh),
    )
    vert_right = (
        to_world(cx, cy, angle_deg, o, -half_sh),
        to_world(cx, cy, angle_deg, o, half_sh),
    )
    return horiz, vert_left, vert_right


def polygon_inscribed_radius(inscribed_diameter: float) -> float:
    return inscribed_diameter / 2.0


def polygon_circumscribed_radius(inscribed_diameter: float, sides: int) -> float:
    r_in = inscribed_diameter / 2.0
    return r_in / math.cos(math.pi / max(3, sides))


def polygon_circumscribed_diameter(inscribed_diameter: float, sides: int) -> float:
    return polygon_circumscribed_radius(inscribed_diameter, sides) * 2.0
