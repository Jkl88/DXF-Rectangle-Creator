from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPen, QPainter
from PyQt6.QtWidgets import QGraphicsObject, QStyleOptionGraphicsItem, QWidget

from app.editor.region_rect import apply_edge_position, hit_region_edge
from app.geometry.shutter import region_bounds
from app.models.base import DrawnRectangle


class DrawnRectangleGraphicsItem(QGraphicsObject):
    def __init__(
        self, region: DrawnRectangle, colors, selected: bool,
        on_select, on_move, on_edge_move, on_move_end, on_drag_start=None,
        get_view_scale=None, parent=None,
    ):
        super().__init__(parent)
        self.region = region
        self.colors = colors
        self.selected = selected
        self.on_select = on_select
        self.on_move = on_move
        self.on_edge_move = on_edge_move
        self.on_move_end = on_move_end
        self.on_drag_start = on_drag_start
        self.get_view_scale = get_view_scale or (lambda: 1.0)
        self._dragging = False
        self._drag_edge: str | None = None
        self._drag_start = None
        self._orig = None
        self.setZValue(5)
        self.setAcceptHoverEvents(True)

    def boundingRect(self) -> QRectF:
        left, top, right, bottom = region_bounds(
            self.region.cx, self.region.cy, self.region.width, self.region.height,
        )
        pad = 2.0
        return QRectF(left - pad, top - pad, right - left + 2 * pad, bottom - top + 2 * pad)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None):
        r = self.region
        left, top, right, bottom = region_bounds(r.cx, r.cy, r.width, r.height)
        sel_color = self.colors["selection"]
        border = QColor(sel_color if self.selected else r.color)
        border.setAlpha(220)
        painter.setPen(QPen(border, 1.5 if self.selected else 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(left, top, right - left, bottom - top))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.on_select(self.region.id, notify=False)
            pos = event.scenePos()
            edge = hit_region_edge(
                pos.x(), pos.y(), self.region.cx, self.region.cy,
                self.region.width, self.region.height, self.get_view_scale(),
            )
            self._drag_edge = edge
            self._dragging = edge is None
            self._drag_start = pos
            self._orig = (self.region.cx, self.region.cy)
            if self.on_drag_start:
                self.on_drag_start(self.region.id)
            self.grabMouse()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_edge and self._drag_start is not None:
            pos = event.scenePos()
            cx, cy, w, h = self.on_edge_move(self.region.id, self._drag_edge, pos.x(), pos.y())
            self.region.cx, self.region.cy = cx, cy
            self.region.width, self.region.height = w, h
            self.prepareGeometryChange()
            self.update()
            event.accept()
            return
        if self._dragging and self._orig:
            delta = event.scenePos() - self._drag_start
            nx, ny = self.on_move(
                self.region.id, self._orig[0] + delta.x(), self._orig[1] + delta.y(),
            )
            self.region.cx, self.region.cy = nx, ny
            self.prepareGeometryChange()
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging or self._drag_edge:
            self._dragging = False
            self._drag_edge = None
            self.ungrabMouse()
            if self.on_move_end:
                self.on_move_end(self.region.id)
            event.accept()
            return
        super().mouseReleaseEvent(event)
