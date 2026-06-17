from __future__ import annotations

import math

_SKIP_TYPES = frozenset({
    "DIMENSION", "TEXT", "MTEXT", "ATTDEF", "ATTRIB", "HATCH",
    "POINT", "LEADER", "MLEADER", "VIEWPORT", "IMAGE", "REGION",
})
_PATH_TYPES = frozenset({
    "LINE", "ARC", "LWPOLYLINE", "POLYLINE", "SPLINE", "ELLIPSE", "SOLID", "3DFACE", "TRACE",
})


def _wcs_center_xy(entity) -> tuple[float, float]:
    from ezdxf.math import OCS, Vec3
    ocs = OCS(entity.dxf.extrusion)
    c = ocs.to_wcs(Vec3(entity.dxf.center))
    return float(c.x), float(-c.y)


def _circle_dict(entity) -> dict:
    cx, cy = _wcs_center_xy(entity)
    return {"type": "circle", "cx": cx, "cy": cy, "r": float(entity.dxf.radius)}


def _arc_pick_dict(entity) -> dict:
    cx, cy = _wcs_center_xy(entity)
    return {
        "type": "arc",
        "cx": cx,
        "cy": cy,
        "r": float(entity.dxf.radius),
        "start": float(entity.dxf.start_angle),
        "end": float(entity.dxf.end_angle),
        "pick_only": True,
    }


def _paths_to_polylines(entity) -> list[dict]:
    """Tessellate entity in WCS; flip Y for Qt editor coords (no entity.transform)."""
    try:
        from ezdxf.path import make_path
        path = make_path(entity)
    except Exception:
        return []
    result: list[dict] = []
    sub_paths = list(path.sub_paths()) if hasattr(path, "sub_paths") else [path]
    for sub in sub_paths:
        try:
            pts = [(float(v.x), float(-v.y)) for v in sub.flattening(0.02)]
        except Exception:
            continue
        if len(pts) < 2:
            continue
        closed = bool(getattr(sub, "is_closed", False))
        if not closed and len(pts) >= 3:
            x0, y0 = pts[0]
            x1, y1 = pts[-1]
            if math.hypot(x0 - x1, y0 - y1) < 0.05:
                closed = True
        result.append({
            "type": "polyline",
            "points": pts,
            "closed": closed,
            "bulges": [0.0] * len(pts),
        })
    return result


def _import_entity(entity) -> list[dict]:
    t = entity.dxftype()
    if t in _SKIP_TYPES:
        return []
    if t == "CIRCLE":
        try:
            return [_circle_dict(entity)]
        except Exception:
            return []
    if t in _PATH_TYPES:
        flat = _paths_to_polylines(entity)
        if not flat:
            return []
        if t == "ARC":
            try:
                return flat + [_arc_pick_dict(entity)]
            except Exception:
                pass
        return flat
    return []


def import_modelspace_entities(msp) -> list[dict]:
    from ezdxf.disassemble import recursive_decompose

    entities: list[dict] = []
    for entity in msp:
        t = entity.dxftype()
        if t in _SKIP_TYPES:
            continue
        if t == "INSERT":
            try:
                for item in recursive_decompose(entity):
                    entities.extend(_import_entity(item))
            except Exception:
                try:
                    for ve in entity.virtual_entities():
                        entities.extend(_import_entity(ve))
                except Exception:
                    pass
            continue
        entities.extend(_import_entity(entity))
    return entities


def entities_bbox(
    entities: list[dict],
    *,
    extra_points: list[tuple[float, float]] | None = None,
) -> tuple[float, float, float, float]:
    pts: list[tuple[float, float]] = list(extra_points or [])
    for ent in entities:
        if ent.get("pick_only"):
            continue
        t = ent["type"]
        if t == "line":
            pts.append((ent["x1"], ent["y1"]))
            pts.append((ent["x2"], ent["y2"]))
        elif t in ("circle", "arc"):
            cx, cy, r = ent["cx"], ent["cy"], ent["r"]
            pts.extend([(cx - r, cy - r), (cx + r, cy + r)])
        elif t == "polyline":
            pts.extend(ent["points"])
    if not pts:
        return 0.0, 0.0, 100.0, 100.0
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    w = max(xmax - xmin, 1.0)
    h = max(ymax - ymin, 1.0)
    return xmin, ymin, w, h


def translate_entities(entities: list[dict], dx: float, dy: float) -> list[dict]:
    if abs(dx) < 1e-12 and abs(dy) < 1e-12:
        return entities
    shifted: list[dict] = []
    for ent in entities:
        t = ent["type"]
        if t == "line":
            shifted.append({
                **ent,
                "x1": ent["x1"] + dx, "y1": ent["y1"] + dy,
                "x2": ent["x2"] + dx, "y2": ent["y2"] + dy,
            })
        elif t in ("circle", "arc"):
            shifted.append({**ent, "cx": ent["cx"] + dx, "cy": ent["cy"] + dy})
        elif t == "polyline":
            shifted.append({
                **ent,
                "points": [(x + dx, y + dy) for x, y in ent["points"]],
            })
        else:
            shifted.append(ent)
    return shifted


def normalize_imported_entities(entities: list[dict]) -> list[dict]:
    """Move geometry to local coords so it fits the editor (ignore DXF world offset)."""
    xmin, ymin, _, _ = entities_bbox(entities)
    return translate_entities(entities, -xmin, -ymin)


def _bulge_arc_points(
    x1: float, y1: float, x2: float, y2: float, bulge: float, steps: int = 16,
) -> list[tuple[float, float]]:
    if abs(bulge) < 1e-9:
        return [(x1, y1), (x2, y2)]
    dx, dy = x2 - x1, y2 - y1
    chord = math.hypot(dx, dy)
    if chord < 1e-9:
        return [(x1, y1)]
    sagitta = abs(bulge) * chord / 2
    radius = (chord ** 2 / 4 + sagitta ** 2) / (2 * sagitta)
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    nx, ny = -dy / chord, dx / chord
    center_dist = math.sqrt(max(radius ** 2 - (chord / 2) ** 2, 0))
    sign = 1 if bulge > 0 else -1
    cx, cy = mx + nx * center_dist * sign, my + ny * center_dist * sign
    a1 = math.atan2(y1 - cy, x1 - cx)
    a2 = math.atan2(y2 - cy, x2 - cx)
    if bulge > 0:
        if a2 <= a1:
            a2 += 2 * math.pi
    else:
        if a2 >= a1:
            a2 -= 2 * math.pi
    pts = []
    for i in range(steps + 1):
        t = i / steps
        a = a1 + (a2 - a1) * t
        pts.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
    return pts


def entity_snap_points(entities: list[dict]) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for ent in entities:
        if ent.get("pick_only"):
            continue
        t = ent["type"]
        if t == "line":
            pts.append((ent["x1"], ent["y1"]))
            pts.append((ent["x2"], ent["y2"]))
        elif t == "circle":
            cx, cy, r = ent["cx"], ent["cy"], ent["r"]
            pts.append((cx, cy))
            pts.extend([
                (cx - r, cy), (cx + r, cy), (cx, cy - r), (cx, cy + r),
            ])
        elif t == "arc":
            cx, cy, r = ent["cx"], ent["cy"], ent["r"]
            pts.append((cx, cy))
            for deg in (ent["start"], ent["end"]):
                a = math.radians(deg)
                pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        elif t == "polyline":
            points = ent["points"]
            bulges = ent.get("bulges") or []
            for x, y in points:
                pts.append((x, y))
            count = len(points) if not ent.get("closed") else len(points)
            for i in range(count - 1):
                x1, y1 = points[i]
                x2, y2 = points[i + 1]
                bulge = bulges[i] if i < len(bulges) else 0.0
                if abs(bulge) > 1e-9:
                    for px, py in _bulge_arc_points(x1, y1, x2, y2, bulge, steps=4)[1:-1]:
                        pts.append((px, py))
            if ent.get("closed") and len(points) > 2:
                x1, y1 = points[-1]
                x2, y2 = points[0]
                bulge = bulges[-1] if bulges else 0.0
                if abs(bulge) > 1e-9:
                    for px, py in _bulge_arc_points(x1, y1, x2, y2, bulge, steps=4)[1:-1]:
                        pts.append((px, py))
    return pts


def paint_entities(painter, entities, pen) -> None:
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtGui import QPainterPath

    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    for ent in entities:
        if ent.get("pick_only"):
            continue
        t = ent["type"]
        if t == "line":
            painter.drawLine(QPointF(ent["x1"], ent["y1"]), QPointF(ent["x2"], ent["y2"]))
        elif t == "circle":
            r = ent["r"]
            painter.drawEllipse(QRectF(ent["cx"] - r, ent["cy"] - r, 2 * r, 2 * r))
        elif t == "arc":
            r = ent["r"]
            rect = QRectF(ent["cx"] - r, ent["cy"] - r, 2 * r, 2 * r)
            span = ent["end"] - ent["start"]
            while span <= -360:
                span += 360
            while span > 360:
                span -= 360
            painter.drawArc(rect, int(ent["start"] * 16), int(span * 16))
        elif t == "polyline":
            pts = ent["points"]
            bulges = ent.get("bulges") or []
            if not pts:
                continue
            path = QPainterPath()
            path.moveTo(pts[0][0], pts[0][1])
            count = len(pts) if not ent.get("closed") else len(pts)
            for i in range(count - 1):
                x1, y1 = pts[i]
                x2, y2 = pts[i + 1]
                bulge = bulges[i] if i < len(bulges) else 0.0
                if abs(bulge) < 1e-9:
                    path.lineTo(x2, y2)
                else:
                    for px, py in _bulge_arc_points(x1, y1, x2, y2, bulge)[1:]:
                        path.lineTo(px, py)
            if ent.get("closed") and len(pts) > 2:
                x1, y1 = pts[-1]
                x2, y2 = pts[0]
                bulge = bulges[-1] if bulges else 0.0
                if abs(bulge) < 1e-9:
                    path.lineTo(x2, y2)
                else:
                    for px, py in _bulge_arc_points(x1, y1, x2, y2, bulge)[1:]:
                        path.lineTo(px, py)
                path.closeSubpath()
            painter.drawPath(path)


def add_entities_to_msp(msp, entities: list[dict]) -> None:
    for ent in entities:
        if ent.get("pick_only"):
            continue
        t = ent["type"]
        if t == "line":
            msp.add_line((ent["x1"], ent["y1"]), (ent["x2"], ent["y2"]))
        elif t == "circle":
            msp.add_circle((ent["cx"], ent["cy"]), ent["r"])
        elif t == "arc":
            msp.add_arc(
                center=(ent["cx"], ent["cy"]),
                radius=ent["r"],
                start_angle=ent["start"],
                end_angle=ent["end"],
            )
        elif t == "polyline":
            pts = [(x, y) for x, y in ent["points"]]
            if ent.get("closed") and pts and pts[0] != pts[-1]:
                pts.append(pts[0])
            msp.add_lwpolyline(pts, close=bool(ent.get("closed")))


def _editor_to_dxf_xy(
    x: float, y: float, *, height: float, y_negate: bool,
) -> tuple[float, float]:
    if y_negate:
        return x, -y
    return x, height - y


def export_entities_to_msp(
    msp, entities: list[dict], *, height: float, y_negate: bool,
) -> None:
    """Write contour entities converting editor Y-down coords to DXF Y-up."""
    xy = lambda x, y: _editor_to_dxf_xy(x, y, height=height, y_negate=y_negate)
    for ent in entities:
        if ent.get("pick_only"):
            continue
        t = ent["type"]
        if t == "line":
            msp.add_line(xy(ent["x1"], ent["y1"]), xy(ent["x2"], ent["y2"]))
        elif t == "circle":
            cx, cy = xy(ent["cx"], ent["cy"])
            msp.add_circle((cx, cy), ent["r"])
        elif t == "arc":
            cx, cy = xy(ent["cx"], ent["cy"])
            msp.add_arc(
                center=(cx, cy),
                radius=ent["r"],
                start_angle=ent["start"],
                end_angle=ent["end"],
            )
        elif t == "polyline":
            pts = [xy(x, y) for x, y in ent["points"]]
            if ent.get("closed") and pts and pts[0] != pts[-1]:
                pts.append(pts[0])
            msp.add_lwpolyline(pts, close=bool(ent.get("closed")))
