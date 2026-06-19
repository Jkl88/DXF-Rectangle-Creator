from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.geometry.slot import slot_arc_centers_world, slot_geom
from app.models.base import (
    ArrayKind,
    CircleContour,
    ContourKind,
    DimensionState,
    DrawnRectangle,
    DxfContour,
    Hole,
    HoleArray,
    HoleKind,
    InfiniteLine,
    InstanceState,
    LeaderState,
    MeasureAnnotation,
    MirrorAxis,
    ObjectDisplayState,
    MeasureAnchor,
    RectContour,
    ResolvedHole,
    Selection,
    SelectionKind,
    ShutterLayoutParams,
    ShutterRegion,
    TitleBlock,
    _clone_hole,
    _transform_point,
)

HOLE_COLORS = [
    "#e03131", "#1971c2", "#2f9e44", "#f08c00",
    "#9c36b5", "#0c8599", "#e64980", "#495057",
]


@dataclass
class Document:
    designation: str = ""
    name: str = ""
    contour_kind: ContourKind = ContourKind.RECT
    rect: RectContour = field(default_factory=RectContour)
    circle: CircleContour = field(default_factory=CircleContour)
    dxf_contour: DxfContour = field(default_factory=DxfContour)
    holes: list[Hole] = field(default_factory=list)
    arrays: list[HoleArray] = field(default_factory=list)
    selection: Selection = field(default_factory=Selection)
    dim_states: dict[str, DimensionState] = field(default_factory=dict)
    object_states: dict[str, ObjectDisplayState] = field(default_factory=dict)
    leader_states: dict[str, LeaderState] = field(default_factory=dict)
    instance_overrides: dict[str, tuple[float, float]] = field(default_factory=dict)
    instance_states: dict[str, InstanceState] = field(default_factory=dict)
    default_font_size: int = 9
    title_block: TitleBlock = field(default_factory=TitleBlock)
    measures: list[MeasureAnnotation] = field(default_factory=list)
    shutters: list[ShutterRegion] = field(default_factory=list)
    shutter_layout: ShutterLayoutParams = field(default_factory=ShutterLayoutParams.defaults)
    infinite_lines: list[InfiniteLine] = field(default_factory=list)
    drawn_rects: list[DrawnRectangle] = field(default_factory=list)
    _listeners: list[Callable[[], None]] = field(default_factory=list, repr=False)

    def subscribe(self, callback: Callable[[], None]) -> None:
        self._listeners.append(callback)

    def notify(self) -> None:
        for cb in self._listeners:
            cb()

    def datum_origin(self) -> tuple[float, float]:
        if self.contour_kind == ContourKind.DXF:
            return self.dxf_contour.origin_x, self.dxf_contour.origin_y
        if self.contour_kind == ContourKind.CIRCLE:
            return self.contour_center()
        return 0.0, 0.0

    def contour_center(self) -> tuple[float, float]:
        if self.contour_kind == ContourKind.CIRCLE:
            r = self.circle.diameter / 2
            return r, r
        x, y, w, h = self.contour_bounds()
        return x + w / 2, y + h / 2

    def contour_bounds(self) -> tuple[float, float, float, float]:
        if self.contour_kind == ContourKind.CIRCLE:
            d = self.circle.diameter
            return 0, 0, d, d
        if self.contour_kind == ContourKind.DXF:
            from app.geometry.dxf_entities import entities_bbox
            extra: list[tuple[float, float]] = []
            if self.dxf_contour.origin_set:
                extra.append((self.dxf_contour.origin_x, self.dxf_contour.origin_y))
            return entities_bbox(self.dxf_contour.entities, extra_points=extra or None)
        return 0, 0, self.rect.width, self.rect.height

    def update_auto_name(self) -> None:
        if self.contour_kind == ContourKind.CIRCLE:
            self.name = f"C_{self.circle.diameter:.1f}"
        elif self.contour_kind == ContourKind.DXF:
            if self.dxf_contour.source_file:
                self.name = os.path.splitext(self.dxf_contour.source_file)[0]
            else:
                _, _, w, h = self.contour_bounds()
                self.name = f"DXF_{w:.1f}x{h:.1f}"
        else:
            self.name = f"R_{self.rect.width:.1f}x{self.rect.height:.1f}"

    def set_origin(self, x: float, y: float) -> None:
        if self.contour_kind != ContourKind.DXF:
            return
        self.dxf_contour.origin_x = x
        self.dxf_contour.origin_y = y

    def shift_all_geometry(self, dx: float, dy: float) -> None:
        if abs(dx) < 1e-12 and abs(dy) < 1e-12:
            return
        for hole in self.holes:
            hole.cx += dx
            hole.cy += dy
        for arr in self.arrays:
            arr.center_x += dx
            arr.center_y += dy
        for m in self.measures:
            m.p1x += dx
            m.p1y += dy
            m.p2x += dx
            m.p2y += dy
        for s in self.shutters:
            s.cx += dx
            s.cy += dy
        for line in self.infinite_lines:
            line.src_x1 += dx
            line.src_y1 += dy
            line.src_x2 += dx
            line.src_y2 += dy
        for r in self.drawn_rects:
            r.cx += dx
            r.cy += dy
        for key, (ox, oy) in list(self.instance_overrides.items()):
            self.instance_overrides[key] = (ox + dx, oy + dy)

    def shift_geometry_except_infinite_line(self, line_id: str, dx: float, dy: float) -> None:
        """Shift document geometry but keep one infinite line's world position fixed."""
        if abs(dx) < 1e-12 and abs(dy) < 1e-12:
            return
        self.shift_all_geometry(dx, dy)
        line = self.get_infinite_line(line_id)
        if line is None:
            return
        line.src_x1 -= dx
        line.src_y1 -= dy
        line.src_x2 -= dx
        line.src_y2 -= dy

    def place_dxf_origin(self, x: float, y: float) -> None:
        if self.contour_kind != ContourKind.DXF:
            return
        from app.geometry.dxf_entities import translate_entities
        self.dxf_contour.entities = translate_entities(self.dxf_contour.entities, -x, -y)
        self.shift_all_geometry(-x, -y)
        self.dxf_contour.origin_x = 0.0
        self.dxf_contour.origin_y = 0.0
        self.dxf_contour.origin_set = True

    def dxf_snap_points(self) -> list[tuple[float, float]]:
        if self.contour_kind != ContourKind.DXF:
            return []
        from app.geometry.dxf_entities import entity_snap_points
        return entity_snap_points(self.dxf_contour.entities)

    def get_hole(self, hole_id: str) -> Optional[Hole]:
        for h in self.holes:
            if h.id == hole_id:
                return h
        return None

    def get_array(self, array_id: str) -> Optional[HoleArray]:
        for a in self.arrays:
            if a.id == array_id:
                return a
        return None

    def next_hole_color(self) -> str:
        return HOLE_COLORS[len(self.holes) % len(HOLE_COLORS)]

    def add_hole(self, hole: Optional[Hole] = None) -> Hole:
        if hole is None:
            hole = Hole(cx=10.0, cy=10.0, diameter=6.0, color=self.next_hole_color())
        if not hole.name:
            hole.name = f"Отверстие {len(self.holes) + 1}"
        self.holes.append(hole)
        self.select(SelectionKind.HOLE, hole.id)
        self.notify()
        return hole

    def arrays_for_hole(self, hole_id: str) -> list[HoleArray]:
        return [a for a in self.arrays if a.source_hole_id == hole_id]

    def add_array_for_hole(self, hole_id: str) -> Optional[HoleArray]:
        hole = self.get_hole(hole_id)
        if hole is None:
            return None
        cx, cy = self.contour_center()
        n = len(self.arrays_for_hole(hole_id)) + 1
        arr = HoleArray(
            source_hole_id=hole_id,
            name=f"Массив {n}",
            center_x=cx,
            center_y=cy,
            radius=math.hypot(hole.cx - cx, hole.cy - cy) or 30.0,
        )
        self.arrays.append(arr)
        self.select(SelectionKind.ARRAY, arr.id)
        self.notify()
        return arr

    def remove_selected(self) -> None:
        sel = self.selection
        if sel.kind == SelectionKind.HOLE and sel.object_id:
            self.arrays = [a for a in self.arrays if a.source_hole_id != sel.object_id]
            prefix = f"{sel.object_id}:"
            self.instance_overrides = {
                k: v for k, v in self.instance_overrides.items() if not k.startswith(prefix)
            }
            self.instance_states = {
                k: v for k, v in self.instance_states.items() if not k.startswith(prefix)
            }
            self.holes = [h for h in self.holes if h.id != sel.object_id]
        elif sel.kind == SelectionKind.ARRAY and sel.object_id:
            self.arrays = [a for a in self.arrays if a.id != sel.object_id]
        elif sel.kind == SelectionKind.MEASURE and sel.object_id:
            mid = sel.object_id
            self.measures = [m for m in self.measures if m.id != mid]
            for did in self.annotation_ids_for_measure(mid):
                if did.startswith("note_"):
                    self.leader_states.pop(did, None)
                else:
                    self.dim_states.pop(did, None)
        elif sel.kind == SelectionKind.SHUTTER and sel.object_id:
            sid = sel.object_id
            self.shutters = [s for s in self.shutters if s.id != sid]
            for did in self.dim_ids_for_shutter(sid):
                self.dim_states.pop(did, None)
        elif sel.kind == SelectionKind.INFINITE_LINE and sel.object_id:
            lid = sel.object_id
            self.infinite_lines = [ln for ln in self.infinite_lines if ln.id != lid]
            for did in self.dim_ids_for_infinite_line(lid):
                self.dim_states.pop(did, None)
        elif sel.kind == SelectionKind.DRAWN_RECT and sel.object_id:
            rid = sel.object_id
            self.drawn_rects = [r for r in self.drawn_rects if r.id != rid]
        self.select(SelectionKind.NONE)
        self.notify()

    def select(self, kind: SelectionKind, object_id: str = "", instance_index: int = -1, notify: bool = True) -> None:
        self.selection = Selection(kind=kind, object_id=object_id, instance_index=instance_index)
        if notify:
            self.notify()

    @staticmethod
    def instance_key(hole_id: str, index: int) -> str:
        return f"{hole_id}:{index}"

    def get_instance_state(self, hole_id: str, index: int) -> InstanceState:
        key = self.instance_key(hole_id, index)
        if key not in self.instance_states:
            self.instance_states[key] = InstanceState(key=key)
        return self.instance_states[key]

    def _instances_added_by_array(self, arr: HoleArray, pattern_size: int) -> int:
        if arr.kind == ArrayKind.GRID:
            cells = max(0, arr.count_x * arr.count_y - 1)
            return pattern_size * cells
        if arr.kind == ArrayKind.MIRROR:
            return pattern_size
        if arr.kind == ArrayKind.CIRCULAR:
            return pattern_size * max(0, arr.count - 1)
        return 0

    def _pattern_size_before_array(self, hole_id: str, array_id: str) -> int:
        size = 1
        for arr in self.arrays_for_hole(hole_id):
            if arr.id == array_id:
                return size
            size += self._instances_added_by_array(arr, size)
        return size

    def _grid_cell_index_to_local(self, arr: HoleArray, cell_i: int) -> int:
        n = 0
        for iy in range(arr.count_y):
            for ix in range(arr.count_x):
                if ix == 0 and iy == 0:
                    continue
                if n == cell_i:
                    return n
                n += 1
        return 0

    def _find_array_for_sub_index(self, hole_id: str, sub: int) -> Optional[tuple[HoleArray, int]]:
        """Map pattern sub-index (1..pattern_size-1) to owning array and local index."""
        if sub <= 0:
            return None
        ps = 1
        for arr in self.arrays_for_hole(hole_id):
            added = self._instances_added_by_array(arr, ps)
            if sub < ps + added:
                local = sub - ps
                if arr.kind == ArrayKind.GRID:
                    cell_i = local // ps
                    inner_sub = local % ps
                    if inner_sub > 0:
                        return self._find_array_for_sub_index(hole_id, inner_sub)
                    return arr, self._grid_cell_index_to_local(arr, cell_i)
                if arr.kind == ArrayKind.MIRROR:
                    inner_sub = local % ps
                    if inner_sub > 0:
                        return self._find_array_for_sub_index(hole_id, inner_sub)
                    return arr, 0
                if arr.kind == ArrayKind.CIRCULAR:
                    inner_sub = local % ps
                    if inner_sub > 0:
                        return self._find_array_for_sub_index(hole_id, inner_sub)
                    return arr, local // ps
            ps += added
        return None

    def find_array_for_instance(self, hole_id: str, index: int) -> Optional[tuple[HoleArray, int]]:
        if index <= 0:
            return None
        ps = 1
        offset = 1
        for arr in self.arrays_for_hole(hole_id):
            added = self._instances_added_by_array(arr, ps)
            if offset <= index < offset + added:
                local = index - offset
                sub = local % ps
                if sub > 0:
                    return self._find_array_for_sub_index(hole_id, sub)
                cell_i = local // ps
                if arr.kind == ArrayKind.GRID:
                    return arr, self._grid_cell_index_to_local(arr, cell_i)
                if arr.kind == ArrayKind.MIRROR:
                    return arr, 0
                if arr.kind == ArrayKind.CIRCULAR:
                    return arr, cell_i
            offset += added
            ps += added
        return None

    def _grid_coords_for_local_index(self, arr: HoleArray, local_index: int) -> tuple[int, int]:
        n = 0
        for iy in range(arr.count_y):
            for ix in range(arr.count_x):
                if ix == 0 and iy == 0:
                    continue
                if n == local_index:
                    return ix, iy
                n += 1
        return 1, 0

    def move_primary_hole(self, hole_id: str, x: float, y: float) -> None:
        if self.is_movement_blocked(SelectionKind.HOLE, hole_id, 0):
            return
        hole = self.get_hole(hole_id)
        if hole is None:
            return
        dx, dy = x - hole.cx, y - hole.cy
        if abs(dx) < 1e-12 and abs(dy) < 1e-12:
            return
        hole.cx, hole.cy = x, y
        self._translate_circular_arrays_for_hole(hole_id, dx, dy)

    def _translate_circular_arrays_for_hole(self, hole_id: str, dx: float, dy: float) -> None:
        circular_arrs = [
            arr for arr in self.arrays_for_hole(hole_id) if arr.kind == ArrayKind.CIRCULAR
        ]
        if not circular_arrs or any(not arr.center_fixed for arr in circular_arrs):
            prefix = f"{hole_id}:"
            for key, (ox, oy) in list(self.instance_overrides.items()):
                if key.startswith(prefix):
                    self.instance_overrides[key] = (ox + dx, oy + dy)
        for arr in circular_arrs:
            if arr.center_fixed:
                self.sync_circular_array_radius(arr)
            else:
                arr.center_x += dx
                arr.center_y += dy

    def move_grid_instance(self, hole_id: str, arr: HoleArray, local_index: int, x: float, y: float) -> None:
        if self.is_movement_blocked(SelectionKind.ARRAY, arr.id):
            return
        hole = self.get_hole(hole_id)
        if hole is None:
            return
        ix, iy = self._grid_coords_for_local_index(arr, local_index)
        dx, dy = x - hole.cx, y - hole.cy
        rad = math.radians(-arr.grid_angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        lx = dx * cos_a - dy * sin_a
        ly = dx * sin_a + dy * cos_a
        if ix != 0:
            arr.step_x = lx / ix
        if iy != 0:
            arr.step_y = ly / iy
        self._clear_hole_instance_overrides(hole_id)

    def _clear_hole_instance_overrides(self, hole_id: str) -> None:
        prefix = f"{hole_id}:"
        self.instance_overrides = {
            k: v for k, v in self.instance_overrides.items() if not k.startswith(prefix)
        }

    @staticmethod
    def grid_array_span_x(arr: HoleArray) -> float:
        if arr.count_x <= 1:
            return 0.0
        return arr.step_x * (arr.count_x - 1)

    @staticmethod
    def grid_array_span_y(arr: HoleArray) -> float:
        if arr.count_y <= 1:
            return 0.0
        return arr.step_y * (arr.count_y - 1)

    def set_grid_array_span_x(self, arr: HoleArray, span: float) -> None:
        if arr is None or arr.count_x <= 1:
            return
        arr.step_x = max(0.0, span) / (arr.count_x - 1)
        self._clear_hole_instance_overrides(arr.source_hole_id)

    def set_grid_array_span_y(self, arr: HoleArray, span: float) -> None:
        if arr is None or arr.count_y <= 1:
            return
        arr.step_y = max(0.0, span) / (arr.count_y - 1)
        self._clear_hole_instance_overrides(arr.source_hole_id)

    def set_grid_array_step_x(self, arr: HoleArray, step: float) -> None:
        if arr is None:
            return
        arr.step_x = step
        self._clear_hole_instance_overrides(arr.source_hole_id)

    def set_grid_array_step_y(self, arr: HoleArray, step: float) -> None:
        if arr is None:
            return
        arr.step_y = step
        self._clear_hole_instance_overrides(arr.source_hole_id)

    def move_mirror_instance(self, hole_id: str, index: int, x: float, y: float) -> None:
        if self.is_movement_blocked(SelectionKind.HOLE, hole_id, index):
            return
        self.instance_overrides[f"{hole_id}:{index}"] = (x, y)

    def is_instance_visible_in_editor(self, hole_id: str, index: int) -> bool:
        if index == 0:
            return True
        if self.get_instance_state(hole_id, index).always_show:
            return True
        sel = self.selection
        if sel.kind == SelectionKind.ARRAY:
            arr = self.get_array(sel.object_id)
            if arr and arr.source_hole_id == hole_id:
                return True
        return False

    def is_instance_exported(self, hole_id: str, index: int) -> bool:
        if index == 0:
            return True
        return self.get_instance_state(hole_id, index).always_show

    def get_dim_state(self, dim_id: str) -> DimensionState:
        if dim_id not in self.dim_states:
            self.dim_states[dim_id] = DimensionState(
                dim_id=dim_id, font_size=self.default_font_size,
            )
        return self.dim_states[dim_id]

    def apply_default_font_size(self, new_size: int) -> None:
        for st in self.dim_states.values():
            if not st.font_size_custom:
                st.font_size = new_size
        for st in self.leader_states.values():
            if not st.font_size_custom:
                st.font_size = new_size

    @staticmethod
    def object_state_key(kind: str, object_id: str = "") -> str:
        return f"{kind}:{object_id}"

    def get_object_state(self, kind: str, object_id: str = "") -> ObjectDisplayState:
        key = self.object_state_key(kind, object_id)
        if key not in self.object_states:
            self.object_states[key] = ObjectDisplayState()
        return self.object_states[key]

    def dim_ids_for_contour(self) -> list[str]:
        if self.contour_kind != ContourKind.RECT:
            return []
        return ["w_all", "h_all"]

    def leader_ids_for_contour(self) -> list[str]:
        ids: list[str] = []
        if self.contour_kind == ContourKind.CIRCLE:
            ids.append("note_contour_d")
        elif self.contour_kind == ContourKind.RECT and self.rect.corner_size > 0:
            ids.append("note_contour_corner")
        return ids

    def dim_ids_for_array(self, array_id: str) -> list[str]:
        arr = self.get_array(array_id)
        if arr is None:
            return []
        ids: list[str] = []
        if arr.kind == ArrayKind.GRID:
            if arr.count_x > 1:
                ids.append(f"{array_id}_gh")
                ids.append(f"{array_id}_glx")
            if arr.count_y > 1:
                ids.append(f"{array_id}_gv")
                ids.append(f"{array_id}_gly")
        elif arr.kind == ArrayKind.CIRCULAR:
            ids.extend([f"{array_id}_cx", f"{array_id}_cy"])
        return ids

    def leader_ids_for_array(self, array_id: str) -> list[str]:
        arr = self.get_array(array_id)
        if arr is None:
            return []
        if arr.kind == ArrayKind.CIRCULAR:
            ids = [f"note_{array_id}_r"]
            if arr.count > 1:
                ids.append(f"note_{array_id}_s")
            angle = self.circular_array_spoke_angle(arr)
            if angle is not None and self.spoke_angle_needs_annotation(angle):
                ids.append(f"note_{array_id}_a")
            return ids
        return []

    @staticmethod
    def circular_spoke_angle_deg(center_x: float, center_y: float,
                                 hole_x: float, hole_y: float) -> float:
        return math.degrees(math.atan2(hole_y - center_y, hole_x - center_x)) % 360.0

    @staticmethod
    def spoke_angle_needs_annotation(angle_deg: float, tol: float = 0.05) -> bool:
        rem = angle_deg % 90.0
        return rem > tol and rem < 90.0 - tol

    def circular_array_spoke_angle(self, arr: HoleArray) -> float | None:
        if arr.kind != ArrayKind.CIRCULAR:
            return None
        hole = self.get_hole(arr.source_hole_id)
        if hole is None:
            return None
        return self.circular_spoke_angle_deg(arr.center_x, arr.center_y, hole.cx, hole.cy)

    def set_circular_array_spoke_angle(self, arr: HoleArray, angle_deg: float) -> None:
        if self.is_movement_blocked(SelectionKind.ARRAY, arr.id):
            return
        hole = self.get_hole(arr.source_hole_id)
        if hole is None:
            return
        self.sync_circular_array_radius(arr)
        rad = math.radians(angle_deg % 360.0)
        hole.cx = arr.center_x + arr.radius * math.cos(rad)
        hole.cy = arr.center_y + arr.radius * math.sin(rad)

    def circular_array_step_angle(self, arr: HoleArray) -> float | None:
        if arr.kind != ArrayKind.CIRCULAR or arr.count < 2:
            return None
        if arr.step_angle > 0:
            return arr.step_angle
        return 360.0 / arr.count

    def set_circular_array_step_angle(self, arr: HoleArray, angle_deg: float) -> None:
        if self.is_movement_blocked(SelectionKind.ARRAY, arr.id):
            return
        if arr.kind != ArrayKind.CIRCULAR:
            return
        arr.step_angle = max(0.0, angle_deg % 360.0)

    def annotation_ids_for_array(self, array_id: str) -> list[str]:
        return self.dim_ids_for_array(array_id) + self.leader_ids_for_array(array_id)

    def annotation_ids_for_contour(self) -> list[str]:
        return self.dim_ids_for_contour() + self.leader_ids_for_contour()

    def annotation_ids_for_hole(self, hole_id: str) -> list[str]:
        ids = self.dim_ids_for_hole(hole_id)
        hole = self.get_hole(hole_id)
        if hole is None:
            return ids
        if hole.kind in (HoleKind.RECT, HoleKind.OVAL):
            ids.append(f"note_{hole_id}")
        if hole.kind in (HoleKind.CIRCLE, HoleKind.POLYGON):
            ids.append(f"note_{hole_id}_d")
        if hole.kind != HoleKind.CIRCLE and self.spoke_angle_needs_annotation(hole.angle % 360.0):
            ids.append(f"note_{hole_id}_ang")
        return ids

    def _set_annotation_always_show(self, ann_id: str, value: bool) -> None:
        if ann_id.startswith("note_"):
            self.get_leader_state(ann_id).always_show = value
        else:
            self.get_dim_state(ann_id).always_show = value

    def set_object_show_dims(self, kind: str, object_id: str, value: bool) -> None:
        self.get_object_state(kind, object_id).show_dims = value
        if kind == "contour":
            ann_ids = self.annotation_ids_for_contour()
        elif kind == "hole":
            ann_ids = self.annotation_ids_for_hole(object_id)
        elif kind == "array":
            ann_ids = self.annotation_ids_for_array(object_id)
        elif kind == "measure":
            ann_ids = self.annotation_ids_for_measure(object_id)
        elif kind == "shutter":
            ann_ids = self.dim_ids_for_shutter(object_id)
        elif kind == "drawn_rect":
            ann_ids = self.dim_ids_for_drawn_rect(object_id)
        else:
            return
        for ann_id in ann_ids:
            self._set_annotation_always_show(ann_id, value and not self.is_zero_dimension(ann_id))
        self.notify()

    def toggle_object_show_dims(self, kind: str, object_id: str = "") -> None:
        st = self.get_object_state(kind, object_id)
        self.set_object_show_dims(kind, object_id, not st.show_dims)

    def is_annotation_locked(self, ann_id: str) -> bool:
        from app.geometry.dim_lock import is_annotation_locked
        return is_annotation_locked(self, ann_id)

    def is_movement_blocked(
        self, kind: SelectionKind, object_id: str = "", instance_index: int = -1,
    ) -> bool:
        from app.geometry.dim_lock import movement_blocked
        return movement_blocked(self, kind, object_id, instance_index)

    def is_resize_blocked(self, kind: SelectionKind, object_id: str) -> bool:
        from app.geometry.dim_lock import resize_blocked
        return resize_blocked(self, kind, object_id)

    def hole_display_diameter(self, hole: Hole) -> float:
        if hole.kind in (HoleKind.CIRCLE, HoleKind.POLYGON):
            return hole.diameter
        return 0.0

    def dim_ids_for_hole(self, hole_id: str) -> list[str]:
        ids = [f"{hole_id}_ox", f"{hole_id}_oy"]
        for arr in self.arrays_for_hole(hole_id):
            ids.extend(self.annotation_ids_for_array(arr.id))
        return ids

    def get_dimension_value(self, dim_id: str) -> float | None:
        """Return the measured distance for an editable dimension, or None."""
        if dim_id.endswith("_ang"):
            hole = self.get_hole(dim_id[5:-4])
            if hole is not None:
                return hole.angle % 360.0
            return None
        if dim_id.startswith("note_") and dim_id.endswith("_r"):
            mid = dim_id[5:-2]
            m = self.get_measure(mid)
            if m is not None and m.kind == "radius":
                return m.size
            arr = self.get_array(mid)
            if arr and arr.kind == ArrayKind.CIRCULAR:
                return arr.radius
            return None
        if dim_id.startswith("note_") and dim_id.endswith("_a"):
            arr = self.get_array(dim_id[5:-2])
            if arr and arr.kind == ArrayKind.CIRCULAR:
                return self.circular_array_spoke_angle(arr)
            return None
        if dim_id.startswith("note_") and dim_id.endswith("_s"):
            arr = self.get_array(dim_id[5:-2])
            if arr and arr.kind == ArrayKind.CIRCULAR:
                return self.circular_array_step_angle(arr)
            return None
        if dim_id.startswith("note_") and dim_id.endswith("_d"):
            mid = dim_id[5:-2]
            m = self.get_measure(mid)
            if m is not None and m.kind == "diameter":
                return m.size
            hole = self.get_hole(mid)
            if hole is not None:
                return self.hole_display_diameter(hole)
            return None
        if dim_id == "note_contour_d":
            if self.contour_kind == ContourKind.CIRCLE:
                return self.circle.diameter
            return None
        if dim_id.startswith("note_") and dim_id not in (
            "note_contour_corner", "note_contour_d",
        ) and not dim_id.endswith(("_r", "_a", "_s", "_ang", "_d")):
            hole = self.get_hole(dim_id[5:])
            if hole is not None and hole.kind in (HoleKind.RECT, HoleKind.OVAL):
                return hole.width
            return None
        if dim_id.startswith("note_"):
            return None
        if dim_id in ("c_d", "c_d2"):
            return self.circle.diameter
        if dim_id == "w_all":
            return self.rect.width
        if dim_id == "h_all":
            return self.rect.height

        ccx, ccy = self.contour_center()
        ox, oy = self.datum_origin()
        if dim_id.endswith("_ox"):
            hole = self.get_hole(dim_id[:-3])
            if hole is None:
                return None
            if self.contour_kind == ContourKind.CIRCLE:
                return hole.cx - ccx
            return hole.cx - ox
        if dim_id.endswith("_oy"):
            hole = self.get_hole(dim_id[:-3])
            if hole is None:
                return None
            if self.contour_kind == ContourKind.CIRCLE:
                return hole.cy - ccy
            return hole.cy - oy
        if dim_id.endswith("_gh"):
            arr = self.get_array(dim_id[:-3])
            if arr and arr.kind == ArrayKind.GRID:
                return arr.step_x
            return None
        if dim_id.endswith("_gv"):
            arr = self.get_array(dim_id[:-3])
            if arr and arr.kind == ArrayKind.GRID:
                return arr.step_y
            return None
        if dim_id.endswith("_glx"):
            arr = self.get_array(dim_id[:-4])
            if arr and arr.kind == ArrayKind.GRID:
                return self.grid_array_span_x(arr)
            return None
        if dim_id.endswith("_gly"):
            arr = self.get_array(dim_id[:-4])
            if arr and arr.kind == ArrayKind.GRID:
                return self.grid_array_span_y(arr)
            return None
        if dim_id.endswith("_cx"):
            arr = self.get_array(dim_id[:-3])
            if arr is None:
                return None
            return arr.center_x - ccx if self.contour_kind == ContourKind.CIRCLE else arr.center_x
        if dim_id.endswith("_cy"):
            arr = self.get_array(dim_id[:-3])
            if arr is None:
                return None
            return arr.center_y - ccy if self.contour_kind == ContourKind.CIRCLE else arr.center_y
        if dim_id.endswith("_h"):
            m = self.get_measure(dim_id[:-2])
            if m is not None:
                return abs(m.p2x - m.p1x)
        if dim_id.endswith("_v"):
            m = self.get_measure(dim_id[:-2])
            if m is not None:
                return abs(m.p2y - m.p1y)
        if dim_id.endswith("_d"):
            m = self.get_measure(dim_id[:-2])
            if m is not None:
                return math.hypot(m.p2x - m.p1x, m.p2y - m.p1y)
        for suffix in ("_left", "_right", "_top", "_bottom"):
            if dim_id.endswith(suffix):
                sid = dim_id[: -len(suffix)]
                s = self.get_shutter(sid)
                if s is None:
                    return None
                _, _, cw, ch = self.contour_bounds()
                left, right, top, bottom = self.shutter_edge_refs(s)
                if suffix == "_left":
                    return left
                if suffix == "_right":
                    return cw - right
                if suffix == "_top":
                    return top
                return ch - bottom
        if dim_id.endswith("_rh"):
            rid = dim_id[:-3]
            r = self.get_drawn_rect(rid)
            if r is not None:
                return r.height
            s = self.get_shutter(rid)
            return s.height if s else None
        if dim_id.endswith("_rw"):
            r = self.get_drawn_rect(dim_id[:-3])
            if r is not None:
                return r.width
            s = self.get_shutter(dim_id[:-3])
            return s.width if s else None
        if dim_id.endswith("_dist"):
            line = self.get_infinite_line(dim_id[:-5])
            if line is not None:
                return abs(line.offset)
        return None

    @staticmethod
    def _is_zero_measurement(value: float | None) -> bool:
        return value is not None and abs(value) < 1e-9

    def is_zero_dimension(self, dim_id: str) -> bool:
        """True when the measured value is zero — such annotations are never shown."""
        if dim_id.startswith("note_") and dim_id.endswith("_ang"):
            val = self.get_dimension_value(dim_id)
            return val is None or not self.spoke_angle_needs_annotation(val)
        if dim_id.startswith("note_") and dim_id.endswith("_d"):
            return self._is_zero_measurement(self.get_dimension_value(dim_id))
        if dim_id.startswith("note_") and dim_id not in ("note_contour_corner", "note_contour_d"):
            if dim_id.endswith(("_r", "_a", "_s")):
                return self._is_zero_measurement(self.get_dimension_value(dim_id))
            hole = self.get_hole(dim_id[len("note_"):])
            if hole is None:
                return False
            if hole.kind in (HoleKind.CIRCLE, HoleKind.POLYGON):
                return self._is_zero_measurement(hole.diameter)
            return self._is_zero_measurement(hole.width) and self._is_zero_measurement(hole.height)
        if dim_id == "note_contour_d":
            return self._is_zero_measurement(self.circle.diameter)
        if dim_id == "note_contour_corner":
            return self._is_zero_measurement(self.rect.corner_size)
        return self._is_zero_measurement(self.get_dimension_value(dim_id))

    def set_dimension_value(self, dim_id: str, value: float) -> bool:
        """Apply a new measured distance to the geometry behind a dimension."""
        from app.geometry.dim_lock import is_annotation_locked
        if is_annotation_locked(self, dim_id):
            return False
        if dim_id in ("c_d", "c_d2", "note_contour_d"):
            self.circle.diameter = max(1.0, value)
            self.update_auto_name()
            return True
        if dim_id == "w_all":
            self.rect.width = max(1.0, value)
            self.rect.clamp_corner()
            self.update_auto_name()
            return True
        if dim_id == "h_all":
            self.rect.height = max(1.0, value)
            self.rect.clamp_corner()
            self.update_auto_name()
            return True

        if dim_id.endswith("_sl") or dim_id.endswith("_sd"):
            return False

        if dim_id.startswith("note_") and dim_id.endswith("_d"):
            mid = dim_id[5:-2]
            m = self.get_measure(mid)
            if m is not None and m.kind == "diameter":
                from app.geometry.measure_bind import apply_circle_size
                apply_circle_size(m.anchor1, value, self)
                m.size = value
                return True
            hole = self.get_hole(mid)
            if hole is None:
                return False
            if hole.kind == HoleKind.CIRCLE:
                hole.diameter = max(0.1, value)
            elif hole.kind == HoleKind.POLYGON:
                hole.diameter = max(0.1, value)
            else:
                return False
            self._after_hole_geometry_change(hole.id)
            return True
        if dim_id.startswith("note_") and dim_id not in (
            "note_contour_corner", "note_contour_d",
        ) and not dim_id.endswith(("_r", "_a", "_s", "_ang", "_d")):
            hole = self.get_hole(dim_id[5:])
            if hole is not None and hole.kind in (HoleKind.RECT, HoleKind.OVAL):
                hole.width = max(0.1, value)
                self._after_hole_geometry_change(hole.id)
                return True
        if dim_id.startswith("note_") and dim_id.endswith("_ang"):
            hole = self.get_hole(dim_id[5:-4])
            if hole is None:
                return False
            hole.angle = value % 360.0
            self._after_hole_geometry_change(hole.id)
            return True

        ccx, ccy = self.contour_center()
        ox, oy = self.datum_origin()
        if dim_id.endswith("_ox"):
            hole = self.get_hole(dim_id[:-3])
            if hole is None:
                return False
            new_cx = ccx + value if self.contour_kind == ContourKind.CIRCLE else ox + value
            self.move_primary_hole(hole.id, new_cx, hole.cy)
            return True
        if dim_id.endswith("_oy"):
            hole = self.get_hole(dim_id[:-3])
            if hole is None:
                return False
            new_cy = ccy + value if self.contour_kind == ContourKind.CIRCLE else oy + value
            self.move_primary_hole(hole.id, hole.cx, new_cy)
            return True
        if dim_id.endswith("_gh"):
            arr = self.get_array(dim_id[:-3])
            if arr and arr.kind == ArrayKind.GRID:
                self.set_grid_array_step_x(arr, value)
                return True
            return False
        if dim_id.endswith("_gv"):
            arr = self.get_array(dim_id[:-3])
            if arr and arr.kind == ArrayKind.GRID:
                self.set_grid_array_step_y(arr, value)
                return True
            return False
        if dim_id.endswith("_glx"):
            arr = self.get_array(dim_id[:-4])
            if arr and arr.kind == ArrayKind.GRID:
                self.set_grid_array_span_x(arr, value)
                return True
            return False
        if dim_id.endswith("_gly"):
            arr = self.get_array(dim_id[:-4])
            if arr and arr.kind == ArrayKind.GRID:
                self.set_grid_array_span_y(arr, value)
                return True
            return False
        if dim_id.endswith("_cx"):
            arr = self.get_array(dim_id[:-3])
            if arr is None:
                return False
            arr.center_x = ccx + value if self.contour_kind == ContourKind.CIRCLE else value
            self.sync_circular_array_radius(arr)
            return True
        if dim_id.endswith("_cy"):
            arr = self.get_array(dim_id[:-3])
            if arr is None:
                return False
            arr.center_y = ccy + value if self.contour_kind == ContourKind.CIRCLE else value
            self.sync_circular_array_radius(arr)
            return True
        if dim_id.startswith("note_") and dim_id.endswith("_r"):
            mid = dim_id[5:-2]
            m = self.get_measure(mid)
            if m is not None and m.kind == "radius":
                from app.geometry.measure_bind import apply_circle_size
                apply_circle_size(m.anchor1, value, self)
                m.size = value
                return True
            arr = self.get_array(mid)
            if arr is None or arr.kind != ArrayKind.CIRCULAR:
                return False
            self.move_circular_array_radius(arr, value)
            return True
        if dim_id.startswith("note_") and dim_id.endswith("_a"):
            arr = self.get_array(dim_id[5:-2])
            if arr is None or arr.kind != ArrayKind.CIRCULAR:
                return False
            self.set_circular_array_spoke_angle(arr, value)
            return True
        if dim_id.startswith("note_") and dim_id.endswith("_s"):
            arr = self.get_array(dim_id[5:-2])
            if arr is None or arr.kind != ArrayKind.CIRCULAR:
                return False
            self.set_circular_array_step_angle(arr, value)
            return True
        if dim_id.endswith("_dist"):
            line = self.get_infinite_line(dim_id[:-5])
            if line is None:
                return False
            if line.locked:
                from app.geometry.infinite_line_bind import set_infinite_line_distance_locked
                set_infinite_line_distance_locked(line, self, value)
            else:
                from app.geometry.infinite_line_bind import set_infinite_line_distance
                set_infinite_line_distance(line, self, value)
            return True
        if dim_id.endswith("_h"):
            from app.geometry.measure_bind import apply_measure_horizontal
            return apply_measure_horizontal(self, dim_id[:-2], value)
        if dim_id.endswith("_v"):
            from app.geometry.measure_bind import apply_measure_vertical
            return apply_measure_vertical(self, dim_id[:-2], value)
        mid = dim_id[:-2] if dim_id.endswith("_d") else ""
        if mid and self.get_measure(mid) is not None:
            from app.geometry.measure_bind import apply_measure_distance
            m = self.get_measure(mid)
            if m is not None and m.kind == "linear":
                return apply_measure_distance(self, mid, value)
        if dim_id.endswith("_rw"):
            r = self.get_drawn_rect(dim_id[:-3])
            if r is not None:
                r.width = max(1.0, value)
                return True
            s = self.get_shutter(dim_id[:-3])
            if s is not None:
                s.width = max(1.0, value)
                return True
        if dim_id.endswith("_rh"):
            rid = dim_id[:-3]
            r = self.get_drawn_rect(rid)
            if r is not None:
                r.height = max(1.0, value)
                return True
            s = self.get_shutter(rid)
            if s is not None:
                s.height = max(1.0, value)
                return True
        return False

    def set_hole_polygon_dims(self, hole_id: str, diameter: float, sides: int) -> bool:
        hole = self.get_hole(hole_id)
        if hole is None or hole.kind != HoleKind.POLYGON:
            return False
        hole.diameter = max(0.1, diameter)
        hole.sides = max(3, int(sides))
        self._after_hole_geometry_change(hole.id)
        return True

    def set_hole_leader_sizes(self, hole_id: str, width: float, height: float) -> bool:
        hole = self.get_hole(hole_id)
        if hole is None or hole.kind not in (HoleKind.RECT, HoleKind.OVAL):
            return False
        hole.width = max(0.1, width)
        hole.height = max(0.1, height)
        self._after_hole_geometry_change(hole.id)
        return True

    def _after_hole_geometry_change(self, hole_id: str) -> None:
        for arr in self.arrays:
            if arr.source_hole_id == hole_id:
                self.sync_circular_array_radius(arr)

    def toggle_dimension_visibility(self, dim_id: str) -> bool:
        if dim_id.startswith("note_"):
            st = self.get_leader_state(dim_id)
            st.always_show = not st.always_show
        else:
            st = self.get_dim_state(dim_id)
            st.always_show = not st.always_show
        self.notify()
        return True

    def get_leader_state(self, note_id: str) -> LeaderState:
        if note_id not in self.leader_states:
            self.leader_states[note_id] = LeaderState(
                note_id=note_id, font_size=self.default_font_size,
            )
        return self.leader_states[note_id]

    def add_measure(
        self,
        p1x: float, p1y: float, p2x: float, p2y: float,
        *,
        kind: str = "linear",
        size: float = 0.0,
        anchor1: MeasureAnchor | None = None,
        anchor2: MeasureAnchor | None = None,
    ) -> MeasureAnnotation:
        from app.models.base import MeasureAnchor as MA
        m = MeasureAnnotation(
            p1x=p1x, p1y=p1y, p2x=p2x, p2y=p2y,
            kind=kind, size=size,
            name=f"Размер {len(self.measures) + 1}",
            anchor1=anchor1 or MA("free", x=p1x, y=p1y),
            anchor2=anchor2 or MA("free", x=p2x, y=p2y),
        )
        self.measures.append(m)
        self.select(SelectionKind.MEASURE, m.id)
        self.notify()
        return m

    def sync_all_measure_points(self) -> None:
        from app.geometry.measure_bind import (
            resolve_circle_measure_anchor, resolve_measure_anchor, sync_measure_points,
        )
        tol = 2.0
        for m in self.measures:
            if m.kind in ("diameter", "radius"):
                if m.anchor1.kind in ("free", ""):
                    m.anchor1 = resolve_circle_measure_anchor(
                        self, m.p1x, m.p1y, m.kind, m.size, tol,
                    )
            else:
                if m.anchor1.kind in ("free", ""):
                    m.anchor1 = resolve_measure_anchor(self, m.p1x, m.p1y, tol)
                if m.anchor2.kind in ("free", ""):
                    m.anchor2 = resolve_measure_anchor(self, m.p2x, m.p2y, tol)
            sync_measure_points(self, m)

    def dim_ids_for_drawn_rect(self, rect_id: str) -> list[str]:
        return [f"{rect_id}_rw", f"{rect_id}_rh"]

    def get_measure(self, measure_id: str) -> Optional[MeasureAnnotation]:
        for m in self.measures:
            if m.id == measure_id:
                return m
        return None

    def leader_ids_for_measure(self, measure_id: str) -> list[str]:
        m = self.get_measure(measure_id)
        if m is None:
            return []
        if m.kind == "diameter":
            return [f"note_{measure_id}_d"]
        if m.kind == "radius":
            return [f"note_{measure_id}_r"]
        return []

    def annotation_ids_for_measure(self, measure_id: str) -> list[str]:
        return self.dim_ids_for_measure(measure_id) + self.leader_ids_for_measure(measure_id)

    def dim_ids_for_measure(self, measure_id: str) -> list[str]:
        m = self.get_measure(measure_id)
        if m is None:
            return []
        if m.kind != "linear":
            return []
        ids = [f"{measure_id}_h", f"{measure_id}_v"]
        if self.measure_needs_angled_dim(m):
            ids.append(f"{measure_id}_d")
        return ids

    @staticmethod
    def measure_needs_angled_dim(m: MeasureAnnotation) -> bool:
        if m.kind != "linear":
            return False
        dx = m.p2x - m.p1x
        dy = m.p2y - m.p1y
        if math.hypot(dx, dy) < 1e-6:
            return False
        angle = math.degrees(math.atan2(dy, dx)) % 180.0
        rem = angle % 90.0
        return rem > 0.05 and rem < 90.0 - 0.05

    def add_shutter(self, cx: float, cy: float, width: float, height: float) -> ShutterRegion:
        w = max(1.0, abs(width))
        h = max(1.0, abs(height))
        s = ShutterRegion(
            cx=cx, cy=cy, width=w, height=h,
            name=f"Шторки {len(self.shutters) + 1}",
            color=HOLE_COLORS[len(self.shutters) % len(HOLE_COLORS)],
        )
        self.shutters.append(s)
        self.select(SelectionKind.SHUTTER, s.id)
        self.notify()
        return s

    def get_shutter(self, shutter_id: str) -> Optional[ShutterRegion]:
        for s in self.shutters:
            if s.id == shutter_id:
                return s
        return None

    def move_shutter(self, shutter_id: str, cx: float, cy: float) -> None:
        if self.is_movement_blocked(SelectionKind.SHUTTER, shutter_id):
            return
        s = self.get_shutter(shutter_id)
        if s is None:
            return
        s.cx, s.cy = cx, cy

    def resize_shutter_edge(self, shutter_id: str, edge: str, value: float) -> None:
        if self.is_resize_blocked(SelectionKind.SHUTTER, shutter_id):
            return
        s = self.get_shutter(shutter_id)
        if s is None:
            return
        from app.editor.region_rect import apply_edge_position
        s.cx, s.cy, s.width, s.height = apply_edge_position(
            edge, s.cx, s.cy, s.width, s.height, value,
        )

    def add_infinite_line(
        self, src_x1: float, src_y1: float, src_x2: float, src_y2: float, offset: float,
        source_anchor: MeasureAnchor | None = None,
    ) -> InfiniteLine:
        from app.geometry.infinite_line_bind import init_infinite_geometry
        line = InfiniteLine(
            name=f"Всп. линия {len(self.infinite_lines) + 1}",
            color=HOLE_COLORS[len(self.infinite_lines) % len(HOLE_COLORS)],
            source_anchor=source_anchor or MeasureAnchor(),
        )
        init_infinite_geometry(line, src_x1, src_y1, src_x2, src_y2, offset)
        self.infinite_lines.append(line)
        self.select(SelectionKind.INFINITE_LINE, line.id)
        self.notify()
        return line

    def sync_infinite_lines(self) -> None:
        from app.geometry.infinite_line_bind import init_infinite_geometry, sync_infinite_line_offset
        for line in self.infinite_lines:
            if (
                abs(line.inf_x2 - line.inf_x1) < 1e-9
                and abs(line.inf_y2 - line.inf_y1) < 1e-9
                and (abs(line.src_x2 - line.src_x1) > 1e-9 or abs(line.src_y2 - line.src_y1) > 1e-9)
            ):
                init_infinite_geometry(
                    line, line.src_x1, line.src_y1, line.src_x2, line.src_y2, line.offset,
                )
            sync_infinite_line_offset(line, self)

    def move_infinite_line(self, line_id: str, dx: float, dy: float) -> None:
        if self.is_movement_blocked(SelectionKind.INFINITE_LINE, line_id):
            return
        from app.geometry.infinite_line_bind import move_infinite_line_by, sync_infinite_line_offset
        line = self.get_infinite_line(line_id)
        if line is None or line.locked:
            return
        move_infinite_line_by(line, dx, dy)
        sync_infinite_line_offset(line, self)

    def get_infinite_line(self, line_id: str) -> Optional[InfiniteLine]:
        for ln in self.infinite_lines:
            if ln.id == line_id:
                return ln
        return None

    def dim_ids_for_infinite_line(self, line_id: str) -> list[str]:
        return [f"{line_id}_dist"]

    def add_drawn_rect(self, cx: float, cy: float, width: float, height: float) -> DrawnRectangle:
        w = max(1.0, abs(width))
        h = max(1.0, abs(height))
        r = DrawnRectangle(
            cx=cx, cy=cy, width=w, height=h,
            name=f"Прямоугольник {len(self.drawn_rects) + 1}",
            color=HOLE_COLORS[len(self.drawn_rects) % len(HOLE_COLORS)],
        )
        self.drawn_rects.append(r)
        self.select(SelectionKind.DRAWN_RECT, r.id)
        self.notify()
        return r

    def get_drawn_rect(self, rect_id: str) -> Optional[DrawnRectangle]:
        for r in self.drawn_rects:
            if r.id == rect_id:
                return r
        return None

    def move_drawn_rect(self, rect_id: str, cx: float, cy: float) -> None:
        if self.is_movement_blocked(SelectionKind.DRAWN_RECT, rect_id):
            return
        r = self.get_drawn_rect(rect_id)
        if r is None:
            return
        r.cx, r.cy = cx, cy

    def resize_drawn_rect_edge(self, rect_id: str, edge: str, value: float) -> None:
        if self.is_resize_blocked(SelectionKind.DRAWN_RECT, rect_id):
            return
        r = self.get_drawn_rect(rect_id)
        if r is None:
            return
        from app.editor.region_rect import apply_edge_position
        r.cx, r.cy, r.width, r.height = apply_edge_position(
            edge, r.cx, r.cy, r.width, r.height, value,
        )

    def snap_line_targets(self, exclude_region_id: str = "") -> list:
        from app.geometry.line_math import collect_line_segments, infinite_line_segments, LineSeg
        segs: list[LineSeg] = []
        for seg in collect_line_segments(self):
            if exclude_region_id and seg.obj_id == exclude_region_id:
                continue
            segs.append(seg)
        segs.extend(infinite_line_segments(self))
        return segs

    def dim_ids_for_shutter(self, shutter_id: str) -> list[str]:
        return [
            f"{shutter_id}_left", f"{shutter_id}_right",
            f"{shutter_id}_top", f"{shutter_id}_bottom",
            f"{shutter_id}_rw", f"{shutter_id}_rh",
        ]

    def shutter_edge_refs(self, s: ShutterRegion) -> tuple[float, float, float, float]:
        left = s.cx - s.width / 2
        right = s.cx + s.width / 2
        top = s.cy - s.height / 2
        bottom = s.cy + s.height / 2
        return left, right, top, bottom

    def snap_points_for_shutter_drag(self, shutter_id: str) -> list[tuple[float, float]]:
        points = self.snap_points_for_drag("", 0)
        for s in self.shutters:
            if s.id != shutter_id:
                points.append((s.cx, s.cy))
                left, right, top, bottom = self.shutter_edge_refs(s)
                points.extend([
                    (left, top), (right, top), (right, bottom), (left, bottom),
                    (left, (top + bottom) / 2), (right, (top + bottom) / 2),
                    ((left + right) / 2, top), ((left + right) / 2, bottom),
                ])
        for r in self.drawn_rects:
            points.append((r.cx, r.cy))
            left, right, top, bottom = self.region_edge_refs(r.cx, r.cy, r.width, r.height)
            points.extend([
                (left, top), (right, top), (right, bottom), (left, bottom),
            ])
        for hole in self.holes:
            for i, rh in enumerate(self._resolve_single_hole(hole)):
                if not self.is_instance_visible_in_editor(hole.id, i):
                    continue
                points.append((rh.cx, rh.cy))
        return points

    @staticmethod
    def region_edge_refs(cx: float, cy: float, width: float, height: float) -> tuple[float, float, float, float]:
        left = cx - width / 2
        right = cx + width / 2
        top = cy - height / 2
        bottom = cy + height / 2
        return left, right, top, bottom

    def snap_points_for_drawn_rect_drag(self, rect_id: str) -> list[tuple[float, float]]:
        return self.snap_points_for_shutter_drag(rect_id)

    def snap_points_for_region_edge_drag(self, region_id: str) -> list[tuple[float, float]]:
        return self.snap_points_for_shutter_drag(region_id)

    def all_snap_points(self) -> list[tuple[float, float]]:
        """Snap targets for measure tool — corners and centers of all visible geometry."""
        points: list[tuple[float, float]] = []
        _, _, w, h = self.contour_bounds()
        if self.contour_kind == ContourKind.RECT:
            cx, cy = w / 2, h / 2
            points.extend([
                (0, 0), (w, 0), (w, h), (0, h),
                (cx, 0), (w, cy), (cx, h), (0, cy), (cx, cy),
            ])
        elif self.contour_kind == ContourKind.CIRCLE:
            cx, cy = self.contour_center()
            r = self.circle.diameter / 2
            points.extend([
                (cx, cy), (cx - r, cy), (cx + r, cy), (cx, cy - r), (cx, cy + r),
            ])
        else:
            points.extend(self.dxf_snap_points())
            if self.dxf_contour.origin_set:
                ox, oy = self.datum_origin()
                points.append((ox, oy))
        for arr in self.arrays:
            if arr.kind == ArrayKind.CIRCULAR:
                points.append((arr.center_x, arr.center_y))
        for hole in self.holes:
            for i, rh in enumerate(self._resolve_single_hole(hole)):
                if not self.is_instance_visible_in_editor(hole.id, i):
                    continue
                self._append_snap_points(points, rh)
        for s in self.shutters:
            points.append((s.cx, s.cy))
            left, right, top, bottom = self.shutter_edge_refs(s)
            points.extend([
                (left, top), (right, top), (right, bottom), (left, bottom),
                (left, (top + bottom) / 2), (right, (top + bottom) / 2),
                ((left + right) / 2, top), ((left + right) / 2, bottom),
            ])
        for r in self.drawn_rects:
            points.append((r.cx, r.cy))
            left, right, top, bottom = self.region_edge_refs(r.cx, r.cy, r.width, r.height)
            points.extend([
                (left, top), (right, top), (right, bottom), (left, bottom),
            ])
        return points

    def resolve_holes(self) -> list[ResolvedHole]:
        result: list[ResolvedHole] = []
        for hole in self.holes:
            for i, rh in enumerate(self._resolve_single_hole(hole)):
                if self.is_instance_exported(hole.id, i):
                    result.append(rh)
        return result

    def _resolve_single_hole(self, hole: Hole) -> list[ResolvedHole]:
        pattern: list[ResolvedHole] = [_clone_hole(hole, hole.cx, hole.cy)]
        for arr in self.arrays_for_hole(hole.id):
            pattern = self._apply_array_to_pattern(hole, arr, pattern)
        instances: list[ResolvedHole] = []
        for i, rh in enumerate(pattern):
            key = f"{hole.id}:{i}"
            if key in self.instance_overrides:
                ox, oy = self.instance_overrides[key]
                angle = rh.angle - hole.angle
                instances.append(_clone_hole(hole, ox, oy, angle))
            else:
                instances.append(rh)
        return instances

    def _clone_resolved(self, hole: Hole, rh: ResolvedHole, cx: float, cy: float,
                        angle: float | None = None) -> ResolvedHole:
        return ResolvedHole(
            kind=rh.kind,
            cx=cx,
            cy=cy,
            diameter=rh.diameter,
            width=rh.width,
            height=rh.height,
            angle=rh.angle if angle is None else angle,
            sides=rh.sides,
            source_id=hole.id,
        )

    def _transform_pattern_cell(
        self, hole: Hole, arr: HoleArray, pattern: list[ResolvedHole], ix: int, iy: int,
    ) -> list[ResolvedHole]:
        rad = math.radians(arr.grid_angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        cell_cx, cell_cy = _transform_point(
            hole.cx + ix * arr.step_x, hole.cy + iy * arr.step_y,
            hole.cx, hole.cy, arr.grid_angle,
        )
        out: list[ResolvedHole] = []
        for rh in pattern:
            rel_x, rel_y = rh.cx - hole.cx, rh.cy - hole.cy
            rx = rel_x * cos_a - rel_y * sin_a
            ry = rel_x * sin_a + rel_y * cos_a
            out.append(self._clone_resolved(hole, rh, cell_cx + rx, cell_cy + ry))
        return out

    def _mirror_resolved(self, hole: Hole, rh: ResolvedHole, arr: HoleArray) -> ResolvedHole:
        _, _, w, h = self.contour_bounds()
        if self.contour_kind == ContourKind.CIRCLE:
            ccx, ccy = self.contour_center()
            if arr.mirror_axis == MirrorAxis.HORIZONTAL:
                mx, my = rh.cx, 2 * ccy - rh.cy
            else:
                mx, my = 2 * ccx - rh.cx, rh.cy
        elif arr.mirror_axis == MirrorAxis.HORIZONTAL:
            mx, my = rh.cx, h - rh.cy
        else:
            mx, my = w - rh.cx, rh.cy
        return self._clone_resolved(hole, rh, mx, my)

    def _rotate_resolved_around(
        self, hole: Hole, arr: HoleArray, rh: ResolvedHole, angle_deg: float,
    ) -> ResolvedHole:
        dx, dy = rh.cx - arr.center_x, rh.cy - arr.center_y
        dist = math.hypot(dx, dy)
        a0 = math.atan2(dy, dx)
        a1 = a0 + math.radians(angle_deg)
        cx = arr.center_x + dist * math.cos(a1)
        cy = arr.center_y + dist * math.sin(a1)
        rot = angle_deg if hole.kind != HoleKind.CIRCLE else 0.0
        return self._clone_resolved(hole, rh, cx, cy, rh.angle + rot)

    def _apply_array_to_pattern(
        self, hole: Hole, arr: HoleArray, pattern: list[ResolvedHole],
    ) -> list[ResolvedHole]:
        if arr.kind == ArrayKind.GRID:
            result = list(pattern)
            for iy in range(arr.count_y):
                for ix in range(arr.count_x):
                    if ix == 0 and iy == 0:
                        continue
                    result.extend(self._transform_pattern_cell(hole, arr, pattern, ix, iy))
            return result
        if arr.kind == ArrayKind.MIRROR:
            mirrored = [self._mirror_resolved(hole, rh, arr) for rh in pattern]
            return pattern + mirrored
        if arr.kind == ArrayKind.CIRCULAR:
            result = list(pattern)
            step = arr.step_angle if arr.step_angle > 0 else (360.0 / arr.count if arr.count else 360.0)
            for i in range(1, arr.count):
                for rh in pattern:
                    result.append(self._rotate_resolved_around(hole, arr, rh, i * step))
            return result
        return pattern

    def set_instance_position(self, hole_id: str, index: int, x: float, y: float) -> None:
        if index == 0:
            self.move_primary_hole(hole_id, x, y)
        else:
            self.instance_overrides[f"{hole_id}:{index}"] = (x, y)

    def translate_hole_pattern(self, hole_id: str, index: int, x: float, y: float) -> None:
        hole = self.get_hole(hole_id)
        if hole is None:
            return
        resolved = self._resolve_single_hole(hole)
        if index < 0 or index >= len(resolved):
            return
        cur = resolved[index]
        dx, dy = x - cur.cx, y - cur.cy
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            return
        hole.cx += dx
        hole.cy += dy
        prefix = f"{hole_id}:"
        for key, (ox, oy) in list(self.instance_overrides.items()):
            if key.startswith(prefix):
                self.instance_overrides[key] = (ox + dx, oy + dy)
        for arr in self.arrays:
            if arr.source_hole_id == hole_id:
                self.sync_circular_array_radius(arr)

    def sync_circular_array_radius(self, arr: HoleArray) -> None:
        hole = self.get_hole(arr.source_hole_id)
        if hole is None:
            return
        arr.radius = math.hypot(hole.cx - arr.center_x, hole.cy - arr.center_y)

    def move_circular_array_radius(self, arr: HoleArray, new_radius: float) -> None:
        if self.is_movement_blocked(SelectionKind.ARRAY, arr.id):
            return
        hole = self.get_hole(arr.source_hole_id)
        if hole is None:
            return
        arr.radius = max(0.0, new_radius)
        angle = math.atan2(hole.cy - arr.center_y, hole.cx - arr.center_x)
        hole.cx = arr.center_x + arr.radius * math.cos(angle)
        hole.cy = arr.center_y + arr.radius * math.sin(angle)

    def snap_points_for_drag(self, hole_id: str, instance_index: int) -> list[tuple[float, float]]:
        """Return snap targets: contour key points + centers of all other visible holes.

        Keeps the snap set minimal for smooth dragging.
        """
        points: list[tuple[float, float]] = []
        _, _, w, h = self.contour_bounds()
        if self.contour_kind == ContourKind.RECT:
            cx, cy = w / 2, h / 2
            # Corners, center, edge midpoints (center defines vertical/horizontal axes)
            points.extend([
                (0, 0), (w, 0), (w, h), (0, h),
                (cx, 0), (w, cy), (cx, h), (0, cy),
                (cx, cy),
            ])
        else:
            cx, cy = self.contour_center()
            r = self.circle.diameter / 2
            # Center + 4 cardinal points on circumference
            points.extend([
                (cx, cy), (cx - r, cy), (cx + r, cy), (cx, cy - r), (cx, cy + r),
            ])

        # Circular array centers
        for arr in self.arrays:
            if arr.kind == ArrayKind.CIRCULAR:
                points.append((arr.center_x, arr.center_y))

        # Centers of all other visible hole instances only (no sub-geometry)
        for other in self.holes:
            for i, rh in enumerate(self._resolve_single_hole(other)):
                if other.id == hole_id:
                    continue
                if not self.is_instance_visible_in_editor(other.id, i):
                    continue
                points.append((rh.cx, rh.cy))
        return points

    def snap_points_for_array_center_drag(self, array_id: str) -> list[tuple[float, float]]:
        """Snap targets for circular array center handle — same as holes, minus own center."""
        arr = self.get_array(array_id)
        if arr is None:
            return []
        points = self.snap_points_for_drag(arr.source_hole_id, 0)
        if arr.kind != ArrayKind.CIRCULAR:
            return points
        cx, cy = arr.center_x, arr.center_y
        return [
            (x, y) for x, y in points
            if abs(x - cx) > 1e-9 or abs(y - cy) > 1e-9
        ]

    def _append_snap_points(self, points: list[tuple[float, float]], rh: ResolvedHole) -> None:
        points.append((rh.cx, rh.cy))
        if rh.kind == HoleKind.RECT:
            hw, hh = rh.width / 2, rh.height / 2
            rad = math.radians(rh.angle)
            cos_a, sin_a = math.cos(rad), math.sin(rad)
            for lx, ly in [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh),
                           (0, -hh), (hw, 0), (0, hh), (-hw, 0)]:
                wx = rh.cx + lx * cos_a - ly * sin_a
                wy = rh.cy + lx * sin_a + ly * cos_a
                points.append((wx, wy))
        elif rh.kind == HoleKind.OVAL:
            g = slot_geom(rh.width, rh.height)
            if g.arc_offset >= 1e-9:
                c1, c2 = slot_arc_centers_world(rh.cx, rh.cy, rh.width, rh.height, rh.angle)
                points.append(c1)
                points.append(c2)
            half = g.cap / 2.0
            rad = math.radians(rh.angle)
            cos_a, sin_a = math.cos(rad), math.sin(rad)
            for lx, ly in [(0, -half), (0, half), (-half, 0), (half, 0)]:
                wx = rh.cx + lx * cos_a - ly * sin_a
                wy = rh.cy + lx * sin_a + ly * cos_a
                points.append((wx, wy))
        elif rh.kind in (HoleKind.CIRCLE, HoleKind.POLYGON):
            r = rh.diameter / 2
            points.extend([
                (rh.cx - r, rh.cy), (rh.cx + r, rh.cy),
                (rh.cx, rh.cy - r), (rh.cx, rh.cy + r),
            ])
