from __future__ import annotations

import math

from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPainterPath, QPen
from PyQt6.QtWidgets import QApplication, QGraphicsEllipseItem, QGraphicsItem, QGraphicsPathItem, QGraphicsRectItem, QGraphicsScene

from app.editor.guides import SnapGuideItem
from app.editor.placement_preview import ToolPlacementPreview
from app.editor.infinite_line_items import InfiniteLineGraphicsItem
from app.editor.rectangle_items import DrawnRectangleGraphicsItem
from app.editor.shutter_items import ShutterRegionGraphicsItem
from app.editor.handles import ArrayCenterHandle, OriginHandle, PlacementCrosshairItem
from app.editor.items import ContourGraphicsItem, DimGraphicsItem, HoleGraphicsItem, LeaderGraphicsItem
from app.formatting import format_dim
from app.geometry.slot import (
    polygon_inscribed_radius, slot_center_axes_world,
)
from app.models.base import ContourKind, HoleKind, HoleArray, SelectionKind, ArrayKind, MirrorAxis, _transform_point
from app.models.document import Document
from app.theme import canvas_colors


DIM_STEP = 11
DIM_EXT = 7
SCENE_EXTENT = 200_000.0


class EditorSceneController:
    def __init__(self, document: Document, scene: QGraphicsScene, on_edit_dimension=None,
                 on_add_shutter=None, on_add_infinite_line=None, on_add_rectangle=None,
                 on_place_hole=None, on_place_array=None,
                 on_aux_distance_input=None, on_rect_size_input=None):
        self.document = document
        self.scene = scene
        self.on_edit_dimension = on_edit_dimension
        self.on_add_shutter = on_add_shutter
        self.on_add_infinite_line = on_add_infinite_line
        self.on_add_rectangle = on_add_rectangle
        self.on_place_hole = on_place_hole
        self.on_place_array = on_place_array
        self.on_aux_distance_input = on_aux_distance_input
        self.on_rect_size_input = on_rect_size_input
        self.colors = canvas_colors()
        self._placement_preview = ToolPlacementPreview(scene)
        self._lane_counters: dict[str, int] = {}
        self._built_offsets: dict[str, list[float]] = {}
        self._drag_dim_refs: dict[str, float] = {}
        self._drag_line_anchors: dict[str, tuple[float, float, float, float]] = {}
        self._guide_item = SnapGuideItem()
        self.measure_mode = False
        self.measure_p1: tuple[float, float] | None = None
        self.measure_pending_kind: str = "linear"
        self.measure_pending_size: float = 0.0
        self.measure_leader_placement = False
        self._measure_preview_leader = None
        self._measure_marker_p1: QGraphicsEllipseItem | None = None
        self._measure_marker_cursor: QGraphicsEllipseItem | None = None
        self.origin_placement_mode = False
        self._origin_placement_marker: PlacementCrosshairItem | None = None
        self.shutter_mode = False
        self.aux_line_mode = False
        self.rectangle_mode = False
        self.hole_place_mode = False
        self.array_place_mode = False
        self._hole_place_cursor: tuple[float, float] | None = None
        self._hole_place_color = "#e03131"
        self._array_place_hole_id = ""
        self._array_place_count = 2
        self._array_place_cursor: tuple[float, float] | None = None
        self._aux_offset_sign = 1.0
        self._rect_place_cursor: tuple[float, float] | None = None
        self._aux_src: tuple[float, float, float, float] | None = None
        self._aux_current_offset = 0.0
        self._aux_pick_seg = None
        self._aux_preview: QGraphicsPathItem | None = None
        self._shutter_draw_p1: tuple[float, float] | None = None
        self._rect_draw_p1: tuple[float, float] | None = None
        self._rect_preview: QGraphicsRectItem | None = None
        self._shutter_preview: QGraphicsRectItem | None = None
        self._shutter_drag_dim_refs: dict[str, float] = {}
        self._measure_pending_anchor = None
        self._content_rect = QRectF()
        self.scene.addItem(self._guide_item)

    def content_rect(self) -> QRectF:
        return self._content_rect

    def rebuild(self) -> QRectF:
        self.scene.clear()
        self._placement_preview.on_scene_cleared()
        self._measure_marker_p1 = None
        self._measure_marker_cursor = None
        self._measure_preview_leader = None
        self._origin_placement_marker = None
        self._shutter_preview = None
        self._aux_preview = None
        self._rect_preview = None
        self._guide_item = SnapGuideItem()
        self.scene.addItem(self._guide_item)
        self._guide_item.clear()
        self._lane_counters = {"top": 0, "left": 0, "bottom": 0, "right": 0}
        self._built_offsets = {"top": [], "left": [], "bottom": [], "right": []}
        self._drag_dim_refs = {}
        self._drag_line_anchors = {}
        self.scene.setBackgroundBrush(self.colors["background"])
        doc = self.document
        doc.sync_all_measure_points()
        doc.sync_infinite_lines()
        sel = doc.selection

        self.scene.addItem(ContourGraphicsItem(doc, self.colors, self._on_select))

        for hole in doc.holes:
            resolved_list = doc._resolve_single_hole(hole)
            for i, rh in enumerate(resolved_list):
                if not doc.is_instance_visible_in_editor(hole.id, i):
                    continue
                selected = self._is_instance_selected(hole.id, i)
                draggable = self._is_instance_draggable(hole.id, i)
                self.scene.addItem(HoleGraphicsItem(
                    hole.id, i, rh, hole.color, self.colors,
                    selected, draggable,
                    self._on_hole_select,
                    self._on_hole_move,
                    self._on_hole_move_end,
                    self._on_hole_drag_start,
                ))

        self._draw_selection_axes()

        self._build_contour_dims()
        self._build_contour_leader()
        self._build_contour_diameter_leader()
        if doc.contour_kind == ContourKind.DXF and doc.dxf_contour.origin_set and not self.origin_placement_mode:
            ox, oy = doc.datum_origin()
            origin_item = OriginHandle(doc, self._on_origin_select)
            origin_item.setPos(ox, oy)
            self.scene.addItem(origin_item)
        if self.origin_placement_mode:
            self._sync_origin_placement_marker()
        for hole in doc.holes:
            self._build_hole_dims(hole)
            self._build_hole_slot_guides(hole)
            self._build_hole_leader(hole)
            self._build_hole_diameter_leader(hole)
            self._build_hole_angle_leader(hole)
            for arr in doc.arrays_for_hole(hole.id):
                if arr.kind == ArrayKind.CIRCULAR:
                    self._build_circular_array_dims(arr, hole)

        for measure in doc.measures:
            self._build_measure_dims(measure)

        for shutter in doc.shutters:
            self._build_shutter(shutter)

        for line in doc.infinite_lines:
            self._build_infinite_line(line)

        for rect in doc.drawn_rects:
            self._build_drawn_rect(rect)

        if sel.kind == SelectionKind.ARRAY and sel.object_id:
            arr = doc.get_array(sel.object_id)
            if arr and arr.kind == ArrayKind.CIRCULAR:
                self.scene.addItem(ArrayCenterHandle(
                    arr.id, arr.center_x, arr.center_y,
                    self._on_array_center_move, self._on_array_center_move_end,
                    self._on_array_center_drag_start,
                ))

        half = SCENE_EXTENT / 2
        self.scene.setSceneRect(-half, -half, SCENE_EXTENT, SCENE_EXTENT)
        bounds = self.scene.itemsBoundingRect()
        pad = 40
        rect = bounds.adjusted(-pad, -pad, pad, pad)
        self._content_rect = rect
        if self.measure_mode:
            self._sync_measure_markers()
        if self.hole_place_mode and self._hole_place_cursor:
            cx, cy = self._hole_place_cursor
            self._placement_preview.show_hole(
                self.document, cx, cy, 6.0, self._hole_place_color,
            )
        elif self.array_place_mode and self._array_place_cursor:
            self._refresh_array_place_preview()
        elif self.rectangle_mode and self._rect_draw_p1 and self._rect_place_cursor:
            p1 = self._rect_draw_p1
            cx, cy = self._rect_place_cursor
            left, right = sorted((p1[0], cx))
            top, bottom = sorted((p1[1], cy))
            self._placement_preview.show_rect(left, top, right, bottom)
        return rect

    def _on_select(self, kind: str, obj_id: str, notify: bool = True):
        from app.models.base import SelectionKind
        mapping = {
            "contour": SelectionKind.CONTOUR,
            "hole": SelectionKind.HOLE,
            "array": SelectionKind.ARRAY,
            "dimension": SelectionKind.DIMENSION,
            "title_block": SelectionKind.TITLE_BLOCK,
            "measure": SelectionKind.MEASURE,
            "shutter": SelectionKind.SHUTTER,
            "infinite_line": SelectionKind.INFINITE_LINE,
            "drawn_rect": SelectionKind.DRAWN_RECT,
            "origin": SelectionKind.ORIGIN,
        }
        self.document.select(mapping.get(kind, SelectionKind.NONE), obj_id, notify=notify)

    def _on_hole_select(self, hole_id: str, instance_index: int, notify: bool = True):
        if instance_index == 0:
            self.document.select(SelectionKind.HOLE, hole_id, notify=notify)
            return
        found = self.document.find_array_for_instance(hole_id, instance_index)
        if found:
            arr, _ = found
            self.document.select(SelectionKind.ARRAY, arr.id, instance_index, notify=notify)

    def _is_instance_draggable(self, hole_id: str, index: int) -> bool:
        if index == 0:
            return True
        found = self.document.find_array_for_instance(hole_id, index)
        if not found:
            return True
        arr, _ = found
        if arr.kind in (ArrayKind.CIRCULAR, ArrayKind.MIRROR):
            return False
        return True

    def _is_instance_selected(self, hole_id: str, index: int) -> bool:
        sel = self.document.selection
        if sel.kind == SelectionKind.HOLE and sel.object_id == hole_id:
            return True
        if sel.kind == SelectionKind.ARRAY and sel.instance_index == index:
            arr = self.document.get_array(sel.object_id)
            if arr and arr.source_hole_id == hole_id:
                return True
        return False

    def _add_scene_line(self, x1: float, y1: float, x2: float, y2: float, pen: QPen) -> None:
        self.scene.addLine(QLineF(x1, y1, x2, y2), pen)

    def _draw_center_axes(self, cx: float, cy: float, bw: float, bh: float, pen: QPen) -> None:
        self._add_scene_line(cx, 0, cx, bh, pen)
        self._add_scene_line(0, cy, bw, cy, pen)

    def _draw_selection_axes(self) -> None:
        doc = self.document
        sel = doc.selection
        _, _, bw, bh = doc.contour_bounds()

        pen_ax = QPen(QColor("#707070"))
        pen_ax.setStyle(Qt.PenStyle.DashLine)
        pen_ax.setCosmetic(True)
        pen_ax.setWidth(1)

        # ── Осевые базового отверстия выбранного элемента ──────────────────
        hole_id = None
        selected_array = None
        if sel.kind == SelectionKind.HOLE:
            hole_id = sel.object_id
        elif sel.kind == SelectionKind.ARRAY:
            selected_array = doc.get_array(sel.object_id)
            if selected_array:
                hole_id = selected_array.source_hole_id

        if hole_id:
            hole = doc.get_hole(hole_id)
            if hole and hole.kind != HoleKind.OVAL:
                resolved = doc._resolve_single_hole(hole)
                if resolved:
                    self._draw_center_axes(resolved[0].cx, resolved[0].cy, bw, bh, pen_ax)

        # ── Осевые для ВСЕХ массивов (всегда) ──────────────────────────────
        pen_circ = QPen(QColor("#707070"))
        pen_circ.setStyle(Qt.PenStyle.DashLine)
        pen_circ.setCosmetic(True)
        pen_circ.setWidth(1)

        pen_mirror = QPen(QColor("#ff8c00"))
        pen_mirror.setStyle(Qt.PenStyle.DashDotLine)
        pen_mirror.setCosmetic(True)
        pen_mirror.setWidth(1)

        for arr in doc.arrays:
            h = doc.get_hole(arr.source_hole_id)
            if h is None:
                continue
            res = doc._resolve_single_hole(h)
            visible = [rh for i, rh in enumerate(res) if doc.is_instance_visible_in_editor(h.id, i)]
            if len(visible) < 2:
                continue

            if arr.kind == ArrayKind.CIRCULAR:
                # Центр кругового массива — всегда
                self._draw_center_axes(arr.center_x, arr.center_y, bw, bh, pen_ax)
                if arr.radius > 0:
                    item = QGraphicsEllipseItem(
                        arr.center_x - arr.radius,
                        arr.center_y - arr.radius,
                        arr.radius * 2,
                        arr.radius * 2,
                    )
                    item.setPen(pen_circ)
                    item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                    item.setZValue(2)
                    self.scene.addItem(item)

            elif arr.kind == ArrayKind.MIRROR:
                if doc.contour_kind == ContourKind.CIRCLE:
                    ccx, ccy = doc.contour_center()
                    if arr.mirror_axis == MirrorAxis.HORIZONTAL:
                        self._add_scene_line(0, ccy, bw, ccy, pen_mirror)
                    else:
                        self._add_scene_line(ccx, 0, ccx, bh, pen_mirror)
                elif arr.mirror_axis == MirrorAxis.HORIZONTAL:
                    self._add_scene_line(0, bh / 2, bw, bh / 2, pen_mirror)
                else:
                    self._add_scene_line(bw / 2, 0, bw / 2, bh, pen_mirror)

            elif arr.kind == ArrayKind.GRID:
                # Осевые по крайним (угловым) отверстиям сетки
                all_xs = sorted({round(rh.cx, 4) for rh in visible})
                all_ys = sorted({round(rh.cy, 4) for rh in visible})
                for x in (all_xs[0], all_xs[-1]):
                    self._add_scene_line(x, 0, x, bh, pen_ax)
                for y in (all_ys[0], all_ys[-1]):
                    self._add_scene_line(0, y, bw, y, pen_ax)

    def _build_circular_array_dims(self, arr, hole) -> None:
        doc = self.document
        color = hole.color
        arr_id = arr.id
        resolved = doc._resolve_single_hole(hole)
        if not resolved:
            return
        base = resolved[0]
        ccx, ccy = doc.contour_center()
        cx_id, cy_id = f"{arr_id}_cx", f"{arr_id}_cy"
        if doc.contour_kind == ContourKind.CIRCLE:
            self._add_dim(
                cx_id, "top", ccx, arr.center_x,
                self._hole_dim_ref(cx_id, arr.center_y),
                format_dim(arr.center_x - ccx), color, "array", arr_id,
                ext1=ccy, ext2=arr.center_y,
            )
            self._add_dim(
                cy_id, "left", ccy, arr.center_y,
                self._hole_dim_ref(cy_id, arr.center_x),
                format_dim(arr.center_y - ccy), color, "array", arr_id,
                ext1=ccx, ext2=arr.center_x,
            )
        else:
            self._add_dim(
                cx_id, "top", 0, arr.center_x,
                self._hole_dim_ref(cx_id, arr.center_y),
                format_dim(arr.center_x), color, "array", arr_id,
                ext1=0.0, ext2=arr.center_y,
            )
        self._add_dim(
            cy_id, "left", 0, arr.center_y,
            self._hole_dim_ref(cy_id, arr.center_x),
            format_dim(arr.center_y), color, "array", arr_id,
            ext1=0.0, ext2=arr.center_x,
        )
        self._build_circular_array_radius_leader(arr, hole, base)
        self._build_circular_array_step_leader(arr, hole, base)
        self._build_circular_array_angle_leader(arr, hole, base)

    def _is_annotation_selected(self, ann_id: str) -> bool:
        sel = self.document.selection
        return sel.kind == SelectionKind.DIMENSION and sel.object_id == ann_id

    def _resolve_annotation_color(self, ann_id: str, base_color: str) -> tuple[str, bool]:
        selected = self._is_annotation_selected(ann_id)
        if self.document.is_annotation_locked(ann_id):
            locked_color = self.colors["dim_locked"].name()
            if selected:
                return self.colors["selection"].name(), True
            return locked_color, False
        if selected:
            return self.colors["selection"].name(), True
        return base_color, False

    def toggle_selected_dimension_visibility(self) -> bool:
        sel = self.document.selection
        if sel.kind == SelectionKind.DIMENSION and sel.object_id:
            return self.document.toggle_dimension_visibility(sel.object_id)
        if sel.kind == SelectionKind.CONTOUR:
            self.document.toggle_object_show_dims("contour", "")
            return True
        if sel.kind == SelectionKind.HOLE and sel.object_id:
            self.document.toggle_object_show_dims("hole", sel.object_id)
            return True
        if sel.kind == SelectionKind.ARRAY and sel.object_id:
            self.document.toggle_object_show_dims("array", sel.object_id)
            return True
        if sel.kind == SelectionKind.MEASURE and sel.object_id:
            self.document.toggle_object_show_dims("measure", sel.object_id)
            return True
        if sel.kind == SelectionKind.SHUTTER and sel.object_id:
            self.document.toggle_object_show_dims("shutter", sel.object_id)
            return True
        if sel.kind == SelectionKind.INFINITE_LINE and sel.object_id:
            self.document.toggle_object_show_dims("infinite_line", sel.object_id)
            return True
        if sel.kind == SelectionKind.DRAWN_RECT and sel.object_id:
            self.document.toggle_object_show_dims("drawn_rect", sel.object_id)
            return True
        return False

    def _circle_marker_line_width(self, *, contour: bool = False, hole_id: str = "") -> float:
        """Pen width of the referenced circle outline — marker size = width/2 + 0.1."""
        sel = self.document.selection
        if contour:
            return 3.0 if sel.kind == SelectionKind.CONTOUR else 2.0
        if hole_id and sel.kind == SelectionKind.HOLE and sel.object_id == hole_id:
            return 2.0
        return 1.0

    def _add_leader_item(
        self, note_id, ax, ay, text, color, font, ox, oy, **extra,
    ) -> None:
        color, selected = self._resolve_annotation_color(note_id, color)
        self.scene.addItem(LeaderGraphicsItem(
            note_id, ax, ay, text, color, font, ox, oy,
            self._on_select, self._on_leader_move, self._on_leader_move_end,
            on_edit=self.on_edit_dimension,
            selected=selected,
            selection_color=self.colors["selection"].name(),
            locked=self.document.is_annotation_locked(note_id),
            **extra,
        ))

    def _draw_circular_spoke_to_pitch(self, arr, angle_deg: float, pen: QPen) -> None:
        """Луч от центра массива по углу первого отверстия до шаговой окружности."""
        if arr.radius < 1e-6:
            return
        a = math.radians(angle_deg)
        cx, cy = arr.center_x, arr.center_y
        ex = cx + arr.radius * math.cos(a)
        ey = cy + arr.radius * math.sin(a)
        self._add_scene_line(cx, cy, ex, ey, pen)

    def _draw_angle_sector(
        self, cx: float, cy: float, arc_r: float,
        start_deg: float, span_deg: float, color: str,
    ) -> None:
        """Замкнутый сектор: центр → дуга → обратно к центру."""
        if arc_r < 1e-6 or abs(span_deg) < 1e-6:
            return
        path = QPainterPath()
        path.moveTo(cx, cy)
        steps = max(4, int(abs(span_deg) / 12))
        for i in range(steps + 1):
            a = math.radians(start_deg + span_deg * i / steps)
            path.lineTo(cx + arc_r * math.cos(a), cy + arc_r * math.sin(a))
        path.closeSubpath()
        pen = QPen(QColor(color))
        pen.setCosmetic(True)
        pen.setWidth(1)
        item = QGraphicsPathItem(path)
        item.setPen(pen)
        item.setBrush(Qt.BrushStyle.NoBrush)
        item.setZValue(4)
        self.scene.addItem(item)

    def _draw_circular_arc(
        self, cx: float, cy: float, arc_r: float,
        start_deg: float, span_deg: float, pen: QPen, *,
        radius_line: bool = True,
    ) -> None:
        if arc_r < 1e-6 or abs(span_deg) < 1e-6:
            return
        a0 = math.radians(start_deg)
        x0 = cx + arc_r * math.cos(a0)
        y0 = cy + arc_r * math.sin(a0)
        if radius_line:
            self._add_scene_line(cx, cy, x0, y0, pen)
        steps = max(4, int(abs(span_deg) / 12))
        prev_x, prev_y = x0, y0
        for i in range(1, steps + 1):
            a = math.radians(start_deg + span_deg * i / steps)
            px = cx + arc_r * math.cos(a)
            py = cy + arc_r * math.sin(a)
            self._add_scene_line(prev_x, prev_y, px, py, pen)
            prev_x, prev_y = px, py

    def _circular_step_arc_anchor(self, arr, start_deg: float, step_deg: float) -> tuple[float, float]:
        arc_r = max(arr.radius, 6.0)
        bisect = math.radians(start_deg + step_deg / 2.0)
        return (
            arr.center_x + arc_r * math.cos(bisect),
            arr.center_y + arc_r * math.sin(bisect),
        )

    def _build_circular_array_step_leader(self, arr, hole, base) -> None:
        doc = self.document
        if arr.count < 2:
            return
        step_deg = doc.circular_array_step_angle(arr)
        if step_deg is None or step_deg <= 0:
            return
        start_deg = doc.circular_spoke_angle_deg(
            arr.center_x, arr.center_y, base.cx, base.cy,
        )
        arr_id = arr.id
        note_id = f"note_{arr_id}_s"
        if not self._should_show_leader(note_id, "array", arr_id):
            return
        color = hole.color
        pen = QPen(QColor(color))
        pen.setCosmetic(True)
        pen.setWidth(1)
        arc_r = max(arr.radius, 6.0)
        self._draw_circular_arc(
            arr.center_x, arr.center_y, arc_r, start_deg, step_deg, pen,
            radius_line=False,
        )
        st = doc.get_leader_state(note_id)
        f = QFont()
        f.setPointSize(st.font_size)
        ax, ay = self._circular_step_arc_anchor(arr, start_deg, step_deg)
        if st.offset_x == -50.0 and st.offset_y == -20.0:
            bisect = math.radians(start_deg + step_deg / 2.0)
            tx = arr.center_x + (arc_r + 18.0) * math.cos(bisect)
            ty = arr.center_y + (arc_r + 18.0) * math.sin(bisect)
            ox, oy = tx - ax, ty - ay
        else:
            ox, oy = st.offset_x, st.offset_y
        self._add_leader_item(
            note_id, ax, ay, f"{step_deg:.1f}°", color, f, ox, oy,
        )

    def _circular_angle_arc_radius(self, arr) -> float:
        arc_r = min(18.0, arr.radius * 0.35)
        return max(arc_r, 6.0)

    def _circular_angle_arc_anchor(self, arr, angle_deg: float) -> tuple[float, float]:
        arc_r = self._circular_angle_arc_radius(arr)
        bisect = math.radians(angle_deg / 2.0)
        return (
            arr.center_x + arc_r * math.cos(bisect),
            arr.center_y + arc_r * math.sin(bisect),
        )

    def _build_circular_array_angle_leader(self, arr, hole, base) -> None:
        doc = self.document
        angle_deg = doc.circular_spoke_angle_deg(
            arr.center_x, arr.center_y, base.cx, base.cy,
        )
        if not doc.spoke_angle_needs_annotation(angle_deg):
            return
        arr_id = arr.id
        note_id = f"note_{arr_id}_a"
        if not self._should_show_leader(note_id, "array", arr_id):
            return
        color = hole.color
        arc_r = self._circular_angle_arc_radius(arr)
        self._draw_angle_sector(arr.center_x, arr.center_y, arc_r, 0.0, angle_deg, color)
        pen = QPen(QColor(color))
        pen.setCosmetic(True)
        pen.setWidth(1)
        self._draw_circular_spoke_to_pitch(arr, angle_deg, pen)
        st = doc.get_leader_state(note_id)
        f = QFont()
        f.setPointSize(st.font_size)
        ax, ay = self._circular_angle_arc_anchor(arr, angle_deg)
        if st.offset_x == -50.0 and st.offset_y == -20.0:
            bisect = math.radians(angle_deg / 2.0)
            tx = arr.center_x + 22.0 * math.cos(bisect)
            ty = arr.center_y + 22.0 * math.sin(bisect)
            ox, oy = tx - ax, ty - ay
        else:
            ox, oy = st.offset_x, st.offset_y
        self._add_leader_item(
            note_id, ax, ay, f"{angle_deg:.1f}°", color, f, ox, oy,
        )

    def _build_circular_array_radius_leader(self, arr, hole, base) -> None:
        arr_id = arr.id
        note_id = f"note_{arr_id}_r"
        if not self._should_show_leader(note_id, "array", arr_id):
            return
        color = hole.color
        st = self.document.get_leader_state(note_id)
        f = QFont()
        f.setPointSize(st.font_size)
        if st.offset_x == -50.0 and st.offset_y == -20.0:
            ox, oy = 42.0, 28.0
        else:
            ox, oy = st.offset_x, st.offset_y
        self._add_leader_item(
            note_id, arr.center_x, arr.center_y, f"R{format_dim(arr.radius)}", color, f,
            ox, oy, radius_length=arr.radius, marker_line_width=1.0,
        )

    def _show_hole_axes(self, hole_id: str) -> bool:
        sel = self.document.selection
        if sel.kind == SelectionKind.HOLE and sel.object_id == hole_id:
            return True
        if sel.kind == SelectionKind.ARRAY:
            arr = self.document.get_array(sel.object_id)
            if arr and arr.source_hole_id == hole_id:
                return True
        return False

    def _view_scale(self) -> float:
        view = self.scene.views()[0] if self.scene.views() else None
        if view is None:
            return 1.0
        t = view.transform()
        return math.hypot(t.m11(), t.m12()) or 1.0

    def _snap_enabled(self) -> bool:
        return not bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier)

    def _snap_drag(
        self, x: float, y: float, points: list[tuple[float, float]],
        exclude_region_id: str = "",
    ) -> tuple[float, float, bool, list]:
        from app.editor.snap import snap_point_with_lines
        lines = self.document.snap_line_targets(exclude_region_id)
        return snap_point_with_lines(
            x, y, points, lines, self._view_scale(),
            enabled=self._snap_enabled(),
        )

    def _hole_dim_ids(self, hole_id: str) -> list[str]:
        return self.document.dim_ids_for_hole(hole_id)

    def _array_dim_ids(self, array_id: str) -> list[str]:
        return self.document.dim_ids_for_array(array_id)

    def _array_annotation_ids(self, array_id: str) -> list[str]:
        return self.document.annotation_ids_for_array(array_id)

    def _hole_dim_ref(self, dim_id: str, default: float) -> float:
        st = self.document.get_dim_state(dim_id)
        if st.ref_anchor is not None:
            return st.ref_anchor
        return default

    def _hole_dim_line_anchor(self, dim_id: str) -> tuple[float, float, float, float] | None:
        if dim_id in self._drag_line_anchors:
            return self._drag_line_anchors[dim_id]
        return self.document.get_dim_state(dim_id).line_anchor

    def _on_hole_drag_start(self, hole_id: str, index: int) -> None:
        """Freeze dimension reference lines at drag start so they don't follow the object."""
        self._drag_dim_refs = {}
        self._drag_line_anchors = {}
        for dim_id in self._hole_dim_ids(hole_id):
            item = self._find_dim_item(dim_id)
            if item is not None:
                if item._is_angled:
                    anchor = item.line_anchor
                    if anchor is None:
                        anchor = item.current_line_anchor()
                    self._drag_line_anchors[dim_id] = anchor
                    item.line_anchor = anchor
                else:
                    self._drag_dim_refs[dim_id] = item.ref
            else:
                st = self.document.get_dim_state(dim_id)
                if st.ref_anchor is not None:
                    self._drag_dim_refs[dim_id] = st.ref_anchor
                if st.line_anchor is not None:
                    self._drag_line_anchors[dim_id] = st.line_anchor

    def _frozen_dim_ref(self, dim_id: str, current: float) -> float:
        if dim_id in self._drag_dim_refs:
            return self._drag_dim_refs[dim_id]
        return current

    def _sync_hole_graphics(self, hole_id: str) -> None:
        hole = self.document.get_hole(hole_id)
        if hole is None:
            return
        resolved_list = self.document._resolve_single_hole(hole)
        for item in self.scene.items():
            if isinstance(item, HoleGraphicsItem) and item.source_hole_id == hole_id:
                idx = item.instance_index
                if idx < len(resolved_list):
                    rh = resolved_list[idx]
                    item.resolved.cx = rh.cx
                    item.resolved.cy = rh.cy
                    item.resolved.angle = rh.angle
                    item.prepareGeometryChange()
                    item.update()

    def _sync_circular_array_handles(self, hole_id: str) -> None:
        for item in self.scene.items():
            if isinstance(item, ArrayCenterHandle):
                arr = self.document.get_array(item.array_id)
                if arr and arr.source_hole_id == hole_id:
                    item.setPos(arr.center_x, arr.center_y)

    def _find_dim_item(self, dim_id: str) -> DimGraphicsItem | None:
        for item in self.scene.items():
            if isinstance(item, DimGraphicsItem) and item.dim_id == dim_id:
                return item
        return None

    def _find_leader_item(self, note_id: str) -> LeaderGraphicsItem | None:
        for item in self.scene.items():
            if isinstance(item, LeaderGraphicsItem) and item.note_id == note_id:
                return item
        return None

    def _grid_step_endpoints(self, hole, arr, axis: str) -> tuple[tuple[float, float], tuple[float, float]]:
        cx, cy = hole.cx, hole.cy
        if axis == "h":
            return (cx, cy), _transform_point(cx + arr.step_x, cy, cx, cy, arr.grid_angle)
        return (cx, cy), _transform_point(cx, cy + arr.step_y, cx, cy, arr.grid_angle)

    def _grid_span_endpoints(self, hole, arr, axis: str) -> tuple[tuple[float, float], tuple[float, float]]:
        cx, cy = hole.cx, hole.cy
        if axis == "h":
            n = max(0, arr.count_x - 1)
            return (cx, cy), _transform_point(cx + n * arr.step_x, cy, cx, cy, arr.grid_angle)
        n = max(0, arr.count_y - 1)
        return (cx, cy), _transform_point(cx, cy + n * arr.step_y, cx, cy, arr.grid_angle)

    def _collect_dim_snap_targets(self, exclude_id: str, orientation: str) -> list[float]:
        """Collect shelf positions (line_pos) for snap alignment."""
        targets: list[float] = []
        for item in self.scene.items():
            if not isinstance(item, DimGraphicsItem) or item.dim_id == exclude_id:
                continue
            if orientation == "h":
                if item.side in ("top", "bottom"):
                    targets.append(item._shelf_pos())
            elif orientation == "v":
                if item.side in ("left", "right"):
                    targets.append(item._shelf_pos())
        return targets

    def _dim_snap_fn(self, dim_id: str, side: str, angled: bool):
        orient = "h" if side in ("top", "bottom") else "v"
        return lambda: self._collect_dim_snap_targets(dim_id, orient)

    def _update_dim_live(
        self, dim_id: str, owner_kind: str, owner_id: str, a1: float, a2: float, ref: float, text: str,
        ext1: float | None = None, ext2: float | None = None,
        pt1: tuple[float, float] | None = None, pt2: tuple[float, float] | None = None,
    ) -> None:
        if not self._should_show_dim(dim_id, owner_kind, owner_id):
            return
        item = self._find_dim_item(dim_id)
        if item is not None:
            item.update_geometry(a1, a2, ref, text, ext1, ext2, pt1, pt2)

    def _sync_circular_array_dims(self, arr_id: str) -> None:
        arr = self.document.get_array(arr_id)
        if arr is None or arr.kind != ArrayKind.CIRCULAR:
            return
        hole = self.document.get_hole(arr.source_hole_id)
        if hole is None:
            return
        resolved = self.document._resolve_single_hole(hole)
        if not resolved:
            return
        base = resolved[0]
        doc = self.document
        ccx, ccy = doc.contour_center()
        cx_id, cy_id = f"{arr_id}_cx", f"{arr_id}_cy"
        if doc.contour_kind == ContourKind.CIRCLE:
            self._update_dim_live(
                cx_id, "array", arr_id, ccx, arr.center_x,
                self._frozen_dim_ref(cx_id, arr.center_y),
                format_dim(arr.center_x - ccx),
                ext1=ccy, ext2=arr.center_y,
            )
            self._update_dim_live(
                cy_id, "array", arr_id, ccy, arr.center_y,
                self._frozen_dim_ref(cy_id, arr.center_x),
                format_dim(arr.center_y - ccy),
                ext1=ccx, ext2=arr.center_x,
            )
        else:
            self._update_dim_live(
                cx_id, "array", arr_id, 0, arr.center_x,
                self._frozen_dim_ref(cx_id, arr.center_y),
                format_dim(arr.center_x),
                ext1=0.0, ext2=arr.center_y,
            )
            self._update_dim_live(
                cy_id, "array", arr_id, 0, arr.center_y,
                self._frozen_dim_ref(cy_id, arr.center_x),
                format_dim(arr.center_y),
                ext1=0.0, ext2=arr.center_x,
            )
        note_id = f"note_{arr_id}_r"
        leader = self._find_leader_item(note_id)
        if leader is not None:
            leader.update_anchor(arr.center_x, arr.center_y)
            leader.update_text(f"R{format_dim(arr.radius)}")
            leader.update_radius_length(arr.radius)
        angle_deg = doc.circular_spoke_angle_deg(
            arr.center_x, arr.center_y, base.cx, base.cy,
        )
        note_a = f"note_{arr_id}_a"
        leader_a = self._find_leader_item(note_a)
        if leader_a is not None:
            ax, ay = self._circular_angle_arc_anchor(arr, angle_deg)
            leader_a.update_anchor(ax, ay)
            leader_a.update_text(f"{angle_deg:.1f}°")
        step_deg = doc.circular_array_step_angle(arr)
        note_s = f"note_{arr_id}_s"
        leader_s = self._find_leader_item(note_s)
        if leader_s is not None and step_deg is not None:
            ax, ay = self._circular_step_arc_anchor(arr, angle_deg, step_deg)
            leader_s.update_anchor(ax, ay)
            leader_s.update_text(f"{step_deg:.1f}°")

    def _sync_live_dimensions(self, hole_id: str) -> None:
        """Update dimension span/text during drag; dim-line position stays frozen."""
        hole = self.document.get_hole(hole_id)
        if hole is None:
            return
        doc = self.document
        p = hole.id
        ccx, ccy = doc.contour_center()
        ox_id, oy_id = f"{p}_ox", f"{p}_oy"
        if hole.kind != HoleKind.OVAL:
            if doc.contour_kind == ContourKind.CIRCLE:
                self._update_dim_live(
                    ox_id, "hole", p, ccx, hole.cx,
                    self._frozen_dim_ref(ox_id, hole.cy),
                    format_dim(hole.cx - ccx),
                    ext1=ccy, ext2=hole.cy,
                )
                self._update_dim_live(
                    oy_id, "hole", p, ccy, hole.cy,
                    self._frozen_dim_ref(oy_id, hole.cx),
                    format_dim(hole.cy - ccy),
                    ext1=ccx, ext2=hole.cx,
                )
            else:
                self._update_dim_live(
                    ox_id, "hole", p, 0, hole.cx,
                    self._frozen_dim_ref(ox_id, hole.cy),
                    format_dim(hole.cx),
                    ext1=0.0, ext2=hole.cy,
                )
                self._update_dim_live(
                    oy_id, "hole", p, 0, hole.cy,
                    self._frozen_dim_ref(oy_id, hole.cx),
                    format_dim(hole.cy),
                    ext1=0.0, ext2=hole.cx,
                )
        for arr in doc.arrays_for_hole(hole.id):
            if arr.kind == ArrayKind.GRID and arr.count_x > 1:
                gh_id = f"{arr.id}_gh"
                gp1, gp2 = self._grid_step_endpoints(hole, arr, "h")
                self._update_dim_live(
                    gh_id, "array", arr.id, hole.cx, hole.cx + arr.step_x,
                    self._frozen_dim_ref(gh_id, hole.cy),
                    format_dim(arr.step_x),
                    pt1=gp1, pt2=gp2,
                )
                glx_id = f"{arr.id}_glx"
                sp1, sp2 = self._grid_span_endpoints(hole, arr, "h")
                span_x = self.document.grid_array_span_x(arr)
                self._update_dim_live(
                    glx_id, "array", arr.id, hole.cx, hole.cx + span_x,
                    self._frozen_dim_ref(glx_id, hole.cy),
                    format_dim(span_x),
                    pt1=sp1, pt2=sp2,
                )
            if arr.kind == ArrayKind.GRID and arr.count_y > 1:
                gv_id = f"{arr.id}_gv"
                gp1, gp2 = self._grid_step_endpoints(hole, arr, "v")
                self._update_dim_live(
                    gv_id, "array", arr.id, hole.cy, hole.cy + arr.step_y,
                    self._frozen_dim_ref(gv_id, hole.cx),
                    format_dim(arr.step_y),
                    pt1=gp1, pt2=gp2,
                )
                gly_id = f"{arr.id}_gly"
                sp1, sp2 = self._grid_span_endpoints(hole, arr, "v")
                span_y = self.document.grid_array_span_y(arr)
                self._update_dim_live(
                    gly_id, "array", arr.id, hole.cy, hole.cy + span_y,
                    self._frozen_dim_ref(gly_id, hole.cx),
                    format_dim(span_y),
                    pt1=sp1, pt2=sp2,
                )
            if arr.kind == ArrayKind.CIRCULAR:
                self._sync_circular_array_dims(arr.id)

    def _sync_live_leaders(self, hole_id: str) -> None:
        hole = self.document.get_hole(hole_id)
        if hole is None:
            return
        doc = self.document
        note_id = f"note_{hole_id}"
        leader = self._find_leader_item(note_id)
        if leader is not None and hole.kind in (HoleKind.RECT, HoleKind.OVAL):
            leader.update_anchor(hole.cx, hole.cy)
            leader.update_text(f"{format_dim(hole.width)}x{format_dim(hole.height)}")
        note_d = f"note_{hole_id}_d"
        leader_d = self._find_leader_item(note_d)
        if leader_d is not None and hole.kind in (HoleKind.CIRCLE, HoleKind.POLYGON):
            leader_d.update_anchor(hole.cx, hole.cy)
            d = doc.hole_display_diameter(hole)
            label = f"Ø{format_dim(d)}"
            if hole.kind == HoleKind.POLYGON:
                label = f"Ø{format_dim(d)} /{hole.sides}"
            leader_d.update_text(label)
        if hole.kind != HoleKind.CIRCLE:
            angle_deg = hole.angle % 360.0
            if doc.spoke_angle_needs_annotation(angle_deg):
                note_a = f"note_{hole_id}_ang"
                leader_a = self._find_leader_item(note_a)
                if leader_a is not None:
                    ax, ay = self._hole_angle_arc_anchor(hole, angle_deg)
                    leader_a.update_anchor(ax, ay)

    def _guide_bounds(self) -> QRectF:
        _, _, w, h = self.document.contour_bounds()
        pad = 40
        return QRectF(-pad, -pad, w + 2 * pad, h + 2 * pad)

    def _show_snap_guides(self, guides) -> None:
        if guides:
            self._guide_item.set_guides(guides, self._guide_bounds())
        else:
            self._guide_item.clear()

    def _on_hole_move(self, hole_id: str, index: int, x: float, y: float) -> tuple[float, float]:
        others = self.document.snap_points_for_drag(hole_id, index)
        sx, sy, _, guides = self._snap_drag(x, y, others)
        self._show_snap_guides(guides)
        if index == 0:
            self.document.move_primary_hole(hole_id, sx, sy)
        else:
            found = self.document.find_array_for_instance(hole_id, index)
            if found:
                arr, local_idx = found
                if arr.kind == ArrayKind.GRID:
                    self.document.move_grid_instance(hole_id, arr, local_idx, sx, sy)
                elif arr.kind == ArrayKind.MIRROR:
                    self.document.move_mirror_instance(hole_id, index, sx, sy)
                else:
                    resolved = self.document._resolve_single_hole(self.document.get_hole(hole_id))
                    if index < len(resolved):
                        return resolved[index].cx, resolved[index].cy
                    return sx, sy
        self._sync_hole_graphics(hole_id)
        self._sync_circular_array_handles(hole_id)
        self._sync_live_dimensions(hole_id)
        self._sync_live_leaders(hole_id)
        resolved = self.document._resolve_single_hole(self.document.get_hole(hole_id))
        if index < len(resolved):
            return resolved[index].cx, resolved[index].cy
        return sx, sy

    def _on_hole_move_end(self, hole_id: str, index: int, x: float, y: float):
        self._on_hole_move(hole_id, index, x, y)
        for dim_id, ref in self._drag_dim_refs.items():
            self.document.get_dim_state(dim_id).ref_anchor = ref
        for dim_id, anchor in self._drag_line_anchors.items():
            self.document.get_dim_state(dim_id).line_anchor = anchor
        self._drag_dim_refs = {}
        self._drag_line_anchors = {}
        self._guide_item.clear()
        self.document.notify()

    def _on_array_center_drag_start(self, array_id: str) -> None:
        self._drag_dim_refs = {}
        self._drag_line_anchors = {}
        for dim_id in self._array_dim_ids(array_id):
            item = self._find_dim_item(dim_id)
            if item is not None:
                if item._is_angled:
                    anchor = item.line_anchor
                    if anchor is None:
                        anchor = item.current_line_anchor()
                    self._drag_line_anchors[dim_id] = anchor
                    item.line_anchor = anchor
                else:
                    self._drag_dim_refs[dim_id] = item.ref
            else:
                st = self.document.get_dim_state(dim_id)
                if st.ref_anchor is not None:
                    self._drag_dim_refs[dim_id] = st.ref_anchor
                if st.line_anchor is not None:
                    self._drag_line_anchors[dim_id] = st.line_anchor

    def _on_array_center_move(self, array_id: str, x: float, y: float) -> tuple[float, float]:
        arr = self.document.get_array(array_id)
        if arr is None:
            return x, y
        others = self.document.snap_points_for_array_center_drag(array_id)
        sx, sy, _, guides = self._snap_drag(x, y, others)
        self._show_snap_guides(guides)
        arr.center_x, arr.center_y = sx, sy
        self.document.sync_circular_array_radius(arr)
        self._sync_hole_graphics(arr.source_hole_id)
        self._sync_circular_array_dims(array_id)
        return sx, sy

    def _on_array_center_move_end(self, array_id: str, x: float, y: float):
        sx, sy = self._on_array_center_move(array_id, x, y)
        for item in self.scene.items():
            if isinstance(item, ArrayCenterHandle) and item.array_id == array_id:
                item.setPos(sx, sy)
                break
        for dim_id, ref in self._drag_dim_refs.items():
            self.document.get_dim_state(dim_id).ref_anchor = ref
        for dim_id, anchor in self._drag_line_anchors.items():
            self.document.get_dim_state(dim_id).line_anchor = anchor
        self._drag_dim_refs = {}
        self._drag_line_anchors = {}
        self._guide_item.clear()
        self.document.notify()

    def _on_dim_offset(self, dim_id: str, offset: float):
        if self.document.is_annotation_locked(dim_id):
            return
        st = self.document.get_dim_state(dim_id)
        st.offset = offset
        item = self._find_dim_item(dim_id)
        if item is not None:
            st.side = item.side

    def _on_dim_offset_end(self, dim_id: str, offset: float):
        if self.document.is_annotation_locked(dim_id):
            return
        self._on_dim_offset(dim_id, offset)
        item = self._find_dim_item(dim_id)
        if item is not None:
            st = self.document.get_dim_state(dim_id)
            st.side = item.side
            if item._is_angled:
                st.line_anchor = item.current_line_anchor()
        self.document.notify()

    def _on_leader_move(self, note_id: str, ox: float, oy: float):
        if self.document.is_annotation_locked(note_id):
            return
        st = self.document.get_leader_state(note_id)
        st.offset_x, st.offset_y = ox, oy

    def _on_leader_move_end(self, note_id: str, ox: float, oy: float):
        self._on_leader_move(note_id, ox, oy)
        self.document.notify()

    def _font(self, dim_id: str) -> QFont:
        st = self.document.get_dim_state(dim_id)
        f = QFont()
        f.setPointSize(st.font_size)
        return f

    def _lane_offset(self, side: str, dim_id: str) -> float:
        st = self.document.get_dim_state(dim_id)
        if st.offset != DIM_EXT:
            return st.offset
        lane = self._lane_counters.get(side, 0)
        self._lane_counters[side] = lane + 1
        return DIM_EXT + lane * DIM_STEP

    def _should_show_dim(self, dim_id: str, owner_kind: str, owner_id: str = "") -> bool:
        if self.document.is_zero_dimension(dim_id):
            return False
        st = self.document.get_dim_state(dim_id)
        if st.always_show:
            return True
        doc = self.document
        sel = doc.selection
        if sel.kind == SelectionKind.DIMENSION and sel.object_id == dim_id:
            return True
        if owner_kind == "contour":
            if sel.kind == SelectionKind.CONTOUR:
                return True
            return False
        if owner_kind == "hole":
            if sel.kind == SelectionKind.HOLE and sel.object_id == owner_id:
                return True
            return False
        if owner_kind == "array":
            arr = doc.get_array(owner_id)
            if arr is None:
                return False
            if sel.kind == SelectionKind.ARRAY and sel.object_id == owner_id:
                return True
            return False
        if owner_kind == "measure":
            if sel.kind == SelectionKind.MEASURE and sel.object_id == owner_id:
                return True
            return False
        if owner_kind == "shutter":
            if sel.kind == SelectionKind.SHUTTER and sel.object_id == owner_id:
                return True
            return False
        if owner_kind == "infinite_line":
            if sel.kind == SelectionKind.INFINITE_LINE and sel.object_id == owner_id:
                return True
            st_obj = doc.get_object_state("infinite_line", owner_id)
            return st_obj.show_dims
        if owner_kind == "drawn_rect":
            if sel.kind == SelectionKind.DRAWN_RECT and sel.object_id == owner_id:
                return True
            return False
        return False

    def _should_show_leader(self, note_id: str, owner_kind: str, owner_id: str = "") -> bool:
        if self.document.is_zero_dimension(note_id):
            return False
        st = self.document.get_leader_state(note_id)
        if st.always_show:
            return True
        doc = self.document
        sel = doc.selection
        if sel.kind == SelectionKind.DIMENSION and sel.object_id == note_id:
            return True
        if owner_kind == "contour":
            if sel.kind == SelectionKind.CONTOUR:
                return True
            return False
        if owner_kind == "hole":
            if sel.kind == SelectionKind.HOLE and sel.object_id == owner_id:
                return True
            return False
        if owner_kind == "array":
            arr = doc.get_array(owner_id)
            if arr is None:
                return False
            if sel.kind == SelectionKind.ARRAY and sel.object_id == owner_id:
                return True
            return False
        if owner_kind == "measure":
            if sel.kind == SelectionKind.MEASURE and sel.object_id == owner_id:
                return True
            st_obj = doc.get_object_state("measure", owner_id)
            return st_obj.show_dims
        return False

    def _add_dim(self, dim_id, side, a1, a2, ref, text, color, owner_kind="contour", owner_id="",
                 ext1=None, ext2=None, pt1=None, pt2=None):
        if not self._should_show_dim(dim_id, owner_kind, owner_id):
            return
        st = self.document.get_dim_state(dim_id)
        actual_side = st.side or side
        off = self._lane_offset(actual_side, dim_id) if st.offset == DIM_EXT else st.offset
        angled = pt1 is not None and pt2 is not None
        line_anchor = self._hole_dim_line_anchor(dim_id) if angled else None
        color, selected = self._resolve_annotation_color(dim_id, color)
        self.scene.addItem(DimGraphicsItem(
            dim_id, actual_side, a1, a2, ref, text, color, self._font(dim_id), off, [],
            self._on_select, self._on_dim_offset, self._on_dim_offset_end,
            ext1=ext1, ext2=ext2, pt1=pt1, pt2=pt2, line_anchor=line_anchor,
            get_snap_targets=self._dim_snap_fn(dim_id, actual_side, angled),
            on_edit=self.on_edit_dimension,
            selected=selected,
            selection_color=self.colors["selection"].name(),
            locked=self.document.is_annotation_locked(dim_id),
        ))
        self._built_offsets.setdefault(actual_side, []).append(off)

    def _build_contour_dims(self):
        doc = self.document
        if doc.contour_kind != ContourKind.RECT:
            return
        dim_color = self.colors["contour_dim"].name()
        r = doc.rect
        self._add_dim("w_all", "bottom", 0, r.width, r.height, format_dim(r.width), dim_color)
        self._add_dim("h_all", "right", 0, r.height, r.width, format_dim(r.height), dim_color)

    def _on_origin_select(self, notify: bool = True) -> None:
        self.document.select(SelectionKind.ORIGIN, notify=notify)

    def start_origin_placement(self) -> None:
        self.cancel_hole_place()
        self.cancel_array_place()
        self.origin_placement_mode = True
        for item in list(self.scene.items()):
            if isinstance(item, OriginHandle):
                self.scene.removeItem(item)
        self._sync_origin_placement_marker()

    def cancel_origin_placement(self) -> None:
        self.origin_placement_mode = False
        self._hide_origin_placement_marker()
        self._guide_item.clear()

    def _hide_origin_placement_marker(self) -> None:
        if self._origin_placement_marker is not None:
            self._origin_placement_marker.setVisible(False)

    def _sync_origin_placement_marker(self) -> None:
        if self._origin_placement_marker is None:
            self._origin_placement_marker = PlacementCrosshairItem()
            self.scene.addItem(self._origin_placement_marker)
        self._origin_placement_marker.setVisible(self.origin_placement_mode)

    def update_origin_placement_cursor(self, x: float, y: float) -> None:
        if not self.origin_placement_mode:
            return
        self._sync_origin_placement_marker()
        self._origin_placement_marker.setPos(x, y)
        self._origin_placement_marker.setVisible(True)

    def snap_origin_point(self, x: float, y: float, view_scale: float) -> tuple[float, float, bool]:
        from app.editor.snap import snap_point
        points = self.document.dxf_snap_points()
        nx, ny, snapped, guides = snap_point(
            x, y, points, view_scale, enabled=self._snap_enabled(), half_grid=False,
        )
        self._guide_item.set_guides(guides, self._guide_bounds())
        return nx, ny, snapped

    def click_origin_point(self, x: float, y: float) -> tuple[bool, float, float]:
        if not self.origin_placement_mode:
            return False, x, y
        self.origin_placement_mode = False
        self._hide_origin_placement_marker()
        self._guide_item.clear()
        return True, x, y

    def _build_contour_diameter_leader(self) -> None:
        doc = self.document
        if doc.contour_kind != ContourKind.CIRCLE:
            return
        note_id = "note_contour_d"
        if not self._should_show_leader(note_id, "contour"):
            return
        d = doc.circle.diameter
        r = d / 2.0
        cx, cy = r, r
        color = self.colors["contour_dim"].name()
        st = doc.get_leader_state(note_id)
        f = QFont()
        f.setPointSize(st.font_size)
        if st.offset_x == -50.0 and st.offset_y == -20.0:
            mx = (cx + d) / 2.0
            ox = mx - cx - 50.0
            oy = -20.0
        else:
            ox, oy = st.offset_x, st.offset_y
        self._add_leader_item(
            note_id, cx, cy, f"Ø{format_dim(d)}", color, f, ox, oy,
            diameter_radius=r, marker_line_width=self._circle_marker_line_width(contour=True),
        )

    def _build_contour_leader(self):
        """Сноска фаски/скругления контура (если есть)."""
        from app.models.base import CornerMode
        doc = self.document
        if doc.contour_kind != ContourKind.RECT:
            return
        r = doc.rect
        if r.corner_size <= 0:
            return
        note_id = "note_contour_corner"
        if not self._should_show_leader(note_id, "contour"):
            return
        st = self.document.get_leader_state(note_id)
        if r.corner_mode == CornerMode.RADIUS:
            text = f"R{format_dim(r.corner_size)}"
        else:
            text = f"C{format_dim(r.corner_size)}"
        # Анкер в верхнем правом углу контура.
        ax, ay = r.width, 0.0
        f = QFont()
        f.setPointSize(st.font_size)
        color = self.colors["contour_dim"].name()
        self._add_leader_item(
            note_id, ax, ay, text, color, f, st.offset_x, st.offset_y,
        )

    def _hole_angle_arc_radius(self, hole) -> float:
        return max(6.0, min(16.0, min(hole.width, hole.height) * 0.45))

    def _hole_angle_arc_anchor(self, hole, angle_deg: float) -> tuple[float, float]:
        arc_r = self._hole_angle_arc_radius(hole)
        bisect = math.radians(angle_deg / 2.0)
        return (
            hole.cx + arc_r * math.cos(bisect),
            hole.cy + arc_r * math.sin(bisect),
        )

    def _build_hole_angle_leader(self, hole) -> None:
        if hole.kind == HoleKind.CIRCLE:
            return
        angle_deg = hole.angle % 360.0
        if not self.document.spoke_angle_needs_annotation(angle_deg):
            return
        note_id = f"note_{hole.id}_ang"
        if not self._should_show_leader(note_id, "hole", hole.id):
            return
        color = hole.color
        arc_r = self._hole_angle_arc_radius(hole)
        self._draw_angle_sector(hole.cx, hole.cy, arc_r, 0.0, angle_deg, color)
        st = self.document.get_leader_state(note_id)
        f = QFont()
        f.setPointSize(st.font_size)
        ax, ay = self._hole_angle_arc_anchor(hole, angle_deg)
        if st.offset_x == -50.0 and st.offset_y == -20.0:
            bisect = math.radians(angle_deg / 2.0)
            tx = hole.cx + 20.0 * math.cos(bisect)
            ty = hole.cy + 20.0 * math.sin(bisect)
            ox, oy = tx - ax, ty - ay
        else:
            ox, oy = st.offset_x, st.offset_y
        self._add_leader_item(
            note_id, ax, ay, f"{angle_deg:.1f}°", color, f, ox, oy,
        )

    def _build_hole_dims(self, hole):
        doc = self.document
        color = hole.color
        p = hole.id
        ccx, ccy = doc.contour_center()
        ox_id, oy_id = f"{p}_ox", f"{p}_oy"
        if hole.kind != HoleKind.OVAL:
            if doc.contour_kind == ContourKind.CIRCLE:
                self._add_dim(
                    ox_id, "top", ccx, hole.cx,
                    self._hole_dim_ref(ox_id, hole.cy),
                    format_dim(hole.cx - ccx), color, "hole", p,
                    ext1=ccy, ext2=hole.cy,
                )
                self._add_dim(
                    oy_id, "left", ccy, hole.cy,
                    self._hole_dim_ref(oy_id, hole.cx),
                    format_dim(hole.cy - ccy), color, "hole", p,
                    ext1=ccx, ext2=hole.cx,
                )
            else:
                self._add_dim(
                    ox_id, "top", 0, hole.cx,
                    self._hole_dim_ref(ox_id, hole.cy),
                    format_dim(hole.cx), color, "hole", p,
                    ext1=0.0, ext2=hole.cy,
                )
                self._add_dim(
                    oy_id, "left", 0, hole.cy,
                    self._hole_dim_ref(oy_id, hole.cx),
                    format_dim(hole.cy), color, "hole", p,
                    ext1=0.0, ext2=hole.cx,
                )
        for arr in doc.arrays_for_hole(hole.id):
            if arr.kind == ArrayKind.GRID and arr.count_x > 1:
                gh_id = f"{arr.id}_gh"
                gp1, gp2 = self._grid_step_endpoints(hole, arr, "h")
                self._add_dim(
                    gh_id, "top", hole.cx, hole.cx + arr.step_x,
                    self._hole_dim_ref(gh_id, hole.cy),
                    format_dim(arr.step_x), color, "array", arr.id,
                    pt1=gp1, pt2=gp2,
                )
                glx_id = f"{arr.id}_glx"
                sp1, sp2 = self._grid_span_endpoints(hole, arr, "h")
                span_x = doc.grid_array_span_x(arr)
                self._add_dim(
                    glx_id, "bottom", hole.cx, hole.cx + span_x,
                    self._hole_dim_ref(glx_id, hole.cy),
                    format_dim(span_x), color, "array", arr.id,
                    pt1=sp1, pt2=sp2,
                )
            if arr.kind == ArrayKind.GRID and arr.count_y > 1:
                gv_id = f"{arr.id}_gv"
                gp1, gp2 = self._grid_step_endpoints(hole, arr, "v")
                self._add_dim(
                    gv_id, "left", hole.cy, hole.cy + arr.step_y,
                    self._hole_dim_ref(gv_id, hole.cx),
                    format_dim(arr.step_y), color, "array", arr.id,
                    pt1=gp1, pt2=gp2,
                )
                gly_id = f"{arr.id}_gly"
                sp1, sp2 = self._grid_span_endpoints(hole, arr, "v")
                span_y = doc.grid_array_span_y(arr)
                self._add_dim(
                    gly_id, "right", hole.cy, hole.cy + span_y,
                    self._hole_dim_ref(gly_id, hole.cx),
                    format_dim(span_y), color, "array", arr.id,
                    pt1=sp1, pt2=sp2,
                )

    def _build_hole_slot_guides(self, hole) -> None:
        if hole.kind != HoleKind.OVAL or hole.width < 1e-9:
            return
        pen = QPen(QColor("#707070"))
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        pen.setWidth(1)
        horiz, vert_left, vert_right = slot_center_axes_world(
            hole.cx, hole.cy, hole.width, hole.height, hole.angle,
        )
        self._add_scene_line(horiz[0][0], horiz[0][1], horiz[1][0], horiz[1][1], pen)
        self._add_scene_line(vert_left[0][0], vert_left[0][1], vert_left[1][0], vert_left[1][1], pen)
        self._add_scene_line(vert_right[0][0], vert_right[0][1], vert_right[1][0], vert_right[1][1], pen)

    def _build_hole_leader(self, hole):
        note_id = f"note_{hole.id}"
        if hole.kind not in (HoleKind.RECT, HoleKind.OVAL):
            return
        if not self._should_show_leader(note_id, "hole", hole.id):
            return
        st = self.document.get_leader_state(note_id)
        if hole.kind == HoleKind.OVAL:
            text = f"{format_dim(hole.width)}x{format_dim(hole.height)}"
        else:
            text = f"{format_dim(hole.width)}x{format_dim(hole.height)}"
        f = QFont()
        f.setPointSize(st.font_size)
        self._add_leader_item(
            note_id, hole.cx, hole.cy, text, hole.color, f,
            st.offset_x, st.offset_y,
        )

    def _should_show_hole_reference_circle(self, hole_id: str) -> bool:
        hole = self.document.get_hole(hole_id)
        if hole is None or hole.kind not in (HoleKind.CIRCLE, HoleKind.POLYGON):
            return False
        note_id = f"note_{hole_id}_d"
        if self.document.get_leader_state(note_id).always_show:
            return True
        sel = self.document.selection
        if sel.kind == SelectionKind.DIMENSION and sel.object_id == note_id:
            return True
        if sel.kind == SelectionKind.HOLE and sel.object_id == hole_id:
            return True
        return False

    def _draw_hole_reference_circle(self, hole) -> None:
        if hole.kind != HoleKind.POLYGON:
            return
        if not self._should_show_hole_reference_circle(hole.id):
            return
        r = polygon_inscribed_radius(hole.diameter)
        pen = QPen(QColor(hole.color))
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        pen.setWidth(1)
        item = QGraphicsEllipseItem(
            hole.cx - r, hole.cy - r, r * 2, r * 2,
        )
        item.setPen(pen)
        item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        item.setZValue(3)
        self.scene.addItem(item)

    def _build_hole_diameter_leader(self, hole) -> None:
        if hole.kind not in (HoleKind.CIRCLE, HoleKind.POLYGON):
            return
        self._draw_hole_reference_circle(hole)
        note_id = f"note_{hole.id}_d"
        if not self._should_show_leader(note_id, "hole", hole.id):
            return
        d = self.document.hole_display_diameter(hole)
        r = d / 2.0
        color = hole.color
        st = self.document.get_leader_state(note_id)
        f = QFont()
        f.setPointSize(st.font_size)
        if st.offset_x == -50.0 and st.offset_y == -20.0:
            ox, oy = 42.0, -20.0
        else:
            ox, oy = st.offset_x, st.offset_y
        label = f"Ø{format_dim(d)}"
        if hole.kind == HoleKind.POLYGON:
            label = f"Ø{format_dim(d)} /{hole.sides}"
        self._add_leader_item(
            note_id, hole.cx, hole.cy, label, color, f,
            ox, oy, diameter_radius=r,
            marker_line_width=self._circle_marker_line_width(hole_id=hole.id),
        )

    def nudge_selection(self, dx: float, dy: float) -> bool:
        from app.editor.snap import snap_point
        sel = self.document.selection
        if sel.kind == SelectionKind.NONE:
            return False
        if sel.kind == SelectionKind.ORIGIN:
            return False
        if sel.kind == SelectionKind.INFINITE_LINE:
            line = self.document.get_infinite_line(sel.object_id)
            if line is None or line.locked:
                return False
            self.document.move_infinite_line(line.id, dx, dy)
            self.document.notify()
            return True
        if sel.kind == SelectionKind.SHUTTER:
            s = self.document.get_shutter(sel.object_id)
            if s is None:
                return False
            sx, sy, _, _ = self._snap_drag(
                s.cx + dx, s.cy + dy,
                self.document.snap_points_for_shutter_drag(s.id), s.id,
            )
            self.document.move_shutter(s.id, sx, sy)
            self.document.notify()
            return True
        if sel.kind == SelectionKind.DRAWN_RECT:
            r = self.document.get_drawn_rect(sel.object_id)
            if r is None:
                return False
            sx, sy, _, _ = self._snap_drag(
                r.cx + dx, r.cy + dy,
                self.document.snap_points_for_drawn_rect_drag(r.id), r.id,
            )
            self.document.move_drawn_rect(r.id, sx, sy)
            self.document.notify()
            return True
        if sel.kind == SelectionKind.HOLE:
            hole = self.document.get_hole(sel.object_id)
            if hole is None:
                return False
            sx, sy, _, _ = snap_point(
                hole.cx + dx, hole.cy + dy,
                self.document.snap_points_for_drag(hole.id, 0),
                self._view_scale(), 12.0,
                enabled=self._snap_enabled(),
            )
            self.document.move_primary_hole(hole.id, sx, sy)
            self.document.notify()
            return True
        if sel.kind == SelectionKind.ARRAY:
            arr = self.document.get_array(sel.object_id)
            if arr is None:
                return False
            hole_id = arr.source_hole_id
            hole = self.document.get_hole(hole_id)
            if hole is None:
                return False
            if arr.kind == ArrayKind.CIRCULAR:
                sx, sy, _, _ = snap_point(
                    arr.center_x + dx, arr.center_y + dy,
                    self.document.snap_points_for_array_center_drag(arr.id),
                    self._view_scale(), 12.0,
                    enabled=self._snap_enabled(),
                )
                arr.center_x, arr.center_y = sx, sy
                self.document.sync_circular_array_radius(arr)
                self.document.notify()
                return True
            if sel.instance_index <= 0:
                return False
            resolved = self.document._resolve_single_hole(hole)
            if sel.instance_index >= len(resolved):
                return False
            rh = resolved[sel.instance_index]
            sx, sy, _, _ = snap_point(
                rh.cx + dx, rh.cy + dy,
                self.document.snap_points_for_drag(hole_id, sel.instance_index),
                self._view_scale(), 12.0,
                enabled=self._snap_enabled(),
            )
            found = self.document.find_array_for_instance(hole_id, sel.instance_index)
            if not found:
                return False
            arr, local_idx = found
            if arr.kind == ArrayKind.GRID:
                self.document.move_grid_instance(hole_id, arr, local_idx, sx, sy)
            elif arr.kind == ArrayKind.MIRROR:
                return False
            self.document.notify()
            return True
        if sel.kind == SelectionKind.DIMENSION:
            dim_id = sel.object_id
            if self.document.is_annotation_locked(dim_id):
                return False
            if dim_id.startswith("note_"):
                st = self.document.get_leader_state(dim_id)
                st.offset_x += dx
                st.offset_y += dy
            else:
                st = self.document.get_dim_state(dim_id)
                side = self._dim_side(dim_id)
                if side in ("bottom", "right"):
                    st.offset = max(3.0, st.offset + (dy if side == "bottom" else dx))
                else:
                    st.offset = max(3.0, st.offset - (dy if side == "top" else dx))
            self.document.notify()
            return True
        return False

    def _dim_side(self, dim_id: str) -> str:
        st = self.document.get_dim_state(dim_id)
        if st.side:
            return st.side
        if dim_id in ("w_all",):
            return "bottom"
        if dim_id in ("h_all",):
            return "right"
        if dim_id.endswith("_h"):
            return "bottom"
        if dim_id.endswith("_v"):
            return "right"
        if dim_id.endswith("_d") and self.document.get_measure(dim_id[:-2]) is not None:
            return "bottom"
        if dim_id.endswith("_glx"):
            return "bottom"
        if dim_id.endswith("_gly"):
            return "right"
        if dim_id.endswith("_ox") or dim_id.endswith("_gh") or dim_id.endswith("_cx"):
            return "top"
        if dim_id.endswith("_left") or dim_id.endswith("_top"):
            return "left" if dim_id.endswith("_top") else "top"
        if dim_id.endswith("_right"):
            return "top"
        if dim_id.endswith("_bottom"):
            return "left"
        if dim_id.endswith("_rw"):
            return "bottom"
        if dim_id.endswith("_rh"):
            return "right"
        return "left"

    def _build_measure_dims(self, m) -> None:
        p1 = (m.p1x, m.p1y)
        p2 = (m.p2x, m.p2y)
        color = self.colors["dim"].name()
        mid = m.id
        if m.kind == "diameter":
            note_id = f"note_{mid}_d"
            if not self._should_show_leader(note_id, "measure", mid):
                return
            st = self.document.get_leader_state(note_id)
            f = QFont()
            f.setPointSize(st.font_size)
            ox, oy = self._leader_offset_from_points(p1, p2, st)
            self._add_leader_item(
                note_id, p1[0], p1[1], f"Ø{format_dim(m.size)}", color, f, ox, oy,
                diameter_radius=m.size / 2,
                marker_line_width=self._circle_marker_line_width(),
            )
            return
        if m.kind == "radius":
            note_id = f"note_{mid}_r"
            if not self._should_show_leader(note_id, "measure", mid):
                return
            st = self.document.get_leader_state(note_id)
            f = QFont()
            f.setPointSize(st.font_size)
            ox, oy = self._leader_offset_from_points(p1, p2, st)
            self._add_leader_item(
                note_id, p1[0], p1[1], f"R{format_dim(m.size)}", color, f, ox, oy,
                radius_length=m.size,
                marker_line_width=self._circle_marker_line_width(),
            )
            return
        hx = abs(p2[0] - p1[0])
        hy = abs(p2[1] - p1[1])
        dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        y_ref = min(p1[1], p2[1])
        x_ref = max(p1[0], p2[0])
        if hx > 1e-9:
            self._add_dim(
                f"{mid}_h", "bottom", min(p1[0], p2[0]), max(p1[0], p2[0]), y_ref,
                format_dim(hx), color, "measure", mid,
                ext1=p1[1], ext2=p2[1],
            )
        if hy > 1e-9:
            self._add_dim(
                f"{mid}_v", "right", min(p1[1], p2[1]), max(p1[1], p2[1]), x_ref,
                format_dim(hy), color, "measure", mid,
                ext1=p1[0], ext2=p2[0],
            )
        if self.document.measure_needs_angled_dim(m):
            self._add_dim(
                f"{mid}_d", "bottom", 0.0, dist, y_ref,
                format_dim(dist), color, "measure", mid,
                pt1=p1, pt2=p2,
            )

    def _clear_measure_preview(self) -> None:
        if self._measure_preview_leader is not None:
            self.scene.removeItem(self._measure_preview_leader)
            self._measure_preview_leader = None

    def _update_measure_leader_preview(self, x: float, y: float) -> None:
        if not self.measure_leader_placement or self.measure_p1 is None:
            self._clear_measure_preview()
            return
        p1 = self.measure_p1
        kind = self.measure_pending_kind
        size = self.measure_pending_size
        if kind == "diameter":
            text = f"Ø{format_dim(size)}"
            leader_kw = dict(diameter_radius=size / 2, radius_length=None)
        elif kind == "radius":
            text = f"R{format_dim(size)}"
            leader_kw = dict(radius_length=size, diameter_radius=None)
        else:
            self._clear_measure_preview()
            return
        dx, dy = x - p1[0], y - p1[1]
        ln = math.hypot(dx, dy) or 1.0
        ox, oy = dx / ln * 42.0, dy / ln * 42.0
        color = self.colors["dim"].name()
        f = QFont()
        f.setPointSize(10)
        if self._measure_preview_leader is None:
            from app.editor.items import LeaderGraphicsItem
            self._measure_preview_leader = LeaderGraphicsItem(
                "__preview__", p1[0], p1[1], text, color, f, ox, oy,
                lambda *a, **k: None, lambda *a, **k: None, lambda *a, **k: None,
                marker_line_width=self._circle_marker_line_width(),
                **leader_kw,
            )
            self.scene.addItem(self._measure_preview_leader)
        else:
            self._measure_preview_leader.update_anchor(p1[0], p1[1])
            self._measure_preview_leader.update_text(text)
            self._measure_preview_leader.text_offset = QPointF(ox, oy)
            self._measure_preview_leader.diameter_radius = leader_kw["diameter_radius"]
            self._measure_preview_leader.radius_length = leader_kw["radius_length"]
            self._measure_preview_leader.update()

    def set_measure_mode(self, active: bool) -> None:
        self.measure_mode = active
        if active:
            self.cancel_shutter()
            self.cancel_aux_line()
            self.cancel_rectangle()
            self.cancel_hole_place()
            self.cancel_array_place()
        if not active:
            self.measure_p1 = None
            self.measure_pending_kind = "linear"
            self.measure_pending_size = 0.0
            self.measure_leader_placement = False
            self._clear_measure_preview()
        self._hide_measure_markers()

    def cancel_measure(self) -> None:
        self.measure_mode = False
        self.measure_p1 = None
        self.measure_pending_kind = "linear"
        self.measure_pending_size = 0.0
        self.measure_leader_placement = False
        self._measure_pending_anchor = None
        self._clear_measure_preview()
        self._hide_measure_markers()

    def _make_measure_marker(self, color: str) -> QGraphicsEllipseItem:
        r = 5.0
        item = QGraphicsEllipseItem(-r, -r, r * 2, r * 2)
        item.setPen(QPen(QColor(color), 2.0))
        item.setBrush(QBrush(QColor(color)))
        item.setZValue(100)
        item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.scene.addItem(item)
        return item

    def _hide_measure_markers(self) -> None:
        for item in (self._measure_marker_p1, self._measure_marker_cursor):
            if item is not None:
                item.setVisible(False)

    def _sync_measure_markers(self) -> None:
        if self._measure_marker_cursor is None:
            self._measure_marker_cursor = self._make_measure_marker("#2f9e44")
        if self._measure_marker_p1 is None:
            self._measure_marker_p1 = self._make_measure_marker("#2f9e44")
        if self.measure_p1 is not None:
            self._measure_marker_p1.setPos(self.measure_p1[0], self.measure_p1[1])
            self._measure_marker_p1.setVisible(True)
            if self.measure_leader_placement:
                self._measure_marker_cursor.setVisible(False)
            else:
                self._measure_marker_cursor.setPen(QPen(QColor("#f08c00"), 2.0))
                self._measure_marker_cursor.setBrush(QBrush(QColor("#f08c00")))
        else:
            self._measure_marker_p1.setVisible(False)
            self._measure_marker_cursor.setPen(QPen(QColor("#2f9e44"), 2.0))
            self._measure_marker_cursor.setBrush(QBrush(QColor("#2f9e44")))

    def update_measure_cursor(self, x: float, y: float) -> None:
        if not self.measure_mode:
            return
        if self.measure_leader_placement:
            self._sync_measure_markers()
            self._update_measure_leader_preview(x, y)
            return
        self._sync_measure_markers()
        self._measure_marker_cursor.setPos(x, y)
        self._measure_marker_cursor.setVisible(True)

    def click_measure_point(
        self, raw_x: float, raw_y: float, x: float, y: float, snapped: bool,
    ) -> bool:
        """Place point; return True when measure is complete."""
        if not self.measure_mode:
            return False
        if self.measure_leader_placement and self.measure_p1 is not None:
            p1 = self.measure_p1
            from app.models.base import MeasureAnchor
            from app.geometry.measure_bind import resolve_circle_measure_anchor
            anchor1 = self._measure_pending_anchor
            if anchor1 is None:
                anchor1 = resolve_circle_measure_anchor(
                    self.document, p1[0], p1[1],
                    self.measure_pending_kind, self.measure_pending_size,
                    self._measure_hit_tolerance(),
                )
            self.document.add_measure(
                p1[0], p1[1], x, y,
                kind=self.measure_pending_kind,
                size=self.measure_pending_size,
                anchor1=anchor1,
                anchor2=MeasureAnchor("free", x=x, y=y),
            )
            self._measure_pending_anchor = None
            self.measure_mode = False
            self.measure_p1 = None
            self.measure_pending_kind = "linear"
            self.measure_pending_size = 0.0
            self.measure_leader_placement = False
            self._clear_measure_preview()
            self._hide_measure_markers()
            self._guide_item.clear()
            return True
        if self.measure_p1 is None:
            if not snapped:
                hit = self._pick_measure_anchor(raw_x, raw_y)
                if hit is not None:
                    kind, cx, cy, size = hit
                    self.measure_p1 = (cx, cy)
                    self.measure_pending_kind = kind
                    self.measure_pending_size = size
                    from app.geometry.measure_bind import resolve_circle_measure_anchor
                    self._measure_pending_anchor = resolve_circle_measure_anchor(
                        self.document, cx, cy, kind, size, self._measure_hit_tolerance(),
                    )
                    self.measure_leader_placement = True
                    self._sync_measure_markers()
                    self.update_measure_cursor(x, y)
                    return False
            self.measure_p1 = (x, y)
            self.measure_pending_kind = "linear"
            self.measure_pending_size = 0.0
            self._sync_measure_markers()
            self.update_measure_cursor(x, y)
            return False
        p1 = self.measure_p1
        from app.geometry.measure_bind import resolve_measure_anchor
        tol = self._measure_hit_tolerance()
        if self.measure_pending_kind in ("diameter", "radius"):
            from app.models.base import MeasureAnchor
            anchor1 = self._measure_pending_anchor or resolve_measure_anchor(
                self.document, p1[0], p1[1], tol,
            )
            self.document.add_measure(
                p1[0], p1[1], x, y,
                kind=self.measure_pending_kind,
                size=self.measure_pending_size,
                anchor1=anchor1,
                anchor2=MeasureAnchor("free", x=x, y=y),
            )
        else:
            a1 = resolve_measure_anchor(self.document, p1[0], p1[1], tol)
            a2 = resolve_measure_anchor(self.document, x, y, tol)
            self.document.add_measure(p1[0], p1[1], x, y, anchor1=a1, anchor2=a2)
        self._measure_pending_anchor = None
        self.measure_mode = False
        self.measure_p1 = None
        self.measure_pending_kind = "linear"
        self.measure_pending_size = 0.0
        self.measure_leader_placement = False
        self._clear_measure_preview()
        self._hide_measure_markers()
        self._guide_item.clear()
        return True

    @staticmethod
    def _leader_offset_from_points(p1, p2, st) -> tuple[float, float]:
        if st.offset_x != -50.0 or st.offset_y != -20.0:
            return st.offset_x, st.offset_y
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        ln = math.hypot(dx, dy) or 1.0
        return dx / ln * 42.0, dy / ln * 42.0

    def _measure_hit_tolerance(self) -> float:
        return max(2.0, 8.0 / self._view_scale())

    def _pick_measure_anchor(self, x: float, y: float) -> tuple[str, float, float, float] | None:
        tol = self._measure_hit_tolerance()
        doc = self.document
        best: tuple[str, float, float, float, float] | None = None
        for hole in doc.holes:
            for i, rh in enumerate(doc._resolve_single_hole(hole)):
                if not doc.is_instance_visible_in_editor(hole.id, i):
                    continue
                if rh.kind != HoleKind.CIRCLE:
                    continue
                r = rh.diameter / 2
                d = math.hypot(x - rh.cx, y - rh.cy)
                edge_dist = abs(d - r)
                if edge_dist <= tol and (best is None or edge_dist < best[4]):
                    best = ("diameter", rh.cx, rh.cy, rh.diameter, edge_dist)
        if doc.contour_kind == ContourKind.CIRCLE:
            d = doc.circle.diameter
            cx, cy, r = d / 2, d / 2, d / 2
            dist = math.hypot(x - cx, y - cy)
            edge_dist = abs(dist - r)
            if edge_dist <= tol and (best is None or edge_dist < best[4]):
                best = ("diameter", cx, cy, d, edge_dist)
        elif doc.contour_kind == ContourKind.DXF:
            for ent in doc.dxf_contour.entities:
                if ent["type"] == "arc":
                    cx, cy, r = ent["cx"], ent["cy"], ent["r"]
                    d = math.hypot(x - cx, y - cy)
                    edge_dist = abs(d - r)
                    if edge_dist <= tol and (best is None or edge_dist < best[4]):
                        best = ("radius", cx, cy, r, edge_dist)
                elif ent["type"] == "circle":
                    cx, cy, r = ent["cx"], ent["cy"], ent["r"]
                    d = math.hypot(x - cx, y - cy)
                    edge_dist = abs(d - r)
                    if edge_dist <= tol and (best is None or edge_dist < best[4]):
                        best = ("diameter", cx, cy, r * 2, edge_dist)
        if best is None:
            return None
        return best[0], best[1], best[2], best[3]

    def snap_measure_point(self, x: float, y: float, view_scale: float) -> tuple[float, float, bool]:
        points = self.document.all_snap_points()
        nx, ny, snapped, guides = self._snap_drag(x, y, points)
        self._guide_item.set_guides(guides, self._guide_bounds())
        return nx, ny, snapped

    def _on_shutter_select(self, shutter_id: str, notify: bool = True) -> None:
        self.document.select(SelectionKind.SHUTTER, shutter_id, notify=notify)

    def _build_shutter(self, s) -> None:
        sel = self.document.selection
        selected = sel.kind == SelectionKind.SHUTTER and sel.object_id == s.id
        self.scene.addItem(ShutterRegionGraphicsItem(
            s, self.document.shutter_layout, self.colors, selected,
            on_select=self._on_shutter_select,
            on_move=self._on_shutter_move,
            on_edge_move=self._on_shutter_edge_move,
            on_move_end=self._on_shutter_move_end,
            on_drag_start=self._on_shutter_drag_start,
            get_view_scale=self._view_scale,
        ))
        self._build_shutter_dims(s)

    def _build_shutter_dims(self, s) -> None:
        doc = self.document
        if doc.contour_kind != ContourKind.RECT:
            return
        _, _, cw, ch = doc.contour_bounds()
        left, right, top, bottom = doc.shutter_edge_refs(s)
        color = s.color
        sid = s.id
        self._add_dim(
            f"{sid}_left", "top", 0, left, top,
            format_dim(left), color, "shutter", sid,
            ext1=top, ext2=top,
        )
        self._add_dim(
            f"{sid}_right", "top", right, cw, top,
            format_dim(cw - right), color, "shutter", sid,
            ext1=top, ext2=top,
        )
        self._add_dim(
            f"{sid}_top", "left", 0, top, left,
            format_dim(top), color, "shutter", sid,
            ext1=0, ext2=left,
        )
        self._add_dim(
            f"{sid}_bottom", "left", bottom, ch, left,
            format_dim(ch - bottom), color, "shutter", sid,
            ext1=left, ext2=0,
        )
        self._add_dim(
            f"{sid}_rw", "bottom", left, right, bottom,
            format_dim(s.width), color, "shutter", sid,
            ext1=bottom, ext2=bottom,
        )
        self._add_dim(
            f"{sid}_rh", "right", top, bottom, right,
            format_dim(s.height), color, "shutter", sid,
            ext1=right, ext2=right,
        )

    def _shutter_dim_ids(self, shutter_id: str) -> list[str]:
        return self.document.dim_ids_for_shutter(shutter_id)

    def _on_shutter_drag_start(self, shutter_id: str) -> None:
        self._shutter_drag_dim_refs = {}
        for dim_id in self._shutter_dim_ids(shutter_id):
            item = self._find_dim_item(dim_id)
            if item is not None:
                self._shutter_drag_dim_refs[dim_id] = item.ref

    def _sync_shutter_dims(self, shutter_id: str) -> None:
        s = self.document.get_shutter(shutter_id)
        if s is None:
            return
        doc = self.document
        _, _, cw, ch = doc.contour_bounds()
        left, right, top, bottom = doc.shutter_edge_refs(s)
        sid = s.id

        def ref(dim_id: str, current: float) -> float:
            return self._shutter_drag_dim_refs.get(dim_id, current)

        self._update_dim_live(
            f"{sid}_left", "shutter", sid, 0, left,
            ref(f"{sid}_left", top), format_dim(left),
            ext1=top, ext2=top,
        )
        self._update_dim_live(
            f"{sid}_right", "shutter", sid, right, cw,
            ref(f"{sid}_right", top), format_dim(cw - right),
            ext1=top, ext2=top,
        )
        self._update_dim_live(
            f"{sid}_top", "shutter", sid, 0, top,
            ref(f"{sid}_top", left), format_dim(top),
            ext1=0, ext2=left,
        )
        self._update_dim_live(
            f"{sid}_bottom", "shutter", sid, bottom, ch,
            ref(f"{sid}_bottom", left), format_dim(ch - bottom),
            ext1=left, ext2=0,
        )
        self._update_dim_live(
            f"{sid}_rw", "shutter", sid, left, right,
            ref(f"{sid}_rw", bottom), format_dim(s.width),
            ext1=bottom, ext2=bottom,
        )
        self._update_dim_live(
            f"{sid}_rh", "shutter", sid, top, bottom,
            ref(f"{sid}_rh", right), format_dim(s.height),
            ext1=right, ext2=right,
        )

    def _on_shutter_move(self, shutter_id: str, x: float, y: float) -> tuple[float, float]:
        others = self.document.snap_points_for_shutter_drag(shutter_id)
        sx, sy, _, guides = self._snap_drag(x, y, others, shutter_id)
        self._show_snap_guides(guides)
        self.document.move_shutter(shutter_id, sx, sy)
        self._sync_shutter_dims(shutter_id)
        return sx, sy

    def _on_shutter_edge_move(
        self, shutter_id: str, edge: str, mx: float, my: float,
    ) -> tuple[float, float, float, float]:
        others = self.document.snap_points_for_region_edge_drag(shutter_id)
        sx, sy, _, guides = self._snap_drag(mx, my, others, shutter_id)
        self._show_snap_guides(guides)
        value = sx if edge in ("left", "right") else sy
        self.document.resize_shutter_edge(shutter_id, edge, value)
        self._sync_shutter_dims(shutter_id)
        s = self.document.get_shutter(shutter_id)
        assert s is not None
        return s.cx, s.cy, s.width, s.height

    def _on_shutter_move_end(self, shutter_id: str) -> None:
        for dim_id, ref in self._shutter_drag_dim_refs.items():
            self.document.get_dim_state(dim_id).ref_anchor = ref
        self._shutter_drag_dim_refs = {}
        self._guide_item.clear()
        self.document.notify()

    def set_shutter_mode(self, active: bool) -> None:
        self.shutter_mode = active
        if active:
            self.cancel_aux_line()
            self.cancel_rectangle()
            self.cancel_hole_place()
            self.cancel_array_place()
        if not active:
            self._shutter_draw_p1 = None
            self._clear_shutter_preview()

    def cancel_shutter(self) -> None:
        self.set_shutter_mode(False)

    def _ensure_shutter_preview(self) -> None:
        if self._shutter_preview is None:
            self._shutter_preview = QGraphicsRectItem()
            pen = QPen(QColor("#495057"))
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            self._shutter_preview.setPen(pen)
            self._shutter_preview.setBrush(QBrush(QColor(73, 80, 87, 40)))
            self._shutter_preview.setZValue(90)
            self.scene.addItem(self._shutter_preview)

    def _clear_shutter_preview(self) -> None:
        if self._shutter_preview is not None:
            self.scene.removeItem(self._shutter_preview)
            self._shutter_preview = None

    def _update_shutter_preview(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self._ensure_shutter_preview()
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        if right - left < 1e-6:
            right = left + 1.0
        if bottom - top < 1e-6:
            bottom = top + 1.0
        self._shutter_preview.setRect(QRectF(left, top, right - left, bottom - top))

    def shutter_press(self, x: float, y: float) -> None:
        if not self.shutter_mode:
            return
        sx, sy, _ = self.snap_measure_point(x, y, self._view_scale())
        self._shutter_draw_p1 = (sx, sy)
        self._update_shutter_preview(sx, sy, sx, sy)

    def shutter_move(self, x: float, y: float) -> None:
        if not self.shutter_mode or self._shutter_draw_p1 is None:
            return
        sx, sy, _ = self.snap_measure_point(x, y, self._view_scale())
        p1 = self._shutter_draw_p1
        self._update_shutter_preview(p1[0], p1[1], sx, sy)

    def shutter_release(self, x: float, y: float) -> bool:
        """Finish rectangle; return True when shutter created."""
        if not self.shutter_mode or self._shutter_draw_p1 is None:
            return False
        sx, sy, _ = self.snap_measure_point(x, y, self._view_scale())
        p1 = self._shutter_draw_p1
        self._shutter_draw_p1 = None
        self._clear_shutter_preview()
        self._guide_item.clear()
        left, right = sorted((p1[0], sx))
        top, bottom = sorted((p1[1], sy))
        w = right - left
        h = bottom - top
        if w < 1.0 or h < 1.0:
            return False
        cx, cy = (left + right) / 2, (top + bottom) / 2
        if self.on_add_shutter:
            self.on_add_shutter(cx, cy, w, h)
        else:
            self.document.add_shutter(cx, cy, w, h)
        self.shutter_mode = False
        return True

    def snap_shutter_point(self, x: float, y: float, view_scale: float) -> tuple[float, float, bool]:
        return self.snap_measure_point(x, y, view_scale)

    # --- infinite auxiliary line tool ---

    def _on_infinite_line_select(self, line_id: str, notify: bool = True) -> None:
        self.document.select(SelectionKind.INFINITE_LINE, line_id, notify=notify)

    def _build_infinite_line(self, line) -> None:
        sel = self.document.selection
        selected = sel.kind == SelectionKind.INFINITE_LINE and sel.object_id == line.id
        self.scene.addItem(InfiniteLineGraphicsItem(
            line, self.colors, selected,
            on_select=self._on_infinite_line_select,
            on_move=self._on_infinite_line_move,
            on_move_end=self._on_infinite_line_move_end,
        ))
        self._build_infinite_line_dims(line)

    def _on_infinite_line_move(self, line_id: str, dx: float, dy: float) -> None:
        self.document.move_infinite_line(line_id, dx, dy)

    def _on_infinite_line_move_end(self, line_id: str) -> None:
        self.document.notify()

    def _build_infinite_line_dims(self, line) -> None:
        from app.geometry.infinite_line_bind import dimension_points
        pt1, pt2, dist = dimension_points(line, self.document)
        self._add_dim(
            f"{line.id}_dist", "bottom", 0, dist, 0,
            format_dim(dist), line.color,
            "infinite_line", line.id,
            pt1=pt1, pt2=pt2,
        )

    def _clear_aux_preview(self) -> None:
        if self._aux_preview is not None:
            self.scene.removeItem(self._aux_preview)
            self._aux_preview = None

    # --- interactive hole placement ---

    def set_hole_place_mode(self, active: bool, color: str = "#e03131") -> None:
        self.hole_place_mode = active
        self._hole_place_color = color
        if active:
            self.cancel_measure()
            self.cancel_shutter()
            self.cancel_aux_line()
            self.cancel_rectangle()
            self.cancel_array_place()
            self.origin_placement_mode = False
        else:
            self._hole_place_cursor = None
            self._placement_preview.clear()
            self._guide_item.clear()

    def cancel_hole_place(self) -> None:
        self.set_hole_place_mode(False)

    def update_hole_place_cursor(self, x: float, y: float) -> None:
        if not self.hole_place_mode:
            return
        sx, sy, _ = self.snap_measure_point(x, y, self._view_scale())
        self._hole_place_cursor = (sx, sy)
        self._placement_preview.show_hole(
            self.document, sx, sy, 6.0, self._hole_place_color,
        )

    def click_hole_place(self, x: float, y: float) -> bool:
        if not self.hole_place_mode:
            return False
        sx, sy, _ = self.snap_measure_point(x, y, self._view_scale())
        self._hole_place_cursor = (sx, sy)
        if self.on_place_hole:
            self.on_place_hole(sx, sy, self._hole_place_color)
        else:
            self.cancel_hole_place()
        return True

    # --- interactive array placement ---

    def set_array_place_mode(self, active: bool, hole_id: str = "") -> None:
        self.array_place_mode = active
        self._array_place_hole_id = hole_id
        self._array_place_count = 2
        if active:
            self.cancel_measure()
            self.cancel_shutter()
            self.cancel_aux_line()
            self.cancel_rectangle()
            self.cancel_hole_place()
            self.origin_placement_mode = False
            hole = self.document.get_hole(hole_id)
            if hole is not None:
                self._array_place_cursor = (hole.cx + 20.0, hole.cy)
                self._refresh_array_place_preview()
        else:
            self._array_place_cursor = None
            self._placement_preview.clear()
            self._guide_item.clear()

    def cancel_array_place(self) -> None:
        self.set_array_place_mode(False)

    def _array_preview_positions(
        self, sx: float, sy: float,
    ) -> list[tuple[float, float]]:
        hole = self.document.get_hole(self._array_place_hole_id)
        if hole is None:
            return []
        count_x = self._array_place_count
        count_y = 1
        if count_x <= 1:
            return [(hole.cx, hole.cy)]
        step_x = (sx - hole.cx) / (count_x - 1)
        step_y = 0.0
        positions: list[tuple[float, float]] = []
        for iy in range(count_y):
            for ix in range(count_x):
                cx, cy = _transform_point(
                    hole.cx + ix * step_x, hole.cy + iy * step_y,
                    hole.cx, hole.cy, 0.0,
                )
                positions.append((cx, cy))
        return positions

    def _refresh_array_place_preview(self) -> None:
        if not self.array_place_mode or self._array_place_cursor is None:
            return
        hole = self.document.get_hole(self._array_place_hole_id)
        if hole is None:
            return
        sx, sy = self._array_place_cursor
        positions = self._array_preview_positions(sx, sy)
        self._placement_preview.show_array_grid(
            positions, hole.diameter, hole.color,
        )

    def update_array_place_cursor(self, x: float, y: float) -> None:
        if not self.array_place_mode:
            return
        sx, sy, _ = self.snap_measure_point(x, y, self._view_scale())
        self._array_place_cursor = (sx, sy)
        self._refresh_array_place_preview()

    def adjust_array_place_count(self, delta: int) -> None:
        if not self.array_place_mode:
            return
        if self._array_place_cursor is None:
            hole = self.document.get_hole(self._array_place_hole_id)
            if hole is not None:
                self._array_place_cursor = (hole.cx + 20.0, hole.cy)
        self._array_place_count = max(2, min(100, self._array_place_count + delta))
        self._refresh_array_place_preview()

    def click_array_place(self, x: float, y: float) -> bool:
        if not self.array_place_mode:
            return False
        hole = self.document.get_hole(self._array_place_hole_id)
        if hole is None:
            self.cancel_array_place()
            return False
        sx, sy, _ = self.snap_measure_point(x, y, self._view_scale())
        count_x = self._array_place_count
        step_x = 20.0 if count_x <= 1 else (sx - hole.cx) / (count_x - 1)
        n = len(self.document.arrays_for_hole(hole.id)) + 1
        arr = HoleArray(
            source_hole_id=hole.id,
            name=f"Массив {n}",
            kind=ArrayKind.GRID,
            count_x=count_x,
            count_y=1,
            step_x=step_x,
            step_y=20.0,
            grid_angle=0.0,
        )
        if self.on_place_array:
            self.on_place_array(arr)
        else:
            self.cancel_array_place()
        return True

    def can_accept_tool_digits(self) -> bool:
        return bool(
            (self.aux_line_mode and self._aux_src is not None)
            or (self.rectangle_mode and self._rect_draw_p1 is not None)
        )

    def handle_tool_digit_input(self, digits: str) -> bool:
        if self.aux_line_mode and self._aux_src is not None and self.on_aux_distance_input:
            self.on_aux_distance_input(
                self._aux_src, self._aux_current_offset, digits,
            )
            return True
        if self.rectangle_mode and self._rect_draw_p1 is not None and self.on_rect_size_input:
            self.on_rect_size_input(self._rect_draw_p1, digits)
            return True
        return False

    def place_aux_at_distance(self, distance: float) -> bool:
        if not self.aux_line_mode or self._aux_src is None:
            return False
        offset = self._aux_offset_sign * abs(distance)
        from app.geometry.infinite_line_bind import segment_to_source_anchor
        from app.geometry.line_math import parallel_segment, segment_midpoint
        px1, py1, px2, py2 = parallel_segment(*self._aux_src, offset)
        mx, my = segment_midpoint(px1, py1, px2, py2)
        anchor = segment_to_source_anchor(
            self._aux_pick_seg, mx, my, self.document,
        ) if self._aux_pick_seg else None
        if self.on_add_infinite_line:
            self.on_add_infinite_line(*self._aux_src, offset, anchor)
        else:
            self.document.add_infinite_line(*self._aux_src, offset, source_anchor=anchor)
        self._aux_src = None
        self._aux_pick_seg = None
        self._aux_current_offset = 0.0
        self._clear_aux_preview()
        self._placement_preview.clear_dims()
        self.aux_line_mode = False
        self._guide_item.clear()
        return True

    def place_rect_at_sizes(self, width: float, height: float) -> bool:
        if not self.rectangle_mode or self._rect_draw_p1 is None:
            return False
        p1 = self._rect_draw_p1
        self._rect_draw_p1 = None
        self._rect_place_cursor = None
        self._clear_rect_preview()
        self._placement_preview.clear()
        self._guide_item.clear()
        w = max(width, 1.0)
        h = max(height, 1.0)
        cx, cy = p1[0] + w / 2, p1[1] + h / 2
        if self.on_add_rectangle:
            self.on_add_rectangle(cx, cy, w, h)
        else:
            self.document.add_drawn_rect(cx, cy, w, h)
        self.rectangle_mode = False
        return True

    def _update_aux_preview(self, offset: float) -> None:
        if self._aux_src is None:
            return
        from app.geometry.line_math import clip_infinite_line, parallel_segment
        x1, y1, x2, y2 = parallel_segment(*self._aux_src, offset)
        br = self.scene.sceneRect()
        clipped = clip_infinite_line(x1, y1, x2, y2, br.left(), br.top(), br.right(), br.bottom())
        if clipped is None:
            return
        if self._aux_preview is None:
            self._aux_preview = QGraphicsPathItem()
            pen = QPen(QColor("#868e96"))
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            self._aux_preview.setPen(pen)
            self._aux_preview.setZValue(90)
            self.scene.addItem(self._aux_preview)
        path = QPainterPath()
        path.moveTo(clipped[0], clipped[1])
        path.lineTo(clipped[2], clipped[3])
        self._aux_preview.setPath(path)
        self._placement_preview.show_aux_distance(self._aux_src, offset)

    def set_aux_line_mode(self, active: bool) -> None:
        self.aux_line_mode = active
        if active:
            self.cancel_measure()
            self.cancel_shutter()
            self.cancel_rectangle()
            self.cancel_hole_place()
            self.cancel_array_place()
            self.origin_placement_mode = False
        if not active:
            self._aux_src = None
            self._aux_pick_seg = None
            self._aux_current_offset = 0.0
            self._clear_aux_preview()
            self._placement_preview.clear_dims()

    def cancel_aux_line(self) -> None:
        self.set_aux_line_mode(False)

    def aux_line_press(self, x: float, y: float, view_scale: float) -> bool:
        from app.geometry.line_math import (
            collect_line_segments, pick_line_segment, signed_offset_to_line,
        )
        if not self.aux_line_mode:
            return False
        if self._aux_src is None:
            tol = max(4.0, 12.0 / max(view_scale, 0.01))
            seg = pick_line_segment(x, y, collect_line_segments(self.document), tol)
            if seg is None:
                return False
            self._aux_pick_seg = seg
            self._aux_src = (seg.x1, seg.y1, seg.x2, seg.y2)
            offset = signed_offset_to_line(x, y, *self._aux_src)
            self._update_aux_preview(offset)
            return False
        offset = signed_offset_to_line(x, y, *self._aux_src)
        from app.geometry.infinite_line_bind import segment_to_source_anchor
        anchor = segment_to_source_anchor(
            self._aux_pick_seg, x, y, self.document,
        ) if self._aux_pick_seg else None
        if self.on_add_infinite_line:
            self.on_add_infinite_line(*self._aux_src, offset, anchor)
        else:
            self.document.add_infinite_line(*self._aux_src, offset, source_anchor=anchor)
        self._aux_src = None
        self._aux_pick_seg = None
        self._clear_aux_preview()
        self.aux_line_mode = False
        self._guide_item.clear()
        return True

    def aux_line_move(self, x: float, y: float) -> None:
        if not self.aux_line_mode or self._aux_src is None:
            return
        from app.geometry.line_math import signed_offset_to_line
        offset = signed_offset_to_line(x, y, *self._aux_src)
        self._aux_current_offset = offset
        self._aux_offset_sign = 1.0 if offset >= 0 else -1.0
        self._update_aux_preview(offset)

    # --- drawn rectangle tool ---

    def _on_drawn_rect_select(self, rect_id: str, notify: bool = True) -> None:
        self.document.select(SelectionKind.DRAWN_RECT, rect_id, notify=notify)

    def _build_drawn_rect(self, r) -> None:
        sel = self.document.selection
        selected = sel.kind == SelectionKind.DRAWN_RECT and sel.object_id == r.id
        self.scene.addItem(DrawnRectangleGraphicsItem(
            r, self.colors, selected,
            on_select=self._on_drawn_rect_select,
            on_move=self._on_drawn_rect_move,
            on_edge_move=self._on_drawn_rect_edge_move,
            on_move_end=self._on_drawn_rect_move_end,
            on_drag_start=None,
            get_view_scale=self._view_scale,
        ))
        self._build_drawn_rect_dims(r)

    def _build_drawn_rect_dims(self, r) -> None:
        from app.geometry.shutter import region_bounds
        left, top, right, bottom = region_bounds(r.cx, r.cy, r.width, r.height)
        rid = r.id
        color = r.color
        self._add_dim(
            f"{rid}_rw", "bottom", left, right, bottom,
            format_dim(r.width), color, "drawn_rect", rid,
            ext1=bottom, ext2=bottom,
        )
        self._add_dim(
            f"{rid}_rh", "right", top, bottom, right,
            format_dim(r.height), color, "drawn_rect", rid,
            ext1=right, ext2=right,
        )

    def _on_drawn_rect_move(self, rect_id: str, x: float, y: float) -> tuple[float, float]:
        others = self.document.snap_points_for_drawn_rect_drag(rect_id)
        sx, sy, _, guides = self._snap_drag(x, y, others, rect_id)
        self._show_snap_guides(guides)
        self.document.move_drawn_rect(rect_id, sx, sy)
        return sx, sy

    def _on_drawn_rect_edge_move(
        self, rect_id: str, edge: str, mx: float, my: float,
    ) -> tuple[float, float, float, float]:
        others = self.document.snap_points_for_region_edge_drag(rect_id)
        sx, sy, _, guides = self._snap_drag(mx, my, others, rect_id)
        self._show_snap_guides(guides)
        value = sx if edge in ("left", "right") else sy
        self.document.resize_drawn_rect_edge(rect_id, edge, value)
        r = self.document.get_drawn_rect(rect_id)
        assert r is not None
        return r.cx, r.cy, r.width, r.height

    def _on_drawn_rect_move_end(self, rect_id: str) -> None:
        self._guide_item.clear()
        self.document.notify()

    def set_rectangle_mode(self, active: bool) -> None:
        self.rectangle_mode = active
        if active:
            self.cancel_measure()
            self.cancel_shutter()
            self.cancel_aux_line()
            self.cancel_hole_place()
            self.cancel_array_place()
            self.origin_placement_mode = False
        if not active:
            self._rect_draw_p1 = None
            self._rect_place_cursor = None
            self._clear_rect_preview()
            self._placement_preview.clear()

    def cancel_rectangle(self) -> None:
        self.set_rectangle_mode(False)

    def _ensure_rect_preview(self) -> None:
        if self._rect_preview is None:
            self._rect_preview = QGraphicsRectItem()
            pen = QPen(QColor("#495057"))
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            self._rect_preview.setPen(pen)
            self._rect_preview.setBrush(QBrush(QColor(73, 80, 87, 40)))
            self._rect_preview.setZValue(90)
            self.scene.addItem(self._rect_preview)

    def _clear_rect_preview(self) -> None:
        if self._rect_preview is not None:
            self.scene.removeItem(self._rect_preview)
            self._rect_preview = None

    def _update_rect_preview(self, x1: float, y1: float, x2: float, y2: float) -> None:
        self._ensure_rect_preview()
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
        if right - left < 1e-6:
            right = left + 1.0
        if bottom - top < 1e-6:
            bottom = top + 1.0
        self._rect_preview.setRect(QRectF(left, top, right - left, bottom - top))

    def rectangle_press(self, x: float, y: float) -> None:
        if not self.rectangle_mode:
            return
        sx, sy, _ = self.snap_measure_point(x, y, self._view_scale())
        self._rect_draw_p1 = (sx, sy)
        self._rect_place_cursor = (sx, sy)
        self._placement_preview.show_rect(sx, sy, sx + 1.0, sy + 1.0)

    def rectangle_move(self, x: float, y: float) -> None:
        if not self.rectangle_mode or self._rect_draw_p1 is None:
            return
        sx, sy, _ = self.snap_measure_point(x, y, self._view_scale())
        p1 = self._rect_draw_p1
        self._rect_place_cursor = (sx, sy)
        left, right = sorted((p1[0], sx))
        top, bottom = sorted((p1[1], sy))
        self._placement_preview.show_rect(left, top, right, bottom)

    def rectangle_release(self, x: float, y: float) -> bool:
        if not self.rectangle_mode or self._rect_draw_p1 is None:
            return False
        sx, sy, _ = self.snap_measure_point(x, y, self._view_scale())
        p1 = self._rect_draw_p1
        self._rect_draw_p1 = None
        self._rect_place_cursor = None
        self._clear_rect_preview()
        self._placement_preview.clear()
        self._guide_item.clear()
        left, right = sorted((p1[0], sx))
        top, bottom = sorted((p1[1], sy))
        w = right - left
        h = bottom - top
        if w < 1.0 or h < 1.0:
            return False
        cx, cy = (left + right) / 2, (top + bottom) / 2
        if self.on_add_rectangle:
            self.on_add_rectangle(cx, cy, w, h)
        else:
            self.document.add_drawn_rect(cx, cy, w, h)
        self.rectangle_mode = False
        return True
