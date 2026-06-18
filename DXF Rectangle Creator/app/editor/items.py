from __future__ import annotations

import math
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPen, QPainterPath, QPainterPathStroker, QTransform
from PyQt6.QtWidgets import QGraphicsObject

from app.editor.snap import snap_dim_offset
from app.geometry.slot import add_slot_path, slot_geom
from app.models.base import CornerMode, HoleKind

TEXT_OFF = 2
DIM_TICK_HALF = 1.1
DIM_OVERSHOOT = 1.5
_OPPOSITE_SIDE = {"bottom": "top", "top": "bottom", "left": "right", "right": "left"}


def tick_dir_45(ux: float, uy: float) -> tuple[float, float]:
    """Unit direction at 45° to the reference line."""
    ln = math.hypot(ux, uy) or 1.0
    ux, uy = ux / ln, uy / ln
    c = math.sqrt(0.5)
    return ux * c - uy * c, ux * c + uy * c


def _extend_past(x1: float, y1: float, x2: float, y2: float, extra: float) -> tuple[float, float]:
    dx, dy = x2 - x1, y2 - y1
    ln = math.hypot(dx, dy) or 1.0
    return x2 + dx / ln * extra, y2 + dy / ln * extra


class ContourGraphicsItem(QGraphicsObject):
    def __init__(self, document, colors, on_select, parent=None):
        super().__init__(parent)
        self.document = document
        self.colors = colors
        self.on_select = on_select
        self.setZValue(1)
        self.setAcceptHoverEvents(True)

    def boundingRect(self):
        x, y, w, h = self.document.contour_bounds()
        pad = 20
        return QRectF(x - pad, y - pad, w + 2 * pad, h + 2 * pad)

    def paint(self, painter, option, widget=None):
        from app.geometry.dxf_entities import paint_entities
        from app.models.base import ContourKind
        doc = self.document
        selected = doc.selection.kind.value == "contour"
        pen = QPen(self.colors["selection"] if selected else self.colors["contour"])
        pen.setCosmetic(True)
        # Make the contour visually stronger than helper/guide lines.
        pen.setWidth(3 if selected else 2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if doc.contour_kind == ContourKind.DXF:
            paint_entities(painter, doc.dxf_contour.entities, pen)
            return
        if doc.contour_kind == ContourKind.CIRCLE:
            d = doc.circle.diameter
            painter.drawEllipse(QRectF(0, 0, d, d))
        else:
            r = doc.rect
            if r.corner_size <= 0:
                painter.drawRect(QRectF(0, 0, r.width, r.height))
            elif r.corner_mode == CornerMode.CHAMFER:
                c = r.corner_size
                w, h = r.width, r.height
                path = QPainterPath()
                path.moveTo(c, 0)
                path.lineTo(w - c, 0)
                path.lineTo(w, c)
                path.lineTo(w, h - c)
                path.lineTo(w - c, h)
                path.lineTo(c, h)
                path.lineTo(0, h - c)
                path.lineTo(0, c)
                path.closeSubpath()
                painter.drawPath(path)
            else:
                path = QPainterPath()
                path.addRoundedRect(0, 0, r.width, r.height, r.corner_size, r.corner_size)
                painter.drawPath(path)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.on_select("contour", "")
            event.accept()
            return
        super().mousePressEvent(event)


class HoleGraphicsItem(QGraphicsObject):
    def __init__(self, source_hole_id, instance_index, resolved, hole_color, colors, selected,
                 draggable, on_select, on_move, on_move_end, on_drag_start=None, parent=None):
        super().__init__(parent)
        self.source_hole_id = source_hole_id
        self.instance_index = instance_index
        self.resolved = resolved
        self.hole_color = hole_color
        self.colors = colors
        self.selected = selected
        self.draggable = draggable
        self.on_select = on_select
        self.on_move = on_move
        self.on_move_end = on_move_end
        self.on_drag_start = on_drag_start
        self._dragging = False
        self._drag_start = None
        self._orig = None
        self.setZValue(5)
        self.setAcceptHoverEvents(True)

    def boundingRect(self):
        rh = self.resolved
        if rh.kind == HoleKind.CIRCLE:
            r = rh.diameter / 2
            return QRectF(rh.cx - r - 4, rh.cy - r - 4, rh.diameter + 8, rh.diameter + 8)
        if rh.kind == HoleKind.OVAL:
            g = slot_geom(rh.width, rh.height)
            pad = 4
            lo, sh = g.long_outer, g.cap
            return QRectF(rh.cx - lo / 2 - pad, rh.cy - sh / 2 - pad, lo + 2 * pad, sh + 2 * pad)
        return QRectF(rh.cx - rh.width / 2 - 4, rh.cy - rh.height / 2 - 4, rh.width + 8, rh.height + 8)

    def _outline_path(self) -> QPainterPath:
        rh = self.resolved
        path = QPainterPath()
        if rh.kind == HoleKind.CIRCLE:
            path.addEllipse(QRectF(rh.cx - rh.diameter / 2, rh.cy - rh.diameter / 2, rh.diameter, rh.diameter))
        else:
            sub = QPainterPath()
            if rh.kind == HoleKind.RECT:
                sub.addRect(QRectF(-rh.width / 2, -rh.height / 2, rh.width, rh.height))
            elif rh.kind == HoleKind.OVAL:
                add_slot_path(sub, rh.width, rh.height)
            else:
                sides = max(3, rh.sides)
                r = rh.diameter / 2
                for i in range(sides):
                    a = math.radians(360 * i / sides - 90)
                    px, py = r * math.cos(a), r * math.sin(a)
                    if i == 0:
                        sub.moveTo(px, py)
                    else:
                        sub.lineTo(px, py)
                sub.closeSubpath()
            transform = QTransform()
            transform.translate(rh.cx, rh.cy)
            transform.rotate(rh.angle)
            path = transform.map(sub)
        return path

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(8)
        return stroker.createStroke(self._outline_path())

    def paint(self, painter, option, widget=None):
        rh = self.resolved
        color = QColor(self.hole_color)
        pen = QPen(self.colors["selection"] if self.selected else color)
        pen.setCosmetic(True)
        if self.selected:
            pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.save()
        painter.translate(rh.cx, rh.cy)
        painter.rotate(rh.angle)
        if rh.kind == HoleKind.CIRCLE:
            painter.drawEllipse(QRectF(-rh.diameter / 2, -rh.diameter / 2, rh.diameter, rh.diameter))
        elif rh.kind == HoleKind.RECT:
            painter.drawRect(QRectF(-rh.width / 2, -rh.height / 2, rh.width, rh.height))
        elif rh.kind == HoleKind.OVAL:
            path = QPainterPath()
            add_slot_path(path, rh.width, rh.height)
            painter.drawPath(path)
        else:
            sides = max(3, rh.sides)
            r = rh.diameter / 2
            path = QPainterPath()
            for i in range(sides):
                a = math.radians(360 * i / sides - 90)
                px, py = r * math.cos(a), r * math.sin(a)
                if i == 0:
                    path.moveTo(px, py)
                else:
                    path.lineTo(px, py)
            path.closeSubpath()
            painter.drawPath(path)
        painter.restore()
        if self.selected:
            painter.setPen(QPen(self.colors["selection"]))
            painter.drawLine(QPointF(rh.cx - 6, rh.cy), QPointF(rh.cx + 6, rh.cy))
            painter.drawLine(QPointF(rh.cx, rh.cy - 6), QPointF(rh.cx, rh.cy + 6))

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.on_select(self.source_hole_id, self.instance_index, notify=False)
            if not self.draggable:
                event.accept()
                return
            self._dragging = True
            self._drag_start = event.scenePos()
            self._orig = (self.resolved.cx, self.resolved.cy)
            if self.on_drag_start:
                self.on_drag_start(self.source_hole_id, self.instance_index)
            self.grabMouse()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and self._orig:
            delta = event.scenePos() - self._drag_start
            nx, ny = self._orig[0] + delta.x(), self._orig[1] + delta.y()
            sx, sy = self.on_move(self.source_hole_id, self.instance_index, nx, ny)
            self.resolved.cx, self.resolved.cy = sx, sy
            self.prepareGeometryChange()
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if not self.draggable and event.button() == Qt.MouseButton.LeftButton:
            self.on_select(self.source_hole_id, self.instance_index, notify=True)
            event.accept()
            return
        if self._dragging and self._orig:
            delta = event.scenePos() - self._drag_start
            self._dragging = False
            self.ungrabMouse()
            event.accept()
            moved = math.hypot(delta.x(), delta.y()) > 2
            if moved:
                nx, ny = self._orig[0] + delta.x(), self._orig[1] + delta.y()
                self.on_move_end(self.source_hole_id, self.instance_index, nx, ny)
            else:
                self.on_select(self.source_hole_id, self.instance_index, notify=True)
            return
        super().mouseReleaseEvent(event)


class DimGraphicsItem(QGraphicsObject):
    def __init__(self, dim_id, side, a1, a2, ref, text, color, font, offset, snap_offsets,
                 on_select, on_offset, on_offset_end, ext1=None, ext2=None,
                 pt1=None, pt2=None, line_anchor=None, get_snap_targets=None,
                 on_edit=None, selected=False, selection_color=None, locked=False, parent=None):
        super().__init__(parent)
        self.dim_id = dim_id
        self.side = side
        self.a1 = min(a1, a2)
        self.a2 = max(a1, a2)
        self.ref = ref
        self.ext1 = ref if ext1 is None else ext1
        self.ext2 = ref if ext2 is None else ext2
        self.pt1 = QPointF(pt1[0], pt1[1]) if pt1 is not None else None
        self.pt2 = QPointF(pt2[0], pt2[1]) if pt2 is not None else None
        self.line_anchor = line_anchor
        self.text = text
        self.color = QColor(color)
        self.font = QFont(font)
        self.offset = offset
        self.snap_offsets = snap_offsets
        self.get_snap_targets = get_snap_targets
        self.on_select = on_select
        self.on_offset = on_offset
        self.on_offset_end = on_offset_end
        self.on_edit = on_edit
        self.selected = selected
        self.selection_color = QColor(selection_color) if selection_color else None
        self.locked = locked
        self._dragging = False
        self._drag_start_offset = offset
        self._drag_start_pos = None
        self.setZValue(10)
        self.setAcceptHoverEvents(True)

    @property
    def _is_angled(self) -> bool:
        return self.pt1 is not None and self.pt2 is not None

    def update_geometry(
        self, a1: float, a2: float, ref: float, text: str,
        ext1: float | None = None, ext2: float | None = None,
        pt1: tuple[float, float] | None = None, pt2: tuple[float, float] | None = None,
    ) -> None:
        """Update span/text; ref fixes dim-line position, ext1/ext2 reach measured points."""
        if not self._is_angled:
            self.a1 = min(a1, a2)
            self.a2 = max(a1, a2)
            self.ref = ref
            if ext1 is not None:
                self.ext1 = ext1
            if ext2 is not None:
                self.ext2 = ext2
        if pt1 is not None and pt2 is not None:
            self.pt1 = QPointF(pt1[0], pt1[1])
            self.pt2 = QPointF(pt2[0], pt2[1])
        self.text = text
        self.prepareGeometryChange()
        self.update()

    def _offset_from_lp(self, lp: float) -> float:
        if self.side == "bottom":
            return max(3.0, lp - self.ref)
        if self.side == "top":
            return max(3.0, self.ref - lp)
        if self.side == "left":
            return max(3.0, self.ref - lp)
        return max(3.0, lp - self.ref)

    def _perp_for_side(self, ux: float, uy: float) -> tuple[float, float]:
        nx, ny = -uy, ux
        if self.side == "top" and ny > 0:
            nx, ny = -nx, -ny
        elif self.side == "bottom" and ny < 0:
            nx, ny = -nx, -ny
        elif self.side == "left" and nx > 0:
            nx, ny = -nx, -ny
        elif self.side == "right" and nx < 0:
            nx, ny = -nx, -ny
        return nx, ny

    def _dim_vectors(self) -> tuple[float, float, float, float]:
        if self._is_angled:
            dx = self.pt2.x() - self.pt1.x()
            dy = self.pt2.y() - self.pt1.y()
        else:
            if self.side in ("top", "bottom"):
                dx, dy = self.a2 - self.a1, 0.0
            else:
                dx, dy = 0.0, self.a2 - self.a1
        ln = math.hypot(dx, dy) or 1.0
        ux, uy = dx / ln, dy / ln
        nx, ny = self._perp_for_side(ux, uy)
        return ux, uy, nx, ny

    def _line_pos(self):
        if self.side == "bottom":
            return self.ref + self.offset
        if self.side == "top":
            return self.ref - self.offset
        if self.side == "left":
            return self.ref - self.offset
        return self.ref + self.offset

    @staticmethod
    def _project_to_line(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> tuple[float, float]:
        dx, dy = x2 - x1, y2 - y1
        ln2 = dx * dx + dy * dy
        if ln2 < 1e-12:
            return x1, y1
        t = ((px - x1) * dx + (py - y1) * dy) / ln2
        return x1 + t * dx, y1 + t * dy

    def _shelf_pos(self) -> float:
        """Perpendicular coordinate of the dimension line (полка) for snap alignment."""
        if not self._is_angled:
            return self._line_pos()
        _, info = self._layout()
        d1x, d1y, d2x, d2y, _, _ = info
        if self.side in ("top", "bottom"):
            return (d1y + d2y) / 2
        return (d1x + d2x) / 2

    def _offset_for_shelf(self, shelf: float) -> float:
        if not self._is_angled:
            return self._offset_from_lp(shelf)
        _, _, nx, ny = self._dim_vectors()
        p1 = self.pt1
        if self.side in ("top", "bottom"):
            if abs(ny) > 1e-6:
                return max(3.0, (shelf - p1.y()) / ny)
        elif abs(nx) > 1e-6:
            return max(3.0, (shelf - p1.x()) / nx)
        return self.offset

    def current_line_anchor(self) -> tuple[float, float, float, float]:
        """Dim-line endpoints in scene coords (offset-based layout, ignores stored anchor)."""
        saved = self.line_anchor
        self.line_anchor = None
        try:
            _, info = self._layout_free()
            return info[:4]
        finally:
            self.line_anchor = saved

    def _layout_free(self) -> tuple[list, tuple]:
        p1, p2 = self.pt1, self.pt2
        ux, uy, nx, ny = self._dim_vectors()
        ov = DIM_OVERSHOOT
        if self.line_anchor is not None:
            d1x, d1y, d2x, d2y = self.line_anchor
            f1x, f1y = self._project_to_line(p1.x(), p1.y(), d1x, d1y, d2x, d2y)
            f2x, f2y = self._project_to_line(p2.x(), p2.y(), d1x, d1y, d2x, d2y)
            e1x, e1y = _extend_past(p1.x(), p1.y(), f1x, f1y, ov)
            e2x, e2y = _extend_past(p2.x(), p2.y(), f2x, f2y, ov)
            lines = [
                (p1.x(), p1.y(), e1x, e1y),
                (p2.x(), p2.y(), e2x, e2y),
                (d1x - ux * ov, d1y - uy * ov, d2x + ux * ov, d2y + uy * ov),
            ]
            return lines, (d1x, d1y, d2x, d2y, ux, uy)
        o = self.offset
        d1x, d1y = p1.x() + nx * o, p1.y() + ny * o
        d2x, d2y = p2.x() + nx * o, p2.y() + ny * o
        e1x, e1y = _extend_past(p1.x(), p1.y(), d1x, d1y, ov)
        e2x, e2y = _extend_past(p2.x(), p2.y(), d2x, d2y, ov)
        lines = [
            (p1.x(), p1.y(), e1x, e1y),
            (p2.x(), p2.y(), e2x, e2y),
            (d1x - ux * ov, d1y - uy * ov, d2x + ux * ov, d2y + uy * ov),
        ]
        return lines, (d1x, d1y, d2x, d2y, ux, uy)

    def _layout(self):
        if self._is_angled:
            return self._layout_free()
        lp = self._line_pos()
        ov = DIM_OVERSHOOT
        lines = []
        if self.side in ("bottom", "top"):
            sign = 1.0 if self.side == "bottom" else -1.0
            lines += [
                (self.a1, self.ext1, self.a1, lp + sign * ov),
                (self.a2, self.ext2, self.a2, lp + sign * ov),
                (self.a1 - ov, lp, self.a2 + ov, lp),
            ]
        else:
            sign = 1.0 if self.side == "right" else -1.0
            lines += [
                (self.ext1, self.a1, lp + sign * ov, self.a1),
                (self.ext2, self.a2, lp + sign * ov, self.a2),
                (lp, self.a1 - ov, lp, self.a2 + ov),
            ]
        return lines, lp

    def _snap_targets(self) -> list[float]:
        if self.get_snap_targets:
            return self.get_snap_targets()
        return list(self.snap_offsets)

    def _apply_offset_snap(self, off: float) -> float:
        targets = self._snap_targets()
        if not targets:
            return off
        if self._is_angled:
            shelf = self._shelf_for_offset(off)
            snapped = snap_dim_offset(shelf, targets)
            return self._offset_for_shelf(snapped)
        lp = self._offset_to_lp(off)
        snapped_lp = snap_dim_offset(lp, targets)
        return self._offset_from_lp(snapped_lp)

    def _offset_to_lp(self, off: float) -> float:
        if self.side == "bottom":
            return self.ref + off
        if self.side == "top":
            return self.ref - off
        if self.side == "left":
            return self.ref - off
        return self.ref + off

    def _shelf_for_offset(self, off: float) -> float:
        if not self._is_angled:
            return self._offset_to_lp(off)
        _, _, nx, ny = self._dim_vectors()
        p1, p2 = self.pt1, self.pt2
        if self.side in ("top", "bottom"):
            return (p1.y() + ny * off + p2.y() + ny * off) / 2
        return (p1.x() + nx * off + p2.x() + nx * off) / 2

    def _paint_angled_text(self, painter, d1x: float, d1y: float, d2x: float, d2y: float,
                           ux: float, uy: float, tw: int, th: int, metrics) -> None:
        """Place text like axis dims for the same side/orientation."""
        mx, my = (d1x + d2x) / 2, (d1y + d2y) / 2
        if abs(ux) >= abs(uy):
            if self.side == "top":
                painter.drawText(QPointF(mx - tw / 2, my - TEXT_OFF - th + metrics.ascent()), self.text)
            elif self.side == "bottom":
                painter.drawText(QPointF(mx - tw / 2, my + TEXT_OFF + metrics.ascent()), self.text)
            else:
                angle = math.degrees(math.atan2(uy, ux))
                _, _, nx, ny = self._dim_vectors()
                tx, ty = mx + nx * TEXT_OFF, my + ny * TEXT_OFF
                painter.save()
                painter.translate(tx, ty)
                painter.rotate(angle)
                painter.drawText(QPointF(-tw / 2, metrics.ascent()), self.text)
                painter.restore()
        elif self.side == "left":
            painter.save()
            painter.translate(mx - TEXT_OFF - th, my + tw / 2)
            painter.rotate(-90)
            painter.drawText(QPointF(0, metrics.ascent()), self.text)
            painter.restore()
        elif self.side == "right":
            painter.save()
            painter.translate(mx + TEXT_OFF, my + tw / 2)
            painter.rotate(-90)
            painter.drawText(QPointF(0, metrics.ascent()), self.text)
            painter.restore()
        else:
            angle = math.degrees(math.atan2(uy, ux))
            _, _, nx, ny = self._dim_vectors()
            tx, ty = mx + nx * TEXT_OFF, my + ny * TEXT_OFF
            painter.save()
            painter.translate(tx, ty)
            painter.rotate(angle)
            painter.drawText(QPointF(-tw / 2, metrics.ascent()), self.text)
            painter.restore()

    def _text_rect_angled(self, d1x: float, d1y: float, d2x: float, d2y: float,
                          ux: float, uy: float, tw: int, th: int) -> QRectF:
        mx, my = (d1x + d2x) / 2, (d1y + d2y) / 2
        if abs(ux) >= abs(uy):
            if self.side == "top":
                return QRectF(mx - tw / 2, my - TEXT_OFF - th, tw, th)
            if self.side == "bottom":
                return QRectF(mx - tw / 2, my + TEXT_OFF, tw, th)
        if self.side == "left":
            return QRectF(mx - TEXT_OFF - th, my - tw / 2, th, tw)
        if self.side == "right":
            return QRectF(mx + TEXT_OFF, my - tw / 2, th, tw)
        return QRectF(mx - tw / 2, my - th / 2, tw, th)

    def boundingRect(self):
        layout = self._layout()
        lines = layout[0]
        rect = QRectF()
        for x1, y1, x2, y2 in lines:
            rect = rect.united(QRectF(QPointF(x1, y1), QPointF(x2, y2)))
        rect = rect.united(self._text_rect())
        return rect.adjusted(-4, -4, 4, 4)

    def _dim_tick_marks(self) -> list[tuple[float, float, float, float]]:
        if self._is_angled:
            layout = self._layout()
            d1x, d1y, d2x, d2y, ux, uy = layout[1]
            tx, ty = tick_dir_45(ux, uy)
            return [(d1x, d1y, tx, ty), (d2x, d2y, tx, ty)]
        lp = self._layout()[1]
        if self.side in ("bottom", "top"):
            tx, ty = tick_dir_45(1.0, 0.0)
            return [(self.a1, lp, tx, ty), (self.a2, lp, tx, ty)]
        tx, ty = tick_dir_45(0.0, 1.0)
        return [(lp, self.a1, tx, ty), (lp, self.a2, tx, ty)]

    def _draw_color(self) -> QColor:
        if self.selected and self.selection_color is not None:
            return self.selection_color
        return self.color

    def paint(self, painter, option, widget=None):
        layout = self._layout()
        lines = layout[0]
        pen = QPen(self._draw_color())
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setFont(self.font)
        for x1, y1, x2, y2 in lines:
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        tick_pen = QPen(self._draw_color())
        tick_pen.setCosmetic(True)
        painter.setPen(tick_pen)
        for x, y, tx, ty in self._dim_tick_marks():
            ln = math.hypot(tx, ty) or 1.0
            ux, uy = tx / ln, ty / ln
            painter.drawLine(
                QPointF(x - ux * DIM_TICK_HALF, y - uy * DIM_TICK_HALF),
                QPointF(x + ux * DIM_TICK_HALF, y + uy * DIM_TICK_HALF),
            )
        painter.setPen(pen)
        metrics = painter.fontMetrics()
        tw, th = metrics.horizontalAdvance(self.text), metrics.height()
        if self._is_angled:
            d1x, d1y, d2x, d2y, ux, uy = layout[1]
            self._paint_angled_text(painter, d1x, d1y, d2x, d2y, ux, uy, tw, th, metrics)
            return
        lp = layout[1]
        if self.side == "bottom":
            painter.drawText(QPointF((self.a1 + self.a2) / 2 - tw / 2, lp + TEXT_OFF + metrics.ascent()), self.text)
        elif self.side == "top":
            painter.drawText(QPointF((self.a1 + self.a2) / 2 - tw / 2, lp - TEXT_OFF - th + metrics.ascent()), self.text)
        elif self.side == "left":
            painter.save()
            painter.translate(lp - TEXT_OFF - th, (self.a1 + self.a2) / 2 + tw / 2)
            painter.rotate(-90)
            painter.drawText(QPointF(0, metrics.ascent()), self.text)
            painter.restore()
        else:
            painter.save()
            painter.translate(lp + TEXT_OFF, (self.a1 + self.a2) / 2 + tw / 2)
            painter.rotate(-90)
            painter.drawText(QPointF(0, metrics.ascent()), self.text)
            painter.restore()

    def _text_rect(self) -> QRectF:
        metrics = QFontMetrics(self.font)
        tw, th = metrics.horizontalAdvance(self.text), metrics.height()
        if self._is_angled:
            layout = self._layout()
            d1x, d1y, d2x, d2y, ux, uy = layout[1]
            return self._text_rect_angled(d1x, d1y, d2x, d2y, ux, uy, tw, th)
        lp = self._layout()[1]
        if self.side == "bottom":
            return QRectF((self.a1 + self.a2) / 2 - tw / 2, lp + TEXT_OFF, tw, th)
        if self.side == "top":
            return QRectF((self.a1 + self.a2) / 2 - tw / 2, lp - TEXT_OFF - th, tw, th)
        if self.side == "left":
            return QRectF(lp - TEXT_OFF - th, (self.a1 + self.a2) / 2 - tw / 2, th, tw)
        return QRectF(lp + TEXT_OFF, (self.a1 + self.a2) / 2 - tw / 2, th, tw)

    def shape(self):
        path = QPainterPath()
        path.addRect(self._text_rect())
        return path

    def hoverEnterEvent(self, event):
        if self.locked:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        super().hoverEnterEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.locked:
                self.on_select("dimension", self.dim_id, notify=True)
                event.accept()
                return
            self.on_select("dimension", self.dim_id, notify=False)
            self._dragging = True
            self._drag_start_pos = event.scenePos()
            self._drag_start_offset = self.offset
            if self._is_angled:
                self.line_anchor = None
            self.grabMouse()
            event.accept()
            return
        super().mousePressEvent(event)

    def _try_flip_side(self, delta) -> bool:
        if self.side not in _OPPOSITE_SIDE:
            return False
        thresh = 0.5
        min_off = 3.0 + thresh
        if self.offset > min_off:
            return False
        _, _, nx, ny = self._dim_vectors()
        perp = delta.x() * nx + delta.y() * ny
        if perp < -thresh:
            self.side = _OPPOSITE_SIDE[self.side]
            self.offset = 3.0
            return True
        return False

    def mouseMoveEvent(self, event):
        if self._dragging:
            delta = event.scenePos() - self._drag_start_pos
            if self._try_flip_side(delta):
                self._drag_start_pos = event.scenePos()
                self._drag_start_offset = self.offset
                delta = event.scenePos() - self._drag_start_pos
            off = self._drag_start_offset
            if self._is_angled:
                _, _, nx, ny = self._dim_vectors()
                off = max(3, off + delta.x() * nx + delta.y() * ny)
            elif self.side == "bottom":
                off = max(3, off + delta.y())
            elif self.side == "top":
                off = max(3, off - delta.y())
            elif self.side == "left":
                off = max(3, off - delta.x())
            else:
                off = max(3, off + delta.x())
            off = self._apply_offset_snap(off)
            self.offset = off
            self.on_offset(self.dim_id, off)
            self.prepareGeometryChange()
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            delta = event.scenePos() - self._drag_start_pos
            self._dragging = False
            self.ungrabMouse()
            event.accept()
            moved = math.hypot(delta.x(), delta.y()) > 2 or abs(self.offset - self._drag_start_offset) > 0.5
            if moved:
                self.on_offset_end(self.dim_id, self.offset)
            else:
                self.on_select("dimension", self.dim_id, notify=True)
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.on_edit and not self.locked:
            self.on_edit(self.dim_id)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class LeaderGraphicsItem(QGraphicsObject):
    TICK_OFFSET = 0.1

    @classmethod
    def tick_half_len(cls, line_width: float) -> float:
        return line_width / 2.0 + cls.TICK_OFFSET

    def __init__(self, note_id, ax, ay, text, color, font, ox, oy, on_select, on_move, on_move_end,
                 mark_points=None, diameter_radius: float | None = None,
                 radius_length: float | None = None, marker_line_width: float = 2.0,
                 on_edit=None, selected=False, selection_color=None, locked=False, parent=None):
        super().__init__(parent)
        self.note_id = note_id
        self.anchor = QPointF(ax, ay)
        self.text = text
        self.color = QColor(color)
        self.font = QFont(font)
        self.text_offset = QPointF(ox, oy)
        self.mark_points = [QPointF(x, y) for x, y in (mark_points or [])]
        self.diameter_radius = diameter_radius
        self.radius_length = radius_length
        self.marker_line_width = marker_line_width
        self.on_select = on_select
        self.on_move = on_move
        self.on_move_end = on_move_end
        self.on_edit = on_edit
        self.selected = selected
        self.selection_color = QColor(selection_color) if selection_color else None
        self.locked = locked
        self._dragging = False
        self._drag_start = None
        self._offset_start = None
        self.setZValue(11)

    def update_anchor(self, ax: float, ay: float) -> None:
        """Move leader anchor; text offset stays the same."""
        self.anchor = QPointF(ax, ay)
        self.prepareGeometryChange()
        self.update()

    def update_text(self, text: str) -> None:
        self.text = text
        self.prepareGeometryChange()
        self.update()

    def update_mark_points(self, points: list[tuple[float, float]]) -> None:
        self.mark_points = [QPointF(x, y) for x, y in points]
        self.prepareGeometryChange()
        self.update()

    def update_radius_length(self, length: float) -> None:
        self.radius_length = length
        self.prepareGeometryChange()
        self.update()

    def text_pos(self):
        return self.anchor + self.text_offset

    def boundingRect(self):
        tp = self.text_pos()
        metrics = QFontMetrics(self.font)
        tw, th = metrics.horizontalAdvance(self.text), metrics.height()
        rect = QRectF(tp.x(), tp.y(), tw, th)
        _, lines, marks = self._layout_geometry(tw, th)
        for x1, y1, x2, y2 in lines:
            rect = rect.united(QRectF(QPointF(x1, y1), QPointF(x2, y2)))
        half = self.tick_half_len(self.marker_line_width)
        for x, y, tx, ty in marks:
            rect = rect.united(QRectF(
                x - half * abs(tx), y - half * abs(ty),
                2 * half * abs(tx) or half, 2 * half * abs(ty) or half,
            ))
        return rect.adjusted(-4, -4, 4, 4)

    def _text_rect(self) -> QRectF:
        tp = self.text_pos()
        metrics = QFontMetrics(self.font)
        tw, th = metrics.horizontalAdvance(self.text), metrics.height()
        return QRectF(tp.x(), tp.y(), tw, th)

    def _line_attach_point(self, tw: float, th: float) -> QPointF:
        """Точка на краю текста: слева, если якорь слева, иначе справа."""
        tp = self.text_pos()
        mid_y = tp.y() + th / 2.0
        text_cx = tp.x() + tw / 2.0
        if self.anchor.x() < text_cx:
            return QPointF(tp.x(), mid_y)
        return QPointF(tp.x() + tw, mid_y)

    def _leader_unit_vector(self, attach: QPointF) -> tuple[float, float] | None:
        dx = attach.x() - self.anchor.x()
        dy = attach.y() - self.anchor.y()
        ln = math.hypot(dx, dy)
        if ln < 1e-9:
            return None
        return dx / ln, dy / ln

    def _layout_geometry(self, tw: float, th: float) -> tuple[
        QPointF,
        list[tuple[float, float, float, float]],
        list[tuple[float, float, float, float]],
    ]:
        attach = self._line_attach_point(tw, th)
        cx, cy = self.anchor.x(), self.anchor.y()
        lines: list[tuple[float, float, float, float]] = []
        marks: list[tuple[float, float, float, float]] = []
        ov = DIM_OVERSHOOT

        if self.diameter_radius is not None:
            unit = self._leader_unit_vector(attach)
            if unit is not None:
                ux, uy = unit
                tx, ty = tick_dir_45(ux, uy)
                r = self.diameter_radius
                near = QPointF(cx + ux * r, cy + uy * r)
                far = QPointF(cx - ux * r, cy - uy * r)
                lines.append((cx, cy, near.x() + ux * ov, near.y() + uy * ov))
                lines.append((cx, cy, far.x() - ux * ov, far.y() - uy * ov))
                lines.append((near.x(), near.y(), attach.x(), attach.y()))
                marks.append((near.x(), near.y(), tx, ty))
                marks.append((far.x(), far.y(), tx, ty))
                return attach, lines, marks
            lines.append((cx, cy, attach.x(), attach.y()))
            return attach, lines, marks

        if self.radius_length is not None:
            unit = self._leader_unit_vector(attach)
            if unit is not None:
                ux, uy = unit
                tx, ty = tick_dir_45(ux, uy)
                r = self.radius_length
                edge = QPointF(cx + ux * r, cy + uy * r)
                lines.append((cx, cy, edge.x() + ux * ov, edge.y() + uy * ov))
                lines.append((edge.x(), edge.y(), attach.x(), attach.y()))
                marks.append((edge.x(), edge.y(), tx, ty))
                return attach, lines, marks
            lines.append((cx, cy, attach.x(), attach.y()))
            return attach, lines, marks

        if len(self.mark_points) == 1:
            mp = self.mark_points[0]
            unit = self._leader_unit_vector(attach)
            if unit is not None:
                tx, ty = tick_dir_45(unit[0], unit[1])
            else:
                tx, ty = tick_dir_45(1.0, 0.0)
            lines.append((cx, cy, mp.x(), mp.y()))
            lines.append((mp.x(), mp.y(), attach.x(), attach.y()))
            marks.append((mp.x(), mp.y(), tx, ty))
            return attach, lines, marks

        lines.append((cx, cy, attach.x(), attach.y()))
        return attach, lines, marks

    def shape(self):
        path = QPainterPath()
        path.addRect(self._text_rect())
        return path

    def _draw_color(self) -> QColor:
        if self.selected and self.selection_color is not None:
            return self.selection_color
        return self.color

    def paint(self, painter, option, widget=None):
        tp = self.text_pos()
        color = self._draw_color()
        pen = QPen(color)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setFont(self.font)
        metrics = painter.fontMetrics()
        tw, th = metrics.horizontalAdvance(self.text), metrics.height()
        _, lines, marks = self._layout_geometry(tw, th)
        for x1, y1, x2, y2 in lines:
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))
        half = self.tick_half_len(self.marker_line_width)
        mark_pen = QPen(color)
        mark_pen.setCosmetic(True)
        mark_pen.setWidthF(max(1.0, self.marker_line_width))
        painter.setPen(mark_pen)
        for x, y, tx, ty in marks:
            painter.drawLine(
                QPointF(x - tx * half, y - ty * half),
                QPointF(x + tx * half, y + ty * half),
            )
        painter.setPen(pen)
        painter.drawText(QPointF(tp.x(), tp.y() + metrics.ascent()), self.text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.locked:
                self.on_select("dimension", self.note_id, notify=True)
                event.accept()
                return
            self.on_select("dimension", self.note_id, notify=False)
            self._dragging = True
            self._drag_start = event.scenePos()
            self._offset_start = QPointF(self.text_offset)
            self.grabMouse()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.text_offset = self._offset_start + (event.scenePos() - self._drag_start)
            self.on_move(self.note_id, self.text_offset.x(), self.text_offset.y())
            self.prepareGeometryChange()
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            delta = event.scenePos() - self._drag_start
            self._dragging = False
            self.ungrabMouse()
            event.accept()
            moved = math.hypot(delta.x(), delta.y()) > 2
            if moved:
                self.on_move_end(self.note_id, self.text_offset.x(), self.text_offset.y())
            else:
                self.on_select("dimension", self.note_id, notify=True)
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.on_edit and not self.locked:
            self.on_edit(self.note_id)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)
