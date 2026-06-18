from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QPen
from PyQt6.QtWidgets import QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsTextItem

from app.formatting import format_dim
from app.models.base import ContourKind


class ToolPlacementPreview:
    """Temporary graphics shown while placing holes, arrays, aux lines, rectangles."""

    def __init__(self, scene) -> None:
        self.scene = scene
        self._shape_items: list = []
        self._dim_items: list = []

    def on_scene_cleared(self) -> None:
        self._shape_items.clear()
        self._dim_items.clear()

    def clear(self) -> None:
        for item in self._shape_items + self._dim_items:
            self.scene.removeItem(item)
        self._shape_items.clear()
        self._dim_items.clear()

    def clear_dims(self) -> None:
        for item in self._dim_items:
            self.scene.removeItem(item)
        self._dim_items.clear()

    def _add_shape(self, item) -> None:
        item.setZValue(95)
        self.scene.addItem(item)
        self._shape_items.append(item)

    def _add_dim(self, item) -> None:
        item.setZValue(96)
        self.scene.addItem(item)
        self._dim_items.append(item)

    def _line(self, x1: float, y1: float, x2: float, y2: float, color: str, dashed: bool = True) -> None:
        pen = QPen(QColor(color))
        pen.setCosmetic(True)
        if dashed:
            pen.setStyle(Qt.PenStyle.DashLine)
        item = QGraphicsLineItem(x1, y1, x2, y2)
        item.setPen(pen)
        self._add_dim(item)

    def _label(self, x: float, y: float, text: str, color: str) -> None:
        item = QGraphicsTextItem(text)
        item.setDefaultTextColor(QColor(color))
        item.setFont(QFont("", 9))
        item.setPos(x, y)
        self._add_dim(item)

    def show_hole(self, document, cx: float, cy: float, diameter: float, color: str) -> None:
        self.clear()
        r = diameter / 2
        pen = QPen(QColor(color))
        pen.setCosmetic(True)
        ellipse = QGraphicsEllipseItem(cx - r, cy - r, diameter, diameter)
        ellipse.setPen(pen)
        ellipse.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        self._add_shape(ellipse)
        self._position_dims(document, cx, cy, color)

    def show_holes(self, document, positions: list[tuple[float, float]], diameter: float, color: str) -> None:
        self.clear()
        for cx, cy in positions:
            r = diameter / 2
            pen = QPen(QColor(color))
            pen.setCosmetic(True)
            ellipse = QGraphicsEllipseItem(cx - r, cy - r, diameter, diameter)
            ellipse.setPen(pen)
            ellipse.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            self._add_shape(ellipse)
        if positions:
            self._position_dims(document, positions[-1][0], positions[-1][1], color)

    def show_array_grid(
        self, positions: list[tuple[float, float]], diameter: float, color: str,
    ) -> None:
        self.clear()
        for cx, cy in positions:
            r = diameter / 2
            pen = QPen(QColor(color))
            pen.setCosmetic(True)
            ellipse = QGraphicsEllipseItem(cx - r, cy - r, diameter, diameter)
            ellipse.setPen(pen)
            ellipse.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            self._add_shape(ellipse)
        if len(positions) < 2:
            return
        x0, y0 = positions[0]
        x1, y1 = positions[1]
        xn, yn = positions[-1]
        step = math.hypot(x1 - x0, y1 - y0)
        span = math.hypot(xn - x0, yn - y0)
        dim_top = min(p[1] for p in positions) - 14.0
        dim_bot = max(p[1] for p in positions) + 22.0
        self._horizontal_dim(x0, x1, dim_top, format_dim(step), color)
        self._horizontal_dim(x0, xn, dim_bot, format_dim(span), color)

    def _position_dims(self, document, cx: float, cy: float, color: str) -> None:
        ccx, ccy = document.contour_center()
        if document.contour_kind == ContourKind.CIRCLE:
            ox, oy = cx - ccx, cy - ccy
            self._horizontal_dim(ccx, cx, ccy, format_dim(ox), color)
            self._vertical_dim(ccy, cy, ccx, format_dim(oy), color)
        else:
            self._horizontal_dim(0, cx, 0, format_dim(cx), color)
            self._vertical_dim(0, cy, 0, format_dim(cy), color)

    def _horizontal_dim(self, x1: float, x2: float, y: float, text: str, color: str) -> None:
        off = 12.0
        self._line(x1, y, x2, y, color)
        self._line(x1, y, x1, y + off, color, dashed=False)
        self._line(x2, y, x2, y + off, color, dashed=False)
        self._line(x1, y + off, x2, y + off, color, dashed=False)
        self._label((x1 + x2) / 2 - 12, y + off + 2, text, color)

    def _vertical_dim(self, y1: float, y2: float, x: float, text: str, color: str) -> None:
        off = 12.0
        self._line(x, y1, x, y2, color)
        self._line(x, y1, x - off, y1, color, dashed=False)
        self._line(x, y2, x - off, y2, color, dashed=False)
        self._line(x - off, y1, x - off, y2, color, dashed=False)
        self._label(x - off - 28, (y1 + y2) / 2 - 6, text, color)

    def show_aux_distance(
        self, src: tuple[float, float, float, float], offset: float, color: str = "#868e96",
    ) -> None:
        from app.geometry.line_math import segment_midpoint, parallel_segment

        self.clear_dims()
        x1, y1, x2, y2 = parallel_segment(*src, offset)
        self._line(x1, y1, x2, y2, color)
        smx, smy = segment_midpoint(src[0], src[1], src[2], src[3])
        mx, my = segment_midpoint(x1, y1, x2, y2)
        self._line(smx, smy, mx, my, color, dashed=False)
        dist = abs(offset)
        self._label((smx + mx) / 2 + 4, (smy + my) / 2 + 4, format_dim(dist), color)

    def show_rect(self, left: float, top: float, right: float, bottom: float, color: str = "#495057") -> None:
        self.clear()
        w, h = right - left, bottom - top
        if w < 1e-6 or h < 1e-6:
            return
        pen = QPen(QColor(color))
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        from PyQt6.QtWidgets import QGraphicsRectItem
        from PyQt6.QtCore import QRectF

        rect = QGraphicsRectItem(QRectF(left, top, w, h))
        rect.setPen(pen)
        rect.setBrush(QBrush(QColor(73, 80, 87, 40)))
        self._add_shape(rect)
        self._horizontal_dim(left, right, bottom, format_dim(w), color)
        self._vertical_dim(top, bottom, right, format_dim(h), color)
