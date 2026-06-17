from __future__ import annotations

from PyQt6.QtCore import QLineF, QRectF, Qt
from PyQt6.QtGui import QColor, QPen, QPainter
from PyQt6.QtWidgets import QGraphicsObject, QStyleOptionGraphicsItem, QWidget

from app.geometry.infinite_line_bind import infinite_line_geometry
from app.geometry.line_math import clip_infinite_line
from app.models.base import InfiniteLine


class InfiniteLineGraphicsItem(QGraphicsObject):
    def __init__(
        self, line: InfiniteLine, colors, selected: bool,
        on_select, on_move, on_move_end, parent=None,
    ):
        super().__init__(parent)
        self.line = line
        self.colors = colors
        self.selected = selected
        self.on_select = on_select
        self.on_move = on_move
        self.on_move_end = on_move_end
        self._dragging = False
        self._drag_start = None
        self.setZValue(4)
        self.setAcceptHoverEvents(True)

    def boundingRect(self) -> QRectF:
        x1, y1, x2, y2 = infinite_line_geometry(self.line)
        pad = 20.0
        return QRectF(
            min(x1, x2) - pad, min(y1, y2) - pad,
            abs(x2 - x1) + 2 * pad, abs(y2 - y1) + 2 * pad,
        )

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None):
        line = self.line
        x1, y1, x2, y2 = infinite_line_geometry(line)
        br = self.scene().sceneRect() if self.scene() else QRectF(-10000, -10000, 20000, 20000)
        clipped = clip_infinite_line(x1, y1, x2, y2, br.left(), br.top(), br.right(), br.bottom())
        if clipped is None:
            return
        cx1, cy1, cx2, cy2 = clipped
        color = QColor(self.colors["selection"] if self.selected else line.color)
        pen = QPen(color, 1.5 if self.selected else 1.0)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawLine(QLineF(cx1, cy1, cx2, cy2))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.on_select(self.line.id, notify=False)
            if not self.line.locked:
                self._dragging = True
                self._drag_start = event.scenePos()
                self.grabMouse()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and self._drag_start is not None and not self.line.locked:
            delta = event.scenePos() - self._drag_start
            self.on_move(self.line.id, delta.x(), delta.y())
            self._drag_start = event.scenePos()
            self.prepareGeometryChange()
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self.ungrabMouse()
            if self.on_move_end:
                self.on_move_end(self.line.id)
            event.accept()
            return
        super().mouseReleaseEvent(event)
