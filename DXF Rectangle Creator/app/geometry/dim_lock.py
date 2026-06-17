from __future__ import annotations

from typing import TYPE_CHECKING

from app.models.base import ArrayKind, SelectionKind

if TYPE_CHECKING:
    from app.models.document import Document


def is_annotation_locked(doc: Document, ann_id: str) -> bool:
    if ann_id.startswith("note_"):
        return doc.get_leader_state(ann_id).locked
    return doc.get_dim_state(ann_id).locked


def _matches(
    kind: str, object_id: str, instance_index: int,
    tk: str, toid: str, tidx: int,
) -> bool:
    if kind != tk or object_id != toid:
        return False
    if tidx >= 0 and instance_index >= 0 and tidx != instance_index:
        return False
    return True


def _anchor_targets(anchor) -> list[tuple[str, str, int]]:
    if anchor.kind == "hole" and anchor.object_id:
        return [("hole", anchor.object_id, max(0, anchor.instance_index))]
    if anchor.kind == "drawn_rect" and anchor.object_id:
        return [("drawn_rect", anchor.object_id, -1)]
    if anchor.kind == "shutter" and anchor.object_id:
        return [("shutter", anchor.object_id, -1)]
    return []


def _measure_movable_targets(doc: Document, measure_id: str) -> list[tuple[str, str, int]]:
    from app.geometry.measure_bind import _measure_edit_ref_and_movable

    m = doc.get_measure(measure_id)
    if m is None or m.kind != "linear":
        return []
    _, movable = _measure_edit_ref_and_movable(m.anchor1, m.anchor2)
    if movable is None:
        return []
    return _anchor_targets(movable)


def dim_constrained_targets(doc: Document, dim_id: str) -> list[tuple[str, str, int]]:
    if dim_id in ("w_all", "h_all"):
        return [("contour", "", -1)]
    if dim_id.endswith("_ox") or dim_id.endswith("_oy"):
        return [("hole", dim_id[:-3], 0)]
    if dim_id.endswith("_gh") or dim_id.endswith("_gv"):
        arr = doc.get_array(dim_id[:-3])
        if arr is None:
            return []
        targets: list[tuple[str, str, int]] = [("array", arr.id, -1)]
        hole = doc.get_hole(arr.source_hole_id)
        if hole is not None:
            for i in range(1, len(doc._resolve_single_hole(hole))):
                targets.append(("hole", arr.source_hole_id, i))
        return targets
    if dim_id.endswith("_cx") or dim_id.endswith("_cy"):
        return [("array", dim_id[:-3], -1)]
    if dim_id.endswith("_dist"):
        line = doc.get_infinite_line(dim_id[:-5])
        if line is None:
            return []
        targets = _anchor_targets(line.source_anchor)
        targets.append(("infinite_line", line.id, -1))
        return targets
    if dim_id.endswith("_h") or dim_id.endswith("_v") or dim_id.endswith("_d"):
        mid = dim_id[:-2]
        if doc.get_measure(mid) is not None:
            return _measure_movable_targets(doc, mid)
    if dim_id.endswith("_rw") or dim_id.endswith("_rh"):
        rid = dim_id[:-3]
        if doc.get_drawn_rect(rid) is not None:
            return [("drawn_rect", rid, -1)]
        if doc.get_shutter(rid) is not None:
            return [("shutter", rid, -1)]
    for suffix in ("_left", "_right", "_top", "_bottom"):
        if dim_id.endswith(suffix):
            return [("shutter", dim_id[: -len(suffix)], -1)]
    return []


def leader_constrained_targets(doc: Document, note_id: str) -> list[tuple[str, str, int]]:
    if note_id.endswith("_r"):
        arr_id = note_id[5:-2]
        arr = doc.get_array(arr_id)
        if arr is not None and arr.kind == ArrayKind.CIRCULAR:
            return [("array", arr_id, -1)]
    if note_id.endswith("_a") or note_id.endswith("_s"):
        arr_id = note_id[5:-2]
        arr = doc.get_array(arr_id)
        if arr is not None and arr.kind == ArrayKind.CIRCULAR:
            return [("array", arr_id, -1)]
    if note_id.endswith("_d"):
        mid = note_id[5:-2]
        m = doc.get_measure(mid)
        if m is not None:
            return _anchor_targets(m.anchor1)
        hole_id = mid
        if doc.get_hole(hole_id) is not None:
            return [("hole", hole_id, 0)]
    if note_id == "note_contour_d":
        return [("contour", "", -1)]
    if note_id not in ("note_contour_corner", "note_contour_d") and not note_id.endswith(
        ("_r", "_a", "_s", "_ang", "_d"),
    ):
        hole_id = note_id[len("note_"):]
        if doc.get_hole(hole_id) is not None:
            return [("hole", hole_id, 0)]
    return []


def movement_blocked(
    doc: Document, kind: SelectionKind, object_id: str = "", instance_index: int = -1,
) -> bool:
    sk = kind.value
    for dim_id, st in doc.dim_states.items():
        if not st.locked:
            continue
        for tk, toid, tidx in dim_constrained_targets(doc, dim_id):
            if _matches(sk, object_id, instance_index, tk, toid, tidx):
                return True
    for note_id, st in doc.leader_states.items():
        if not st.locked:
            continue
        for tk, toid, tidx in leader_constrained_targets(doc, note_id):
            if _matches(sk, object_id, instance_index, tk, toid, tidx):
                return True
    return False


def resize_blocked(doc: Document, kind: SelectionKind, object_id: str) -> bool:
    sk = kind.value
    for dim_id, st in doc.dim_states.items():
        if not st.locked:
            continue
        if not (dim_id.endswith("_rw") or dim_id.endswith("_rh")):
            continue
        rid = dim_id[:-3]
        for tk, toid, _ in dim_constrained_targets(doc, dim_id):
            if tk == sk and toid == object_id:
                return True
    return False
