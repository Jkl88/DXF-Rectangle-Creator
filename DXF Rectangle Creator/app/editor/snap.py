from __future__ import annotations

import math

from app.geometry.line_math import LineSeg, segment_closest_point

Guide = tuple  # ('v', x) | ('h', y) | ('p', x, y) | ('seg', x1, y1, x2, y2)

HALF_GRID = 0.5
HALF_GRID_THRESHOLD_MM = 0.15


def _snap_half_coord(v: float) -> tuple[float, bool]:
    nearest = round(v / HALF_GRID) * HALF_GRID
    if abs(v - nearest) <= HALF_GRID_THRESHOLD_MM:
        return nearest, True
    return v, False


def snap_point(
    x: float, y: float,
    snap_points: list[tuple[float, float]],
    view_scale: float,
    threshold_px: float = 12.0,
    *,
    enabled: bool = True,
    half_grid: bool = True,
) -> tuple[float, float, bool, list[Guide]]:
    """Snap to targets and/or lightly to 0.5 mm grid.

    When *enabled* is False (e.g. Alt held), returns the raw position.
    """
    if not enabled:
        return x, y, False, []

    threshold = threshold_px / max(view_scale, 0.01)
    nx, ny = x, y
    snapped = False
    guides: list[Guide] = []

    if snap_points:
        # 1. Hard snap to nearest point
        best = None
        best_dist = threshold
        for sx, sy in snap_points:
            d = math.hypot(x - sx, y - sy)
            if d < best_dist:
                best_dist = d
                best = (sx, sy)
        if best:
            bx, by = best
            guides = [("v", bx), ("h", by), ("p", bx, by)]
            return bx, by, True, guides

        # 2. Axis alignment (vertical / horizontal lines through targets)
        best_v = best_h = threshold
        vx = vy = None
        for sx, sy in snap_points:
            dx = abs(x - sx)
            if dx <= threshold and dx < best_v:
                best_v = dx
                vx = sx
            dy = abs(y - sy)
            if dy <= threshold and dy < best_h:
                best_h = dy
                vy = sy
        if vx is not None:
            nx = vx
            snapped = True
            guides.append(("v", vx))
        if vy is not None:
            ny = vy
            snapped = True
            guides.append(("h", vy))
    else:
        vx = vy = None

    # 3. Light snap to 0.5 mm grid on axes that did not align
    if half_grid:
        if vx is None:
            nx, hx = _snap_half_coord(nx)
            snapped = snapped or hx
        if vy is None:
            ny, hy = _snap_half_coord(ny)
            snapped = snapped or hy

    return nx, ny, snapped, guides


def snap_point_with_lines(
    x: float, y: float,
    snap_points: list[tuple[float, float]],
    line_segments: list[LineSeg],
    view_scale: float,
    threshold_px: float = 12.0,
    *,
    enabled: bool = True,
    half_grid: bool = True,
) -> tuple[float, float, bool, list[Guide]]:
    if not enabled:
        return x, y, False, []

    threshold = threshold_px / max(view_scale, 0.01)
    nx, ny, snapped, guides = snap_point(
        x, y, snap_points, view_scale, threshold_px,
        enabled=True, half_grid=False,
    )
    if snapped and any(g[0] == "p" for g in guides):
        return nx, ny, True, guides

    nx, ny = x, y
    snapped = False
    guides = []
    best_dist = threshold
    best_proj: tuple[float, float, LineSeg] | None = None
    for seg in line_segments:
        infinite = seg.kind == "infinite_line"
        px, py, _, dist = segment_closest_point(
            x, y, seg.x1, seg.y1, seg.x2, seg.y2, infinite=infinite,
        )
        if dist < best_dist:
            best_dist = dist
            best_proj = (px, py, seg)

    if best_proj is not None:
        nx, ny = best_proj[0], best_proj[1]
        snapped = True
        seg = best_proj[2]
        guides.append(("seg", seg.x1, seg.y1, seg.x2, seg.y2))

    if snap_points:
        best_v = best_h = threshold
        vx = vy = None
        for sx, sy in snap_points:
            dx = abs(nx - sx)
            if dx <= threshold and dx < best_v:
                best_v = dx
                vx = sx
            dy = abs(ny - sy)
            if dy <= threshold and dy < best_h:
                best_h = dy
                vy = sy
        if vx is not None:
            nx = vx
            snapped = True
            guides.append(("v", vx))
        if vy is not None:
            ny = vy
            snapped = True
            guides.append(("h", vy))

    if half_grid:
        hx = hy = False
        if not any(g[0] == "v" for g in guides):
            nx, hx = _snap_half_coord(nx)
            snapped = snapped or hx
        if not any(g[0] == "h" for g in guides):
            ny, hy = _snap_half_coord(ny)
            snapped = snapped or hy

    return nx, ny, snapped, guides


def snap_dim_offset(offset: float, other_offsets: list[float], threshold: float = 5.0) -> float:
    for o in other_offsets:
        if abs(offset - o) <= threshold:
            return o
    return offset
