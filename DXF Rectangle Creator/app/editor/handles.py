from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem, QGraphicsObject


class PlacementCrosshairItem(QGraphicsObject):
    """Crosshair preview while placing DXF datum origin."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setZValue(100)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)

    def boundingRect(self) -> QRectF:
        return QRectF(-14, -14, 28, 28)

    def paint(self, painter, option, widget=None) -> None:
        pen = QPen(QColor("#ff6b00"))
        pen.setCosmetic(True)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawLine(QPointF(-12, 0), QPointF(12, 0))
        painter.drawLine(QPointF(0, -12), QPointF(0, 12))


class OriginHandle(QGraphicsObject):
    """Fixed datum origin marker for imported DXF contours (re-place via properties)."""

    def __init__(self, document, on_select, parent=None):
        super().__init__(parent)
        self.document = document
        self.on_select = on_select
        self.setZValue(25)
        self.setAcceptHoverEvents(True)

    def boundingRect(self) -> QRectF:
        return QRectF(-12, -12, 24, 24)

    def paint(self, painter, option, widget=None) -> None:
        from app.models.base import SelectionKind
        selected = self.document.selection.kind == SelectionKind.ORIGIN
        color = QColor("#ff6b00") if selected else QColor("#888888")
        pen = QPen(color)
        pen.setCosmetic(True)
        pen.setWidth(2 if selected else 1)
        painter.setPen(pen)
        painter.drawLine(QPointF(-10, 0), QPointF(10, 0))
        painter.drawLine(QPointF(0, -10), QPointF(0, 10))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.on_select(notify=False)
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)


class ArrayCenterHandle(QGraphicsEllipseItem):
    """Ручка центра кругового массива."""

    def __init__(self, array_id, cx, cy, on_move, on_move_end, on_drag_start=None, parent=None):
        super().__init__(-5, -5, 10, 10, parent)
        self.array_id = array_id
        self.on_move = on_move
        self.on_move_end = on_move_end
        self.on_drag_start = on_drag_start
        self.setPos(cx, cy)
        self.setBrush(Qt.GlobalColor.cyan)
        pen = QPen(Qt.GlobalColor.darkCyan)
        pen.setCosmetic(True)
        self.setPen(pen)
        self.setZValue(20)
        self._dragging = False
        self._drag_start = None
        self._orig: tuple[float, float] | None = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.on_drag_start:
                self.on_drag_start(self.array_id)
            self._dragging = True
            self._drag_start = event.scenePos()
            self._orig = (self.pos().x(), self.pos().y())
            self.grabMouse()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and self._orig is not None:
            delta = event.scenePos() - self._drag_start
            nx = self._orig[0] + delta.x()
            ny = self._orig[1] + delta.y()
            sx, sy = self.on_move(self.array_id, nx, ny)
            self.setPos(sx, sy)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging and self._orig is not None:
            delta = event.scenePos() - self._drag_start
            self._dragging = False
            self.ungrabMouse()
            event.accept()
            nx = self._orig[0] + delta.x()
            ny = self._orig[1] + delta.y()
            self.on_move_end(self.array_id, nx, ny)
            return
        super().mouseReleaseEvent(event)
