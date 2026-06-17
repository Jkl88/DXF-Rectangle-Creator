from __future__ import annotations

import math

from app.geometry.line_math import (
    LineSeg, parallel_segment, segment_closest_point, segment_midpoint,
    signed_offset_to_line,
)
from app.geometry.shutter import region_bounds
from app.models.base import ContourKind, MeasureAnchor


def _rect_edge_role(x1: float, y1: float, x2: float, y2: float,
                    left: float, top: float, right: float, bottom: float) -> str:
    if abs(x1 - x2) < 1e-6:
        return "left" if abs(x1 - left) < abs(x1 - right) else "right"
    if abs(y1 - y2) < 1e-6:
        return "top" if abs(y1 - top) < abs(y1 - bottom) else "bottom"
    return "top"


def segment_to_source_anchor(seg: LineSeg, pick_x: float, pick_y: float, doc) -> MeasureAnchor:
    if seg.kind == "drawn_rect" and seg.obj_id:
        r = doc.get_drawn_rect(seg.obj_id)
        if r:
            left, top, right, bottom = region_bounds(r.cx, r.cy, r.width, r.height)
            edge = _rect_edge_role(seg.x1, seg.y1, seg.x2, seg.y2, left, top, right, bottom)
            return MeasureAnchor("drawn_rect", seg.obj_id, -1, edge, x=pick_x, y=pick_y)
    if seg.kind == "shutter" and seg.obj_id:
        s = doc.get_shutter(seg.obj_id)
        if s:
            left, top, right, bottom = region_bounds(s.cx, s.cy, s.width, s.height)
            edge = _rect_edge_role(seg.x1, seg.y1, seg.x2, seg.y2, left, top, right, bottom)
            return MeasureAnchor("shutter", seg.obj_id, -1, edge, x=pick_x, y=pick_y)
    if seg.kind == "contour" or (seg.kind == "" and doc.contour_kind == ContourKind.RECT):
        w, h = doc.rect.width, doc.rect.height
        edge = _rect_edge_role(seg.x1, seg.y1, seg.x2, seg.y2, 0, 0, w, h)
        return MeasureAnchor("contour_rect", "", -1, edge, x=pick_x, y=pick_y)
    return MeasureAnchor("line_segment", "", -1, "segment", x=seg.x1, y=seg.y1)


def get_source_segment(line, doc) -> tuple[float, float, float, float]:
    a = line.source_anchor
    if a.kind == "drawn_rect" and a.object_id:
        r = doc.get_drawn_rect(a.object_id)
        if r:
            left, top, right, bottom = region_bounds(r.cx, r.cy, r.width, r.height)
            return _edge_segment(a.role, left, top, right, bottom)
    if a.kind == "shutter" and a.object_id:
        s = doc.get_shutter(a.object_id)
        if s:
            left, top, right, bottom = region_bounds(s.cx, s.cy, s.width, s.height)
            return _edge_segment(a.role, left, top, right, bottom)
    if a.kind == "contour_rect":
        w, h = doc.rect.width, doc.rect.height
        return _edge_segment(a.role, 0, 0, w, h)
    return line.src_x1, line.src_y1, line.src_x2, line.src_y2


def _edge_segment(role: str, left: float, top: float, right: float, bottom: float) -> tuple[float, float, float, float]:
    if role == "left":
        return left, top, left, bottom
    if role == "right":
        return right, top, right, bottom
    if role == "top":
        return left, top, right, top
    if role == "bottom":
        return left, bottom, right, bottom
    return left, top, right, bottom


def infinite_line_geometry(line) -> tuple[float, float, float, float]:
    if abs(line.inf_x2 - line.inf_x1) > 1e-9 or abs(line.inf_y2 - line.inf_y1) > 1e-9:
        return line.inf_x1, line.inf_y1, line.inf_x2, line.inf_y2
    return parallel_segment(line.src_x1, line.src_y1, line.src_x2, line.src_y2, line.offset)


def init_infinite_geometry(line, src_x1: float, src_y1: float, src_x2: float, src_y2: float, offset: float) -> None:
    line.src_x1, line.src_y1 = src_x1, src_y1
    line.src_x2, line.src_y2 = src_x2, src_y2
    line.offset = offset
    ix1, iy1, ix2, iy2 = parallel_segment(src_x1, src_y1, src_x2, src_y2, offset)
    line.inf_x1, line.inf_y1, line.inf_x2, line.inf_y2 = ix1, iy1, ix2, iy2


def sync_infinite_line_offset(line, doc) -> None:
    src = get_source_segment(line, doc)
    mx, my = segment_midpoint(*infinite_line_geometry(line))
    line.offset = signed_offset_to_line(mx, my, src[0], src[1], src[2], src[3])


def dimension_points(line, doc) -> tuple[tuple[float, float], tuple[float, float], float]:
    src = get_source_segment(line, doc)
    ix1, iy1, ix2, iy2 = infinite_line_geometry(line)
    smx, smy = segment_midpoint(src[0], src[1], src[2], src[3])
    px, py, _, _ = segment_closest_point(smx, smy, ix1, iy1, ix2, iy2, infinite=True)
    pt1x, pt1y, _, _ = segment_closest_point(px, py, src[0], src[1], src[2], src[3])
    dist = math.hypot(px - pt1x, py - pt1y)
    return (pt1x, pt1y), (px, py), dist


def move_infinite_line_by(line, dx: float, dy: float) -> None:
    line.inf_x1 += dx
    line.inf_y1 += dy
    line.inf_x2 += dx
    line.inf_y2 += dy


def set_infinite_line_distance(line, doc, value: float) -> None:
    value = max(0.001, abs(value))
    src = get_source_segment(line, doc)
    sign = 1.0 if line.offset >= 0 else -1.0
    if abs(line.offset) < 1e-9:
        smx, smy = segment_midpoint(*infinite_line_geometry(line))
        sign = 1.0 if signed_offset_to_line(smx, smy, *src) >= 0 else -1.0
    ix1, iy1, ix2, iy2 = parallel_segment(src[0], src[1], src[2], src[3], sign * value)
    line.inf_x1, line.inf_y1, line.inf_x2, line.inf_y2 = ix1, iy1, ix2, iy2
    line.offset = sign * value


def _move_source_anchor_by(anchor: MeasureAnchor, doc, dx: float, dy: float, line_id: str) -> None:
    from app.geometry.measure_bind import is_contour_anchor

    if anchor.kind == "drawn_rect" and anchor.object_id:
        r = doc.get_drawn_rect(anchor.object_id)
        if r:
            doc.move_drawn_rect(anchor.object_id, r.cx + dx, r.cy + dy)
        return
    if anchor.kind == "shutter" and anchor.object_id:
        s = doc.get_shutter(anchor.object_id)
        if s:
            doc.move_shutter(anchor.object_id, s.cx + dx, s.cy + dy)
        return
    if anchor.kind == "hole" and anchor.object_id:
        hole = doc.get_hole(anchor.object_id)
        if hole:
            doc.move_primary_hole(anchor.object_id, hole.cx + dx, hole.cy + dy)
        return
    if is_contour_anchor(anchor) or anchor.kind == "line_segment":
        doc.shift_geometry_except_infinite_line(line_id, dx, dy)


def set_infinite_line_distance_locked(line, doc, value: float) -> None:
    """Locked aux line stays fixed; move the bound source object instead."""
    value = max(0.001, abs(value))
    sync_infinite_line_offset(line, doc)
    current = abs(line.offset)
    delta = value - current
    if abs(delta) < 1e-12:
        return
    src = get_source_segment(line, doc)
    smx, smy = segment_midpoint(src[0], src[1], src[2], src[3])
    ix1, iy1, ix2, iy2 = infinite_line_geometry(line)
    px, py, _, _ = segment_closest_point(smx, smy, ix1, iy1, ix2, iy2, infinite=True)
    to_src_x, to_src_y = smx - px, smy - py
    ln = math.hypot(to_src_x, to_src_y)
    if ln < 1e-9:
        dx, dy = src[2] - src[0], src[3] - src[1]
        seg_ln = math.hypot(dx, dy)
        if seg_ln < 1e-9:
            return
        nx, ny = -dy / seg_ln, dx / seg_ln
        sign = 1.0 if line.offset >= 0 else -1.0
        to_src_x, to_src_y = nx * sign, ny * sign
        ln = 1.0
    ux, uy = to_src_x / ln, to_src_y / ln
    _move_source_anchor_by(line.source_anchor, doc, ux * delta, uy * delta, line.id)
    sync_infinite_line_offset(line, doc)
