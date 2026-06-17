from __future__ import annotations

import math
from typing import TYPE_CHECKING

from app.models.base import ArrayKind, ContourKind, HoleKind, MeasureAnchor

if TYPE_CHECKING:
    from app.models.document import Document


def is_contour_anchor(anchor: MeasureAnchor) -> bool:
    return anchor.kind in ("contour_rect", "contour_circle", "contour_dxf")


def is_fixed_anchor(anchor: MeasureAnchor) -> bool:
    """Contour and free-space points stay fixed when editing a measure."""
    return anchor.kind == "free" or is_contour_anchor(anchor)


def anchor_point(anchor: MeasureAnchor, doc: Document) -> tuple[float, float]:
    if anchor.kind == "free":
        return anchor.x, anchor.y
    if anchor.kind == "contour_rect":
        w, h = doc.rect.width, doc.rect.height
        role = anchor.role
        if role == "corner_tl":
            return 0.0, 0.0
        if role == "corner_tr":
            return w, 0.0
        if role == "corner_br":
            return w, h
        if role == "corner_bl":
            return 0.0, h
        if role == "edge_top":
            return w / 2, 0.0
        if role == "edge_bottom":
            return w / 2, h
        if role == "edge_left":
            return 0.0, h / 2
        if role == "edge_right":
            return w, h / 2
        if role == "center":
            return w / 2, h / 2
    if anchor.kind == "contour_circle":
        d = doc.circle.diameter
        cx, cy, r = d / 2, d / 2, d / 2
        if anchor.role == "center":
            return cx, cy
        if anchor.role == "edge_right":
            return cx + r, cy
        if anchor.role == "edge_left":
            return cx - r, cy
        if anchor.role == "edge_top":
            return cx, cy - r
        if anchor.role == "edge_bottom":
            return cx, cy + r
    if anchor.kind == "hole":
        hole = doc.get_hole(anchor.object_id)
        if hole is None:
            return anchor.x, anchor.y
        resolved = doc._resolve_single_hole(hole)
        idx = max(0, anchor.instance_index)
        if idx < len(resolved):
            rh = resolved[idx]
            return rh.cx, rh.cy
    if anchor.kind == "drawn_rect":
        r = doc.get_drawn_rect(anchor.object_id)
        if r is None:
            return anchor.x, anchor.y
        left = r.cx - r.width / 2
        right = r.cx + r.width / 2
        top = r.cy - r.height / 2
        bottom = r.cy + r.height / 2
        role = anchor.role
        if role == "center":
            return r.cx, r.cy
        if role == "corner_tl":
            return left, top
        if role == "corner_tr":
            return right, top
        if role == "corner_br":
            return right, bottom
        if role == "corner_bl":
            return left, bottom
        if role == "edge_top":
            return r.cx, top
        if role == "edge_bottom":
            return r.cx, bottom
        if role == "edge_left":
            return left, r.cy
        if role == "edge_right":
            return right, r.cy
    if anchor.kind == "dxf_circle":
        ents = doc.dxf_contour.entities
        if 0 <= anchor.entity_index < len(ents):
            ent = ents[anchor.entity_index]
            if anchor.role == "center":
                return ent["cx"], ent["cy"]
    if anchor.kind == "dxf_arc":
        ents = doc.dxf_contour.entities
        if 0 <= anchor.entity_index < len(ents):
            ent = ents[anchor.entity_index]
            if anchor.role == "center":
                return ent["cx"], ent["cy"]
    return anchor.x, anchor.y


def _dist(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x2 - x1, y2 - y1)


def enumerate_snap_targets(doc: Document) -> list[tuple[float, float, MeasureAnchor]]:
    targets: list[tuple[float, float, MeasureAnchor]] = []

    if doc.contour_kind == ContourKind.RECT:
        w, h = doc.rect.width, doc.rect.height
        for role, x, y in (
            ("corner_tl", 0, 0), ("corner_tr", w, 0), ("corner_br", w, h), ("corner_bl", 0, h),
            ("edge_top", w / 2, 0), ("edge_bottom", w / 2, h),
            ("edge_left", 0, h / 2), ("edge_right", w, h / 2),
            ("center", w / 2, h / 2),
        ):
            targets.append((x, y, MeasureAnchor("contour_rect", role=role, x=x, y=y)))
    elif doc.contour_kind == ContourKind.CIRCLE:
        d = doc.circle.diameter
        cx, cy, r = d / 2, d / 2, d / 2
        for role, x, y in (
            ("center", cx, cy),
            ("edge_right", cx + r, cy), ("edge_left", cx - r, cy),
            ("edge_top", cx, cy - r), ("edge_bottom", cx, cy + r),
        ):
            targets.append((x, y, MeasureAnchor("contour_circle", role=role, x=x, y=y)))
    elif doc.contour_kind == ContourKind.DXF:
        from app.geometry.dxf_entities import entity_snap_points
        for i, ent in enumerate(doc.dxf_contour.entities):
            if ent["type"] == "circle":
                cx, cy = ent["cx"], ent["cy"]
                targets.append((
                    cx, cy,
                    MeasureAnchor("dxf_circle", role="center", entity_index=i, x=cx, y=cy),
                ))
            elif ent["type"] == "arc":
                cx, cy = ent["cx"], ent["cy"]
                targets.append((
                    cx, cy,
                    MeasureAnchor("dxf_arc", role="center", entity_index=i, x=cx, y=cy),
                ))
        for x, y in entity_snap_points(doc.dxf_contour.entities):
            targets.append((x, y, MeasureAnchor("contour_dxf", x=x, y=y)))

    for hole in doc.holes:
        for i, rh in enumerate(doc._resolve_single_hole(hole)):
            if not doc.is_instance_visible_in_editor(hole.id, i):
                continue
            targets.append((
                rh.cx, rh.cy,
                MeasureAnchor("hole", hole.id, i, "center", x=rh.cx, y=rh.cy),
            ))

    for r in doc.drawn_rects:
        left = r.cx - r.width / 2
        right = r.cx + r.width / 2
        top = r.cy - r.height / 2
        bottom = r.cy + r.height / 2
        for role, x, y in (
            ("center", r.cx, r.cy),
            ("corner_tl", left, top), ("corner_tr", right, top),
            ("corner_br", right, bottom), ("corner_bl", left, bottom),
            ("edge_top", r.cx, top), ("edge_bottom", r.cx, bottom),
            ("edge_left", left, r.cy), ("edge_right", right, r.cy),
        ):
            targets.append((
                x, y,
                MeasureAnchor("drawn_rect", r.id, -1, role, x=x, y=y),
            ))

    return targets


def resolve_measure_anchor(
    doc: Document, x: float, y: float, tolerance: float,
) -> MeasureAnchor:
    best: MeasureAnchor | None = None
    best_dist = tolerance
    for tx, ty, anchor in enumerate_snap_targets(doc):
        d = _dist(x, y, tx, ty)
        if d < best_dist:
            best_dist = d
            best = anchor
    if best is not None:
        return MeasureAnchor(
            best.kind, best.object_id, best.instance_index, best.role,
            best.entity_index, x, y,
        )
    return MeasureAnchor("free", x=x, y=y)


def resolve_circle_measure_anchor(
    doc: Document, cx: float, cy: float, kind: str, size: float, tolerance: float,
) -> MeasureAnchor:
    tol = max(tolerance, 2.0)
    for hole in doc.holes:
        for i, rh in enumerate(doc._resolve_single_hole(hole)):
            if rh.kind != HoleKind.CIRCLE:
                continue
            if _dist(cx, cy, rh.cx, rh.cy) <= tol:
                return MeasureAnchor(
                    "hole_circle", hole.id, i, kind,
                    x=rh.cx, y=rh.cy,
                )
    if doc.contour_kind == ContourKind.CIRCLE:
        d = doc.circle.diameter
        ccx, ccy = d / 2, d / 2
        if _dist(cx, cy, ccx, ccy) <= tol:
            return MeasureAnchor("contour_circle", role=kind, x=ccx, y=ccy)
    elif doc.contour_kind == ContourKind.DXF:
        for i, ent in enumerate(doc.dxf_contour.entities):
            if ent["type"] == "circle":
                if _dist(cx, cy, ent["cx"], ent["cy"]) <= tol:
                    return MeasureAnchor(
                        "dxf_circle", role=kind, entity_index=i,
                        x=ent["cx"], y=ent["cy"],
                    )
            elif ent["type"] == "arc" and kind == "radius":
                if _dist(cx, cy, ent["cx"], ent["cy"]) <= tol:
                    return MeasureAnchor(
                        "dxf_arc", role=kind, entity_index=i,
                        x=ent["cx"], y=ent["cy"],
                    )
    return MeasureAnchor("free", role=kind, x=cx, y=cy)


def move_anchor_to(anchor: MeasureAnchor, x: float, y: float, doc: Document) -> None:
    if is_fixed_anchor(anchor):
        return
    cur_x, cur_y = anchor_point(anchor, doc)
    dx, dy = x - cur_x, y - cur_y
    if abs(dx) < 1e-12 and abs(dy) < 1e-12:
        return
    if anchor.kind == "hole":
        if anchor.instance_index <= 0:
            hole = doc.get_hole(anchor.object_id)
            if hole:
                doc.move_primary_hole(anchor.object_id, hole.cx + dx, hole.cy + dy)
        else:
            found = doc.find_array_for_instance(anchor.object_id, anchor.instance_index)
            if found:
                arr, local_idx = found
                if arr.kind == ArrayKind.GRID:
                    doc.move_grid_instance(anchor.object_id, arr, local_idx, x, y)
                elif arr.kind == ArrayKind.MIRROR:
                    doc.move_mirror_instance(anchor.object_id, anchor.instance_index, x, y)
        return
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


def apply_circle_size(anchor: MeasureAnchor, value: float, doc: Document) -> None:
    value = max(0.1, value)
    if anchor.kind == "hole_circle":
        hole = doc.get_hole(anchor.object_id)
        if hole is None:
            return
        if anchor.role == "diameter":
            hole.diameter = value
        elif anchor.role == "radius":
            hole.diameter = value * 2
        doc._after_hole_geometry_change(hole.id)
    elif anchor.kind == "contour_circle":
        if anchor.role == "diameter":
            doc.circle.diameter = max(1.0, value)
            doc.update_auto_name()
    elif anchor.kind == "dxf_circle" and anchor.role == "diameter":
        ents = doc.dxf_contour.entities
        if 0 <= anchor.entity_index < len(ents):
            ents[anchor.entity_index]["r"] = max(0.1, value / 2)
    elif anchor.kind == "dxf_arc" and anchor.role == "radius":
        ents = doc.dxf_contour.entities
        if 0 <= anchor.entity_index < len(ents):
            ents[anchor.entity_index]["r"] = max(0.1, value)


def sync_measure_points(doc: Document, m) -> None:
    if m.kind in ("diameter", "radius"):
        ax, ay = anchor_point(m.anchor1, doc)
        m.p1x, m.p1y = ax, ay
        sz = _circle_size(m.anchor1, doc)
        if sz is not None:
            if m.kind == "diameter":
                m.size = sz
            elif m.anchor1.kind == "dxf_arc":
                m.size = sz
            else:
                m.size = sz / 2
        return
    x1, y1 = anchor_point(m.anchor1, doc)
    x2, y2 = anchor_point(m.anchor2, doc)
    m.p1x, m.p1y, m.p2x, m.p2y = x1, y1, x2, y2


def _circle_size(anchor: MeasureAnchor, doc: Document) -> float | None:
    if anchor.kind == "hole_circle":
        hole = doc.get_hole(anchor.object_id)
        if hole:
            return hole.diameter
    if anchor.kind == "contour_circle":
        return doc.circle.diameter
    if anchor.kind == "dxf_circle":
        ents = doc.dxf_contour.entities
        if 0 <= anchor.entity_index < len(ents):
            return ents[anchor.entity_index]["r"] * 2
    if anchor.kind == "dxf_arc":
        ents = doc.dxf_contour.entities
        if 0 <= anchor.entity_index < len(ents):
            return ents[anchor.entity_index]["r"]
    return None


def _measure_edit_ref_and_movable(
    anchor1: MeasureAnchor, anchor2: MeasureAnchor,
) -> tuple[MeasureAnchor | None, MeasureAnchor | None]:
    f1, f2 = is_fixed_anchor(anchor1), is_fixed_anchor(anchor2)
    if f1 and f2:
        return None, None
    if f1:
        return anchor1, anchor2
    if f2:
        return anchor2, anchor1
    return anchor1, anchor2


def apply_measure_horizontal(doc: Document, measure_id: str, value: float) -> bool:
    m = doc.get_measure(measure_id)
    if m is None or m.kind != "linear":
        return False
    ref, movable = _measure_edit_ref_and_movable(m.anchor1, m.anchor2)
    if ref is None or movable is None:
        return False
    value = max(0.0, value)
    ref_pt = anchor_point(ref, doc)
    mov_pt = anchor_point(movable, doc)
    sign = 1.0 if mov_pt[0] >= ref_pt[0] else -1.0
    move_anchor_to(movable, ref_pt[0] + sign * value, mov_pt[1], doc)
    sync_measure_points(doc, m)
    return True


def apply_measure_vertical(doc: Document, measure_id: str, value: float) -> bool:
    m = doc.get_measure(measure_id)
    if m is None or m.kind != "linear":
        return False
    ref, movable = _measure_edit_ref_and_movable(m.anchor1, m.anchor2)
    if ref is None or movable is None:
        return False
    value = max(0.0, value)
    ref_pt = anchor_point(ref, doc)
    mov_pt = anchor_point(movable, doc)
    sign = 1.0 if mov_pt[1] >= ref_pt[1] else -1.0
    move_anchor_to(movable, mov_pt[0], ref_pt[1] + sign * value, doc)
    sync_measure_points(doc, m)
    return True


def apply_measure_distance(doc: Document, measure_id: str, value: float) -> bool:
    m = doc.get_measure(measure_id)
    if m is None or m.kind != "linear":
        return False
    ref, movable = _measure_edit_ref_and_movable(m.anchor1, m.anchor2)
    if ref is None or movable is None:
        return False
    value = max(0.0, value)
    ref_pt = anchor_point(ref, doc)
    mov_pt = anchor_point(movable, doc)
    dx, dy = mov_pt[0] - ref_pt[0], mov_pt[1] - ref_pt[1]
    ln = math.hypot(dx, dy)
    if ln < 1e-9:
        return apply_measure_horizontal(doc, measure_id, value)
    ux, uy = dx / ln, dy / ln
    move_anchor_to(movable, ref_pt[0] + ux * value, ref_pt[1] + uy * value, doc)
    sync_measure_points(doc, m)
    return True
