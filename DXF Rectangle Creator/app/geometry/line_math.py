from __future__ import annotations

import math
from dataclasses import dataclass

from app.models.base import ContourKind, HoleKind


@dataclass
class LineSeg:
    x1: float
    y1: float
    x2: float
    y2: float
    kind: str = ""
    obj_id: str = ""


def segment_length(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x2 - x1, y2 - y1)


def segment_midpoint(x1: float, y1: float, x2: float, y2: float) -> tuple[float, float]:
    return (x1 + x2) / 2, (y1 + y2) / 2


def segment_closest_point(
    x: float, y: float, x1: float, y1: float, x2: float, y2: float, *,
    infinite: bool = False,
) -> tuple[float, float, float, float]:
    """Return (px, py, t, distance). t is param along segment."""
    dx, dy = x2 - x1, y2 - y1
    ln2 = dx * dx + dy * dy
    if ln2 < 1e-12:
        return x1, y1, 0.0, math.hypot(x - x1, y - y1)
    t = ((x - x1) * dx + (y - y1) * dy) / ln2
    if not infinite:
        t = max(0.0, min(1.0, t))
    px, py = x1 + t * dx, y1 + t * dy
    return px, py, t, math.hypot(x - px, y - py)


def signed_offset_to_line(x: float, y: float, x1: float, y1: float, x2: float, y2: float) -> float:
    dx, dy = x2 - x1, y2 - y1
    ln = math.hypot(dx, dy)
    if ln < 1e-12:
        return 0.0
    nx, ny = -dy / ln, dx / ln
    return (x - x1) * nx + (y - y1) * ny


def parallel_segment(
    x1: float, y1: float, x2: float, y2: float, offset: float,
) -> tuple[float, float, float, float]:
    dx, dy = x2 - x1, y2 - y1
    ln = math.hypot(dx, dy)
    if ln < 1e-12:
        return x1, y1, x2, y2
    nx, ny = -dy / ln, dx / ln
    return (
        x1 + nx * offset, y1 + ny * offset,
        x2 + nx * offset, y2 + ny * offset,
    )


def clip_infinite_line(
    x1: float, y1: float, x2: float, y2: float,
    xmin: float, ymin: float, xmax: float, ymax: float,
) -> tuple[float, float, float, float] | None:
    dx, dy = x2 - x1, y2 - y1
    if abs(dx) < 1e-12 and abs(dy) < 1e-12:
        return None
    pts: list[tuple[float, float]] = []
    if abs(dx) > 1e-12:
        for xb in (xmin, xmax):
            t = (xb - x1) / dx
            yb = y1 + t * dy
            if ymin - 1e-6 <= yb <= ymax + 1e-6:
                pts.append((xb, yb))
    if abs(dy) > 1e-12:
        for yb in (ymin, ymax):
            t = (yb - y1) / dy
            xb = x1 + t * dx
            if xmin - 1e-6 <= xb <= xmax + 1e-6:
                pts.append((xb, yb))
    if len(pts) < 2:
        return None
    return pts[0][0], pts[0][1], pts[-1][0], pts[-1][1]


def pick_line_segment(
    x: float, y: float, segments: list[LineSeg], tolerance: float,
) -> LineSeg | None:
    best: LineSeg | None = None
    best_dist = tolerance
    for seg in segments:
        _, _, _, dist = segment_closest_point(x, y, seg.x1, seg.y1, seg.x2, seg.y2)
        if dist < best_dist:
            best_dist = dist
            best = seg
    return best


def collect_line_segments(document) -> list[LineSeg]:
    from app.geometry.shutter import region_bounds

    segs: list[LineSeg] = []
    doc = document

    def add(x1, y1, x2, y2, kind="", obj_id=""):
        if segment_length(x1, y1, x2, y2) > 1e-6:
            segs.append(LineSeg(x1, y1, x2, y2, kind, obj_id))

    if doc.contour_kind == ContourKind.RECT:
        w, h = doc.rect.width, doc.rect.height
        add(0, 0, w, 0, "contour")
        add(w, 0, w, h, "contour")
        add(w, h, 0, h, "contour")
        add(0, h, 0, 0, "contour")
    elif doc.contour_kind == ContourKind.DXF:
        for ent in doc.dxf_contour.entities:
            if ent.get("pick_only"):
                continue
            t = ent["type"]
            if t == "line":
                add(ent["x1"], ent["y1"], ent["x2"], ent["y2"], "dxf")
            elif t == "polyline":
                pts = ent["points"]
                n = len(pts) if not ent.get("closed") else len(pts)
                for i in range(n - 1):
                    add(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], "dxf")
                if ent.get("closed") and len(pts) > 2:
                    add(pts[-1][0], pts[-1][1], pts[0][0], pts[0][1], "dxf")

    for hole in doc.holes:
        for i, rh in enumerate(doc._resolve_single_hole(hole)):
            if not doc.is_instance_visible_in_editor(hole.id, i):
                continue
            if rh.kind == HoleKind.CIRCLE:
                continue
            if rh.kind == HoleKind.RECT:
                hw, hh = rh.width / 2, rh.height / 2
                corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
                rad = math.radians(rh.angle)
                cos_a, sin_a = math.cos(rad), math.sin(rad)
                world = []
                for cx, cy in corners:
                    wx = rh.cx + cx * cos_a - cy * sin_a
                    wy = rh.cy + cx * sin_a + cy * cos_a
                    world.append((wx, wy))
                for j in range(4):
                    x1, y1 = world[j]
                    x2, y2 = world[(j + 1) % 4]
                    add(x1, y1, x2, y2, "hole", hole.id)

    for s in doc.shutters:
        left, top, right, bottom = region_bounds(s.cx, s.cy, s.width, s.height)
        add(left, top, right, top, "shutter", s.id)
        add(right, top, right, bottom, "shutter", s.id)
        add(right, bottom, left, bottom, "shutter", s.id)
        add(left, bottom, left, top, "shutter", s.id)

    for r in doc.drawn_rects:
        left, top, right, bottom = region_bounds(r.cx, r.cy, r.width, r.height)
        add(left, top, right, top, "drawn_rect", r.id)
        add(right, top, right, bottom, "drawn_rect", r.id)
        add(right, bottom, left, bottom, "drawn_rect", r.id)
        add(left, bottom, left, top, "drawn_rect", r.id)

    return segs


def infinite_line_segments(document) -> list[LineSeg]:
    from app.geometry.infinite_line_bind import infinite_line_geometry
    segs: list[LineSeg] = []
    for line in document.infinite_lines:
        x1, y1, x2, y2 = infinite_line_geometry(line)
        segs.append(LineSeg(x1, y1, x2, y2, "infinite_line", line.id))
    return segs
