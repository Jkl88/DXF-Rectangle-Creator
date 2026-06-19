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


def _line_dict(entity) -> dict:
    s = entity.dxf.start
    e = entity.dxf.end
    return {
        "type": "line",
        "x1": float(s.x), "y1": float(-s.y),
        "x2": float(e.x), "y2": float(-e.y),
    }


def _arc_dict(entity) -> dict:
    cx, cy = _wcs_center_xy(entity)
    return {
        "type": "arc",
        "cx": cx,
        "cy": cy,
        "r": float(entity.dxf.radius),
        "start": float(entity.dxf.start_angle),
        "end": float(entity.dxf.end_angle),
    }


def _arc_pick_dict(entity) -> dict:
    return {**_arc_dict(entity), "pick_only": True}


def _polyline_dict_from_points(
    points: list[tuple[float, float]], bulges: list[float], closed: bool,
) -> dict | None:
    if len(points) < 2:
        return None
    return {
        "type": "polyline",
        "points": points,
        "closed": closed,
        "bulges": bulges,
    }


def _lwpolyline_dict(entity) -> dict | None:
    try:
        points: list[tuple[float, float]] = []
        bulges: list[float] = []
        for x, y, bulge in entity.get_points(format="xyb"):
            points.append((float(x), float(-y)))
            bulges.append(float(bulge))
        return _polyline_dict_from_points(points, bulges, bool(entity.closed))
    except Exception:
        return None


def _polyline_dict(entity) -> dict | None:
    try:
        points: list[tuple[float, float]] = []
        bulges: list[float] = []
        for vertex in entity.vertices:
            loc = vertex.dxf.location
            points.append((float(loc.x), float(-loc.y)))
            bulges.append(float(getattr(vertex.dxf, "bulge", 0.0) or 0.0))
        closed = bool(entity.is_closed)
        return _polyline_dict_from_points(points, bulges, closed)
    except Exception:
        return None


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
    if t == "LINE":
        try:
            return [_line_dict(entity)]
        except Exception:
            return []
    if t == "ARC":
        try:
            return [_arc_dict(entity)]
        except Exception:
            return _paths_to_polylines(entity)
    if t == "LWPOLYLINE":
        pl = _lwpolyline_dict(entity)
        if pl is not None:
            return [pl]
        return _paths_to_polylines(entity)
    if t == "POLYLINE":
        pl = _polyline_dict(entity)
        if pl is not None:
            return [pl]
        return _paths_to_polylines(entity)
    if t in _PATH_TYPES:
        return _paths_to_polylines(entity)
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


_ENTITY_LABELS = {
    "line": "Линия",
    "arc": "Дуга",
    "circle": "Окружность",
    "polyline": "Полилиния",
}


def entity_type_label(entity: dict) -> str:
    return _ENTITY_LABELS.get(entity.get("type", ""), "Элемент")


def entity_display_name(entity: dict, index: int) -> str:
    return f"{entity_type_label(entity)} {index}"


def entity_center(entity: dict) -> tuple[float, float]:
    xmin, ymin, w, h = entities_bbox([entity])
    return xmin + w / 2, ymin + h / 2


def _qt_angle_deg(cx: float, cy: float, x: float, y: float) -> float:
    return math.degrees(math.atan2(-(y - cy), x - cx)) % 360.0


def _bulge_segment_to_arc(x1: float, y1: float, x2: float, y2: float, bulge: float) -> dict:
    dx, dy = x2 - x1, y2 - y1
    chord = math.hypot(dx, dy)
    sagitta = abs(bulge) * chord / 2
    radius = (chord ** 2 / 4 + sagitta ** 2) / (2 * sagitta)
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    nx, ny = -dy / chord, dx / chord
    center_dist = math.sqrt(max(radius ** 2 - (chord / 2) ** 2, 0))
    sign = 1 if bulge > 0 else -1
    cx, cy = mx + nx * center_dist * sign, my + ny * center_dist * sign
    start = _qt_angle_deg(cx, cy, x1, y1)
    end = _qt_angle_deg(cx, cy, x2, y2)
    if bulge > 0:
        if end <= start:
            end += 360.0
    elif end >= start:
        end -= 360.0
    return {
        "type": "arc",
        "cx": cx,
        "cy": cy,
        "r": radius,
        "start": start,
        "end": end,
    }


def explode_polyline(entity: dict) -> list[dict]:
    """Split polyline into separate line and arc entities."""
    pts = entity.get("points") or []
    if len(pts) < 2:
        return []
    bulges = entity.get("bulges") or [0.0] * len(pts)
    closed = bool(entity.get("closed"))
    seg_count = len(pts) if closed else len(pts) - 1
    pieces: list[dict] = []
    for i in range(seg_count):
        j = (i + 1) % len(pts)
        x1, y1 = pts[i]
        x2, y2 = pts[j]
        bulge = bulges[i] if i < len(bulges) else 0.0
        if math.hypot(x2 - x1, y2 - y1) < 1e-9:
            continue
        if abs(bulge) < 1e-9:
            pieces.append({"type": "line", "x1": x1, "y1": y1, "x2": x2, "y2": y2})
        else:
            pieces.append(_bulge_segment_to_arc(x1, y1, x2, y2, bulge))
    return pieces


def explode_entity_into_pieces(entity: dict) -> list[dict]:
    """Break compound entity into primitive lines, arcs, circles."""
    t = entity.get("type")
    if t == "polyline":
        return explode_polyline(entity)
    return [entity]


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


def entity_path_for_hit(ent: dict):
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QPainterPath

    path = QPainterPath()
    t = ent["type"]
    if t == "line":
        path.moveTo(ent["x1"], ent["y1"])
        path.lineTo(ent["x2"], ent["y2"])
        return path
    if t == "circle":
        r = ent["r"]
        path.addEllipse(ent["cx"] - r, ent["cy"] - r, 2 * r, 2 * r)
        return path
    if t == "arc":
        r = ent["r"]
        rect = QRectF(ent["cx"] - r, ent["cy"] - r, 2 * r, 2 * r)
        span = ent["end"] - ent["start"]
        while span <= -360:
            span += 360
        while span > 360:
            span -= 360
        path.arcMoveTo(rect, ent["start"])
        path.arcTo(rect, ent["start"], span)
        return path
    if t == "polyline":
        pts = ent["points"]
        bulges = ent.get("bulges") or []
        if not pts:
            return path
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
        return path
    return path


def hit_test_entity(ent: dict, x: float, y: float, tolerance: float) -> bool:
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QPainterPathStroker

    path = entity_path_for_hit(ent)
    if path.isEmpty():
        return False
    stroker = QPainterPathStroker()
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
    stroker.setWidth(max(tolerance * 2, 2.0))
    return stroker.createStroke(path).contains(QPointF(x, y))


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


def _msp_add_polyline(msp, ent: dict, xy, *, flip_bulge: bool = False) -> None:
    pts = ent["points"]
    bulges = ent.get("bulges") or [0.0] * len(pts)
    has_bulge = len(bulges) == len(pts) and any(abs(b) > 1e-9 for b in bulges)
    if has_bulge:
        formatted = []
        for i, (x, y) in enumerate(pts):
            b = bulges[i] if i < len(bulges) else 0.0
            if flip_bulge:
                b = -b
            wx, wy = xy(x, y)
            formatted.append((wx, wy, 0, 0, b))
        msp.add_lwpolyline(formatted, format="xyseb", close=bool(ent.get("closed")))
        return
    world = [xy(x, y) for x, y in pts]
    if ent.get("closed") and world and world[0] != world[-1]:
        world.append(world[0])
    msp.add_lwpolyline(world, close=bool(ent.get("closed")))


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
            _msp_add_polyline(msp, ent, lambda x, y: (x, y))


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
            _msp_add_polyline(msp, ent, xy, flip_bulge=y_negate)
