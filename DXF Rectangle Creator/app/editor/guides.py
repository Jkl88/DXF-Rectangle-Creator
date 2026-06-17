from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPen
from PyQt6.QtWidgets import QGraphicsObject

Guide = tuple  # ('v', x) | ('h', y) | ('p', x, y) | ('seg', x1, y1, x2, y2)


class SnapGuideItem(QGraphicsObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._guides: list[Guide] = []
        self._bounds = QRectF()
        self.setZValue(100)

    def set_guides(self, guides: list[Guide], bounds: QRectF) -> None:
        self._guides = guides
        self._bounds = bounds
        self.prepareGeometryChange()
        self.update()

    def clear(self) -> None:
        self.set_guides([], QRectF())

    def boundingRect(self):
        if self._bounds.isValid():
            return self._bounds
        return QRectF()

    def paint(self, painter, option, widget=None):
        if not self._guides or not self._bounds.isValid():
            return
        align_pen = QPen(QColor("#a8a8a8"))
        align_pen.setStyle(Qt.PenStyle.DashLine)
        align_pen.setCosmetic(True)
        align_pen.setWidth(1)
        seg_pen = QPen(QColor("#909090"))
        seg_pen.setCosmetic(True)
        seg_pen.setWidth(1)
        x0, y0 = self._bounds.left(), self._bounds.top()
        x1, y1 = self._bounds.right(), self._bounds.bottom()
        for guide in self._guides:
            if guide[0] == "v":
                x = guide[1]
                painter.setPen(align_pen)
                painter.drawLine(QPointF(x, y0), QPointF(x, y1))
            elif guide[0] == "h":
                y = guide[1]
                painter.setPen(align_pen)
                painter.drawLine(QPointF(x0, y), QPointF(x1, y))
            elif guide[0] == "p":
                px, py = guide[1], guide[2]
                painter.setPen(align_pen)
                painter.drawLine(QPointF(px, y0), QPointF(px, y1))
                painter.drawLine(QPointF(x0, py), QPointF(x1, py))
            elif guide[0] == "seg":
                painter.setPen(seg_pen)
                painter.drawLine(
                    QPointF(guide[1], guide[2]),
                    QPointF(guide[3], guide[4]),
                )
