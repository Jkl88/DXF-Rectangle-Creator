from __future__ import annotations

import math


def _angle_deg_from_point(cx: float, cy: float, x: float, y: float) -> float:
    return math.degrees(math.atan2(-(y - cy), x - cx)) % 360.0


def _point_on_arc(cx: float, cy: float, r: float, angle_deg: float) -> tuple[float, float]:
    a = math.radians(angle_deg)
    return cx + r * math.cos(a), cy - r * math.sin(a)


def _arc_mid_angle(start: float, end: float) -> float:
    span = end - start
    while span <= 0:
        span += 360.0
    while span > 360:
        span -= 360.0
    return (start + span / 2) % 360.0


def line_length(entity: dict) -> float:
    return math.hypot(entity["x2"] - entity["x1"], entity["y2"] - entity["y1"])


def arc_points(entity: dict) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    cx, cy, r = entity["cx"], entity["cy"], entity["r"]
    start = _point_on_arc(cx, cy, r, entity["start"])
    end = _point_on_arc(cx, cy, r, entity["end"])
    mid = _point_on_arc(cx, cy, r, _arc_mid_angle(entity["start"], entity["end"]))
    return start, end, mid


def set_line_endpoints(entity: dict, x1: float, y1: float, x2: float, y2: float) -> None:
    entity.update({"x1": x1, "y1": y1, "x2": x2, "y2": y2})


def set_line_start(entity: dict, x1: float, y1: float) -> None:
    entity["x1"], entity["y1"] = x1, y1


def set_line_end(entity: dict, x2: float, y2: float) -> None:
    entity["x2"], entity["y2"] = x2, y2


def set_line_length(entity: dict, length: float) -> None:
    length = max(length, 0.1)
    x1, y1, x2, y2 = entity["x1"], entity["y1"], entity["x2"], entity["y2"]
    dx, dy = x2 - x1, y2 - y1
    span = math.hypot(dx, dy)
    if span < 1e-9:
        entity["x2"], entity["y2"] = x1 + length, y1
        return
    scale = length / span
    entity["x2"] = x1 + dx * scale
    entity["y2"] = y1 + dy * scale


def set_arc_radius(entity: dict, radius: float) -> None:
    entity["r"] = max(radius, 0.1)


def set_arc_center(entity: dict, cx: float, cy: float) -> None:
    entity["cx"], entity["cy"] = cx, cy


def set_arc_start_point(entity: dict, x: float, y: float) -> None:
    cx, cy = entity["cx"], entity["cy"]
    entity["r"] = max(math.hypot(x - cx, y - cy), 0.1)
    entity["start"] = _angle_deg_from_point(cx, cy, x, y)


def set_arc_end_point(entity: dict, x: float, y: float) -> None:
    cx, cy = entity["cx"], entity["cy"]
    entity["r"] = max(math.hypot(x - cx, y - cy), 0.1)
    entity["end"] = _angle_deg_from_point(cx, cy, x, y)


def set_arc_mid_point(entity: dict, x: float, y: float) -> None:
    cx, cy = entity["cx"], entity["cy"]
    entity["r"] = max(math.hypot(x - cx, y - cy), 0.1)
    mid_angle = _angle_deg_from_point(cx, cy, x, y)
    span = entity["end"] - entity["start"]
    while span <= 0:
        span += 360.0
    while span > 360:
        span -= 360.0
    half = span / 2
    entity["start"] = (mid_angle - half) % 360.0
    entity["end"] = (mid_angle + half) % 360.0
