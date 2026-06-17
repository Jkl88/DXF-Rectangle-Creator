from __future__ import annotations

from app.geometry.shutter import region_bounds


EDGE_HIT_PX = 8.0


def hit_region_edge(
    scene_x: float, scene_y: float,
    cx: float, cy: float, width: float, height: float,
    view_scale: float,
) -> str | None:
    left, top, right, bottom = region_bounds(cx, cy, width, height)
    tol = max(4.0, EDGE_HIT_PX / max(view_scale, 0.01))
    if scene_x < left - tol or scene_x > right + tol or scene_y < top - tol or scene_y > bottom + tol:
        return None
    d_left = abs(scene_x - left)
    d_right = abs(scene_x - right)
    d_top = abs(scene_y - top)
    d_bottom = abs(scene_y - bottom)
    min_d = min(d_left, d_right, d_top, d_bottom)
    if min_d > tol:
        return None
    if min_d == d_left:
        return "left"
    if min_d == d_right:
        return "right"
    if min_d == d_top:
        return "top"
    return "bottom"


def edge_coord(edge: str, left: float, right: float, top: float, bottom: float) -> float:
    if edge == "left":
        return left
    if edge == "right":
        return right
    if edge == "top":
        return top
    return bottom


def apply_edge_position(
    edge: str, cx: float, cy: float, width: float, height: float, value: float,
) -> tuple[float, float, float, float]:
    left, top, right, bottom = region_bounds(cx, cy, width, height)
    if edge == "left":
        left = value
    elif edge == "right":
        right = value
    elif edge == "top":
        top = value
    else:
        bottom = value
    if right < left:
        left, right = right, left
    if bottom < top:
        top, bottom = bottom, top
    w = max(1.0, right - left)
    h = max(1.0, bottom - top)
    return (left + right) / 2, (top + bottom) / 2, w, h
