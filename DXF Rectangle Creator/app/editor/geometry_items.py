from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QPen, QPainter
from PyQt6.QtWidgets import QGraphicsObject, QStyleOptionGraphicsItem, QWidget

from app.geometry.dxf_entities import entities_bbox, entity_path_for_hit, hit_test_entity, paint_entities
from app.models.base import DrawnGeometry


class DrawnGeometryGraphicsItem(QGraphicsObject):
    def __init__(
        self, geometry: DrawnGeometry, colors, selected: bool,
        on_select, on_move, on_move_end, get_view_scale=None, parent=None,
    ):
        super().__init__(parent)
        self.geometry = geometry
        self.colors = colors
        self.selected = selected
        self.on_select = on_select
        self.on_move = on_move
        self.on_move_end = on_move_end
        self.get_view_scale = get_view_scale or (lambda: 1.0)
        self._dragging = False
        self._drag_start = None
        self._orig_entity = None
        self.setZValue(5)
        self.setAcceptHoverEvents(True)

    def boundingRect(self) -> QRectF:
        xmin, ymin, w, h = entities_bbox([self.geometry.entity])
        pad = 4.0
        return QRectF(xmin - pad, ymin - pad, w + 2 * pad, h + 2 * pad)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None):
        g = self.geometry
        sel_color = self.colors["selection"]
        color = QColor(sel_color if self.selected else g.color)
        color.setAlpha(220)
        pen = QPen(color, 2.5 if self.selected else 1.0)
        pen.setCosmetic(True)
        paint_entities(painter, [g.entity], pen)

    def shape(self):
        from PyQt6.QtGui import QPainterPathStroker

        path = entity_path_for_hit(self.geometry.entity)
        stroker = QPainterPathStroker()
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        tol = max(6.0 / self.get_view_scale(), 2.0)
        stroker.setWidth(tol * 2)
        return stroker.createStroke(path)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.on_select(self.geometry.id, notify=False)
            self._dragging = True
            self._drag_start = event.scenePos()
            import copy
            self._orig_entity = copy.deepcopy(self.geometry.entity)
            self.grabMouse()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and self._orig_entity is not None and self._drag_start is not None:
            delta = event.scenePos() - self._drag_start
            from app.geometry.dxf_entities import translate_entities
            self.geometry.entity = translate_entities([self._orig_entity], delta.x(), delta.y())[0]
            self.prepareGeometryChange()
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self.ungrabMouse()
            if self._orig_entity is not None and self._drag_start is not None:
                delta = event.scenePos() - self._drag_start
                moved = (delta.x() ** 2 + delta.y() ** 2) > 4
                if moved:
                    nx, ny = self.on_move(self.geometry.id, delta.x(), delta.y())
                    from app.geometry.dxf_entities import translate_entities
                    self.geometry.entity = translate_entities([self._orig_entity], nx, ny)[0]
                    if self.on_move_end:
                        self.on_move_end(self.geometry.id)
                else:
                    self.on_select(self.geometry.id, notify=True)
                self._orig_entity = None
                self._drag_start = None
            event.accept()
            return
        super().mouseReleaseEvent(event)
