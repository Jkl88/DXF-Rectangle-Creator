from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QUndoCommand

from app.models.base import ContourKind, Hole, HoleArray, SelectionKind, ShutterRegion, ShutterLayoutParams, InfiniteLine, DrawnRectangle, DrawnGeometry
from app.models.document import Document


class DocumentCommand(QUndoCommand):
    def __init__(self, document: Document, text: str):
        super().__init__(text)
        self.document = document
        self._before = None
        self._after = None

    def _snapshot(self):
        import copy
        return copy.deepcopy({
            "designation": self.document.designation,
            "name": self.document.name,
            "contour_kind": self.document.contour_kind,
            "rect": self.document.rect,
            "circle": self.document.circle,
            "dxf_contour": self.document.dxf_contour,
            "holes": self.document.holes,
            "arrays": self.document.arrays,
            "selection": self.document.selection,
            "instance_overrides": self.document.instance_overrides,
            "instance_states": self.document.instance_states,
            "object_states": self.document.object_states,
            "dim_states": self.document.dim_states,
            "leader_states": self.document.leader_states,
            "default_font_size": self.document.default_font_size,
            "title_block": self.document.title_block,
            "measures": self.document.measures,
            "shutters": self.document.shutters,
            "shutter_layout": self.document.shutter_layout,
            "infinite_lines": self.document.infinite_lines,
            "drawn_rects": self.document.drawn_rects,
            "drawn_geometries": self.document.drawn_geometries,
        })

    def _restore(self, snap):
        self.document.designation = snap["designation"]
        self.document.name = snap["name"]
        self.document.contour_kind = snap["contour_kind"]
        self.document.rect = snap["rect"]
        self.document.circle = snap["circle"]
        self.document.dxf_contour = snap.get("dxf_contour", self.document.dxf_contour)
        self.document.holes = snap["holes"]
        self.document.arrays = snap["arrays"]
        self.document.selection = snap["selection"]
        self.document.instance_overrides = snap.get("instance_overrides", {})
        self.document.instance_states = snap.get("instance_states", {})
        self.document.object_states = snap.get("object_states", {})
        self.document.dim_states = snap.get("dim_states", {})
        self.document.leader_states = snap.get("leader_states", {})
        self.document.default_font_size = snap.get("default_font_size", 9)
        self.document.title_block = snap.get("title_block", self.document.title_block)
        self.document.measures = snap.get("measures", [])
        self.document.shutters = snap.get("shutters", [])
        self.document.shutter_layout = snap.get("shutter_layout", ShutterLayoutParams.defaults())
        self.document.infinite_lines = snap.get("infinite_lines", [])
        self.document.drawn_rects = snap.get("drawn_rects", [])
        self.document.drawn_geometries = snap.get("drawn_geometries", [])
        self.document.notify()

    def redo(self):
        if self._after is not None:
            self._restore(self._after)

    def undo(self):
        if self._before is not None:
            self._restore(self._before)


class PropertyChangeCommand(DocumentCommand):
    def __init__(self, document: Document, apply_fn, text: str):
        super().__init__(document, text)
        self._apply_fn = apply_fn
        self._before = self._snapshot()
        apply_fn()
        self._after = self._snapshot()

    def undo(self):
        super().undo()

    def redo(self):
        super().redo()


class AddHoleCommand(DocumentCommand):
    def __init__(self, document: Document, hole: Hole):
        super().__init__(document, "Добавить отверстие")
        self.hole = hole
        self._before = self._snapshot()

    def redo(self):
        if self.hole not in self.document.holes:
            self.document.holes.append(self.hole)
        self.document.select(SelectionKind.HOLE, self.hole.id)
        self.document.notify()

    def undo(self):
        self.document.holes = [h for h in self.document.holes if h.id != self.hole.id]
        self.document.arrays = [a for a in self.document.arrays if a.source_hole_id != self.hole.id]
        self.document.select(SelectionKind.NONE)
        self.document.notify()


class AddArrayCommand(DocumentCommand):
    def __init__(self, document: Document, arr: HoleArray):
        super().__init__(document, "Добавить массив")
        self.arr = arr
        self._before = self._snapshot()

    def redo(self):
        if self.arr not in self.document.arrays:
            self.document.arrays.append(self.arr)
        self.document.select(SelectionKind.ARRAY, self.arr.id)
        self.document.notify()

    def undo(self):
        self.document.arrays = [a for a in self.document.arrays if a.id != self.arr.id]
        self.document.select(SelectionKind.NONE)
        self.document.notify()


class DeleteCommand(DocumentCommand):
    def __init__(self, document: Document):
        super().__init__(document, "Удалить")
        self._before = self._snapshot()
        document.remove_selected()
        self._after = self._snapshot()

    def undo(self):
        self._restore(self._before)

    def redo(self):
        self._restore(self._after)


class AddShutterCommand(DocumentCommand):
    def __init__(self, document: Document, shutter: ShutterRegion):
        super().__init__(document, "Добавить шторки")
        self.shutter = shutter
        self._before = self._snapshot()

    def redo(self):
        if self.shutter not in self.document.shutters:
            self.document.shutters.append(self.shutter)
        self.document.select(SelectionKind.SHUTTER, self.shutter.id)
        self.document.notify()

    def undo(self):
        self._restore(self._before)


class AddInfiniteLineCommand(DocumentCommand):
    def __init__(self, document: Document, line: InfiniteLine):
        super().__init__(document, "Вспомогательная линия")
        self.line = line
        self._before = self._snapshot()

    def redo(self):
        if self.line not in self.document.infinite_lines:
            self.document.infinite_lines.append(self.line)
        self.document.select(SelectionKind.INFINITE_LINE, self.line.id)
        self.document.notify()

    def undo(self):
        self._restore(self._before)


class AddDrawnRectCommand(DocumentCommand):
    def __init__(self, document: Document, rect: DrawnRectangle):
        super().__init__(document, "Прямоугольник")
        self.rect = rect
        self._before = self._snapshot()

    def redo(self):
        if self.rect not in self.document.drawn_rects:
            self.document.drawn_rects.append(self.rect)
        self.document.select(SelectionKind.DRAWN_RECT, self.rect.id)
        self.document.notify()

    def undo(self):
        self._restore(self._before)


class AddDrawnGeometryCommand(DocumentCommand):
    def __init__(self, document: Document, geometry: DrawnGeometry):
        super().__init__(document, "Геометрия")
        self.geometry = geometry
        self._before = self._snapshot()

    def redo(self):
        if self.geometry not in self.document.drawn_geometries:
            self.document.drawn_geometries.append(self.geometry)
        self.document.select(SelectionKind.DRAWN_GEOMETRY, self.geometry.id)
        self.document.notify()

    def undo(self):
        self._restore(self._before)


class ExplodeDxfContourCommand(DocumentCommand):
    def __init__(self, document: Document):
        super().__init__(document, "Разрушить контур")
        self._before = self._snapshot()

    def redo(self):
        self.document.explode_dxf_contour()

    def undo(self):
        self._restore(self._before)


class ExplodeDrawnGeometryCommand(DocumentCommand):
    def __init__(self, document: Document, geometry_id: str):
        super().__init__(document, "Разобрать полилинию")
        self.geometry_id = geometry_id
        self._before = self._snapshot()

    def redo(self):
        self.document.explode_drawn_geometry(self.geometry_id)

    def undo(self):
        self._restore(self._before)
