import requests
import sys
import shutil
import tempfile
import math
import os
import ezdxf
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QDoubleSpinBox, QSpinBox, QLineEdit, QPushButton, QFileDialog,
    QMessageBox, QScrollArea, QGraphicsView, QGraphicsScene, QCheckBox,
    QRadioButton, QButtonGroup, QGraphicsObject
)
from PyQt6.QtCore import Qt, QUrl, QSettings, QRectF, QPointF
from PyQt6.QtGui import (
    QPainter, QTransform, QColor, QPen, QDesktopServices, QPainterPath, QImage, QFont,
    QPainterPathStroker, QFontMetrics
)
from ezdxf.math import Matrix44

CURRENT_VERSION = "1.1.7"

DIM_STEP = 11
DIM_EXT = 7
TEXT_OFF = 2


class PreviewView(QGraphicsView):
    """Панорама (СКМ / ЛКМ по фону) и масштаб колёсиком."""

    def __init__(self, scene, on_user_view=None, parent=None):
        super().__init__(scene, parent)
        self._on_user_view = on_user_view
        self._panning = False
        self._pan_start = QPointF()
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def _notify_user_view(self):
        if self._on_user_view:
            self._on_user_view()

    def wheelEvent(self, event):
        if event.angleDelta().y() == 0:
            return
        factor = 1.12 if event.angleDelta().y() > 0 else 1 / 1.12
        self.scale(factor, factor)
        self._notify_user_view()
        event.accept()

    def mousePressEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton) or (
            event.button() == Qt.MouseButton.LeftButton and item is None
        ):
            self._panning = True
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            t = self.transform()
            self.setTransform(QTransform(
                t.m11(), t.m12(), t.m21(), t.m22(),
                t.dx() + delta.x(), t.dy() + delta.y(),
            ))
            self._notify_user_view()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class DimItem(QGraphicsObject):
    """Размерная линия с подписью; перетаскивание — дальше/ближе от детали."""

    def __init__(self, dim_id, side, a1, a2, ref, text, color, font, initial_offset=None):
        super().__init__()
        self.dim_id = dim_id
        self.side = side
        self.a1 = min(a1, a2)
        self.a2 = max(a1, a2)
        self.ref = ref
        self.text = text
        self.color = QColor(color)
        self.font = QFont(font)
        self.offset = initial_offset if initial_offset is not None else DIM_EXT
        self._dragging = False
        self._drag_start_offset = self.offset
        self._drag_start_pos = None
        self.setZValue(10)
        self.setAcceptHoverEvents(True)

    def _line_pos(self):
        if self.side == "bottom":
            return self.ref + self.offset
        if self.side == "top":
            return self.ref - self.offset
        if self.side == "left":
            return self.ref - self.offset
        return self.ref + self.offset

    def _layout(self):
        lp = self._line_pos()
        lines = []
        if self.side in ("bottom", "top"):
            lines.append((self.a1, self.ref, self.a1, lp))
            lines.append((self.a2, self.ref, self.a2, lp))
            lines.append((self.a1, lp, self.a2, lp))
        else:
            lines.append((self.ref, self.a1, lp, self.a1))
            lines.append((self.ref, self.a2, lp, self.a2))
            lines.append((lp, self.a1, lp, self.a2))
        return lines, lp

    def _text_rect(self, lp):
        metrics = QFontMetrics(self.font)
        tw = metrics.horizontalAdvance(self.text)
        th = metrics.height()
        if self.side == "bottom":
            return QRectF((self.a1 + self.a2) / 2 - tw / 2, lp + TEXT_OFF, tw, th)
        if self.side == "top":
            return QRectF((self.a1 + self.a2) / 2 - tw / 2, lp - TEXT_OFF - th, tw, th)
        if self.side == "left":
            return QRectF(lp - TEXT_OFF - th, (self.a1 + self.a2) / 2 - tw / 2, th, tw)
        return QRectF(lp + TEXT_OFF, (self.a1 + self.a2) / 2 - tw / 2, th, tw)

    def boundingRect(self):
        lines, lp = self._layout()
        rect = QRectF()
        for x1, y1, x2, y2 in lines:
            rect = rect.united(QRectF(QPointF(x1, y1), QPointF(x2, y2)))
        rect = rect.united(self._text_rect(lp))
        return rect.adjusted(-4, -4, 4, 4)

    def paint(self, painter, option, widget=None):
        lines, lp = self._layout()
        pen = QPen(self.color)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setFont(self.font)
        for x1, y1, x2, y2 in lines:
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        metrics = painter.fontMetrics()
        tw = metrics.horizontalAdvance(self.text)
        th = metrics.height()
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

    def shape(self):
        path = QPainterPath()
        lines, _ = self._layout()
        for x1, y1, x2, y2 in lines:
            path.moveTo(x1, y1)
            path.lineTo(x2, y2)
        stroker = QPainterPathStroker()
        stroker.setWidth(10)
        return stroker.createStroke(path)

    def hoverEnterEvent(self, event):
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        super().hoverEnterEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start_pos = event.scenePos()
            self._drag_start_offset = self.offset
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            delta = event.scenePos() - self._drag_start_pos
            if self.side == "bottom":
                self.offset = max(3, self._drag_start_offset + delta.y())
            elif self.side == "top":
                self.offset = max(3, self._drag_start_offset - delta.y())
            elif self.side == "left":
                self.offset = max(3, self._drag_start_offset - delta.x())
            else:
                self.offset = max(3, self._drag_start_offset + delta.x())
            self.prepareGeometryChange()
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            for view in self.scene().views():
                w = view.window()
                if hasattr(w, "save_dim_offset"):
                    w.save_dim_offset(self.dim_id, self.offset)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class LeaderNoteItem(QGraphicsObject):
    """Сноска с выносной линией; текст перетаскивается мышью."""

    def __init__(self, note_id, anchor_x, anchor_y, text, color, font, text_offset=None):
        super().__init__()
        self.note_id = note_id
        self.anchor = QPointF(anchor_x, anchor_y)
        self.text = text
        self.color = QColor(color)
        self.font = QFont(font)
        if text_offset is None:
            self.text_offset = QPointF(-50, -20)
        elif isinstance(text_offset, QPointF):
            self.text_offset = QPointF(text_offset)
        else:
            self.text_offset = QPointF(text_offset[0], text_offset[1])
        self._dragging = False
        self._drag_start = None
        self._offset_start = None
        self.setZValue(11)
        self.setAcceptHoverEvents(True)

    def text_pos(self):
        return self.anchor + self.text_offset

    def boundingRect(self):
        tp = self.text_pos()
        br_w = len(self.text) * self.font.pointSize() * 0.55
        br_h = self.font.pointSize() + 4
        rect = QRectF(tp.x(), tp.y(), br_w, br_h)
        rect = rect.united(QRectF(self.anchor, tp))
        return rect.adjusted(-4, -4, 4, 4)

    def paint(self, painter, option, widget=None):
        tp = self.text_pos()
        pen = QPen(self.color)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setFont(self.font)
        metrics = painter.fontMetrics()
        tw = metrics.horizontalAdvance(self.text)
        th = metrics.height()
        painter.drawLine(self.anchor, QPointF(tp.x() + tw, tp.y() + th / 2))
        painter.drawText(QPointF(tp.x(), tp.y() + metrics.ascent()), self.text)

    def shape(self):
        path = QPainterPath()
        tp = self.text_pos()
        path.addRect(QRectF(tp.x(), tp.y(), len(self.text) * 6, self.font.pointSize() + 6))
        return path

    def hoverEnterEvent(self, event):
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        super().hoverEnterEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start = event.scenePos()
            self._offset_start = QPointF(self.text_offset)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.text_offset = self._offset_start + (event.scenePos() - self._drag_start)
            self.prepareGeometryChange()
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            for view in self.scene().views():
                w = view.window()
                if hasattr(w, "save_note_offset"):
                    w.save_note_offset(self.note_id, self.text_offset)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class PreviewBuilder:
    """Сборка сцены: габариты снизу/справа, межосевые сверху/слева."""

    def __init__(self, scene, part_w, part_h, font, dim_offsets, note_offsets):
        self.scene = scene
        self.pw = part_w
        self.ph = part_h
        self.font = font
        self.dim_offsets = dim_offsets
        self.note_offsets = note_offsets
        self._top_lane = 0
        self._left_lane = 0

    def _off(self, dim_id, lane_extra=0):
        base = self.dim_offsets.get(dim_id)
        if base is not None:
            return base
        return DIM_EXT + lane_extra * DIM_STEP

    def add_dim(self, dim_id, side, a1, a2, ref, text, color, lane=0):
        offset = self._off(dim_id, lane)
        item = DimItem(dim_id, side, a1, a2, ref, text, color, self.font, offset)
        self.scene.addItem(item)

    def add_center_lines(self, ox, oy, cv, gv, ch, gh, color):
        pen = QPen(QColor(color))
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        ext = max(gh, gv) * 0.15 + 4
        for i in range(cv):
            cy = oy + i * gv
            self.scene.addLine(ox - ext, cy, ox + (ch - 1) * gh + ext, cy, pen)
        for j in range(ch):
            cx = ox + j * gh
            self.scene.addLine(cx, oy - ext, cx, oy + (cv - 1) * gv + ext, pen)

    def add_hole_note(self, note_id, ax, ay, text, color):
        off = self.note_offsets.get(note_id)
        if off is not None:
            offset = (off.x(), off.y())
        else:
            try:
                idx = int(note_id[1:note_id.index("_")])
            except ValueError:
                idx = 0
            offset = (-55, -18 - idx * 16)
        item = LeaderNoteItem(note_id, ax, ay, text, color, self.font, offset)
        self.scene.addItem(item)

    def add_corner_note(self, note_id, ax, ay, text, color):
        off = self.note_offsets.get(note_id)
        if off is not None:
            offset = (off.x(), off.y())
        else:
            offset = (12, 12)
        item = LeaderNoteItem(note_id, ax, ay, text, color, self.font, offset)
        self.scene.addItem(item)

    def array_dims(self, idx, ox, oy, cv, gv, ch, gh, color):
        p = f"a{idx}"
        lane_t, lane_l = 0, 0
        self.add_dim(f"{p}_ox", "top", 0, ox, oy, f"{ox:.1f}", color, lane_t)
        lane_t += 1
        if ch > 1:
            self.add_dim(f"{p}_gh", "top", ox, ox + gh, oy, f"{gh:.1f}", color, lane_t)
            lane_t += 1
            if ch > 2:
                self.add_dim(f"{p}_span", "top", ox, ox + (ch - 1) * gh, oy, f"{(ch - 1) * gh:.1f}", color, lane_t)
        self.add_dim(f"{p}_oy", "left", 0, oy, ox, f"{oy:.1f}", color, lane_l)
        lane_l += 1
        if cv > 1:
            self.add_dim(f"{p}_gv", "left", oy, oy + gv, ox, f"{gv:.1f}", color, lane_l)

    def overall_dims(self):
        self.add_dim("w_all", "bottom", 0, self.pw, self.ph, f"{self.pw:.1f}", "black", 0)
        self.add_dim("h_all", "right", 0, self.ph, self.pw, f"{self.ph:.1f}", "black", 0)

# Виджет для ввода параметров массива отверстий (прямоугольная сетка)
class ArrayEntry(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Горизонтальный layout для параметров массива
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Надпись для массива – её цвет будет задаваться динамически
        self.label = QLabel("Массив:")

        # Отступ слева (по X) от нижнего левого угла
        self.spinOffsetLeft = QDoubleSpinBox()
        self.spinOffsetLeft.setMinimum(0.0)
        self.spinOffsetLeft.setMaximum(10000.0)
        self.spinOffsetLeft.setDecimals(2)
        self.spinOffsetLeft.setValue(30.0)
        self.spinOffsetLeft.setSuffix(" мм")
        self.spinOffsetLeft.setToolTip("Отступ слева от нижнего левого угла")

        # Отступ снизу (по Y) от нижнего левого угла
        self.spinOffsetBottom = QDoubleSpinBox()
        self.spinOffsetBottom.setMinimum(0.0)
        self.spinOffsetBottom.setMaximum(10000.0)
        self.spinOffsetBottom.setDecimals(2)
        self.spinOffsetBottom.setValue(30.0)
        self.spinOffsetBottom.setSuffix(" мм")
        self.spinOffsetBottom.setToolTip("Отступ снизу от нижнего левого угла")

        # Диаметр отверстия
        self.spinHoleDiameter = QDoubleSpinBox()
        self.spinHoleDiameter.setMinimum(0.0)
        self.spinHoleDiameter.setMaximum(10000.0)
        self.spinHoleDiameter.setDecimals(2)
        self.spinHoleDiameter.setValue(10.0)
        self.spinHoleDiameter.setSuffix(" мм")
        self.spinHoleDiameter.setToolTip("Диаметр отверстия")

        # Количество отверстий по вертикали (ряды)
        self.spinCountVert = QSpinBox()
        self.spinCountVert.setMinimum(1)
        self.spinCountVert.setMaximum(1000)
        self.spinCountVert.setValue(2)
        self.spinCountVert.setToolTip("Кол-во отверстий по вертикали (рядов)")

        # Вертикальный промежуток между отверстиями
        self.spinGapVert = QDoubleSpinBox()
        self.spinGapVert.setMinimum(0.0)
        self.spinGapVert.setMaximum(10000.0)
        self.spinGapVert.setDecimals(2)
        self.spinGapVert.setValue(240.0)
        self.spinGapVert.setSuffix(" мм")
        self.spinGapVert.setToolTip("Вертикальный промежуток между отверстиями")

        # Количество отверстий по горизонтали (колонки)
        self.spinCountHorz = QSpinBox()
        self.spinCountHorz.setMinimum(1)
        self.spinCountHorz.setMaximum(1000)
        self.spinCountHorz.setValue(2)
        self.spinCountHorz.setToolTip("Кол-во отверстий по горизонтали (колонок)")

        # Горизонтальный промежуток между отверстиями
        self.spinGapHorz = QDoubleSpinBox()
        self.spinGapHorz.setMinimum(0.0)
        self.spinGapHorz.setMaximum(10000.0)
        self.spinGapHorz.setDecimals(2)
        self.spinGapHorz.setValue(440.0)
        self.spinGapHorz.setSuffix(" мм")
        self.spinGapHorz.setToolTip("Горизонтальный промежуток между отверстиями")

        # Кнопка удаления массива
        self.removeButton = QPushButton("Х")
        self.removeButton.setFixedWidth(40)

        # Добавляем виджеты в layout
        layout.addWidget(self.label)
        layout.addWidget(self.spinOffsetLeft)
        layout.addWidget(self.spinOffsetBottom)
        layout.addWidget(self.spinHoleDiameter)
        layout.addWidget(self.spinCountVert)
        layout.addWidget(self.spinGapVert)
        layout.addWidget(self.spinCountHorz)
        layout.addWidget(self.spinGapHorz)
        layout.addWidget(self.removeButton)

        self.removeButton.clicked.connect(self.remove_self)

    def remove_self(self):
        parent_layout = self.parentWidget().layout()
        parent_layout.removeWidget(self)
        self.deleteLater()

    def get_values(self):
        offset_left = self.spinOffsetLeft.value()
        offset_bottom = self.spinOffsetBottom.value()
        hole_diameter = self.spinHoleDiameter.value()
        count_vert = self.spinCountVert.value()
        gap_vert = self.spinGapVert.value()
        count_horz = self.spinCountHorz.value()
        gap_horz = self.spinGapHorz.value()
        return offset_left, offset_bottom, hole_diameter, count_vert, gap_vert, count_horz, gap_horz

# Основное окно приложения
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"DXF Конструктор: Прямоугольник и Отверстия - v.{CURRENT_VERSION}")

        self.settings = QSettings("DXF", "DXFConstructor")

        centralWidget = QWidget()
        self.setCentralWidget(centralWidget)
        mainLayout = QVBoxLayout(centralWidget)

        # Верхняя панель управления
        controlsWidget = QWidget()
        controlsWidget.setMinimumWidth(600)
        controlsLayout = QVBoxLayout(controlsWidget)
        controlsLayout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Строка 1: Обозначение и Название в одну строку
        row1 = QHBoxLayout()
        row1.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        row1.addWidget(QLabel("Обозначение:"))
        self.lineDesignation = QLineEdit()
        self.lineDesignation.setToolTip("Введите обозначение (необязательно)")
        row1.addWidget(self.lineDesignation)
        row1.addWidget(QLabel("Название:"))
        self.lineName = QLineEdit()
        self.lineName.setToolTip("Название подставляется автоматически в формате R_[ширина]x[высота]")
        row1.addWidget(self.lineName)
        controlsLayout.addLayout(row1)

        # Строка 2: Ширина, Высота и Радиус скругления в одну строку
        row2 = QHBoxLayout()
        row2.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        row2.addWidget(QLabel("Ширина:"))
        self.spinWidth = QDoubleSpinBox()
        self.spinWidth.setMinimum(0.0)
        self.spinWidth.setMaximum(10000.0)
        self.spinWidth.setDecimals(2)
        self.spinWidth.setValue(500.0)
        self.spinWidth.setSuffix(" мм")
        self.spinWidth.setToolTip("Задайте ширину прямоугольника")
        row2.addWidget(self.spinWidth)
        row2.addWidget(QLabel("Высота:"))
        self.spinHeight = QDoubleSpinBox()
        self.spinHeight.setMinimum(0.0)
        self.spinHeight.setMaximum(10000.0)
        self.spinHeight.setDecimals(2)
        self.spinHeight.setValue(300.0)
        self.spinHeight.setSuffix(" мм")
        self.spinHeight.setToolTip("Задайте высоту прямоугольника")
        row2.addWidget(self.spinHeight)

        self.radioCornerRadius = QRadioButton("Радиус")
        self.radioCornerRadius.setChecked(True)
        self.radioCornerRadius.setToolTip("Скругление углов по радиусу")
        self.radioCornerChamfer = QRadioButton("Фаска")
        self.radioCornerChamfer.setToolTip("Срез углов под 45°")
        self.cornerModeGroup = QButtonGroup(self)
        self.cornerModeGroup.addButton(self.radioCornerRadius)
        self.cornerModeGroup.addButton(self.radioCornerChamfer)
        row2.addWidget(self.radioCornerRadius)
        row2.addWidget(self.radioCornerChamfer)

        self.labelCornerSize = QLabel("Размер:")
        row2.addWidget(self.labelCornerSize)
        self.spinCornerRadius = QDoubleSpinBox()
        self.spinCornerRadius.setMinimum(0.0)
        self.spinCornerRadius.setMaximum(10000.0)
        self.spinCornerRadius.setDecimals(2)
        self.spinCornerRadius.setValue(0.0)
        self.spinCornerRadius.setSuffix(" мм")
        self.spinCornerRadius.setToolTip("Задайте радиус скругления углов прямоугольника")
        row2.addWidget(self.spinCornerRadius)
        controlsLayout.addLayout(row2)

        # Обновление предпросмотра при изменении размеров
        self.spinWidth.valueChanged.connect(self.update_corner_size_limit)
        self.spinHeight.valueChanged.connect(self.update_corner_size_limit)
        self.spinCornerRadius.valueChanged.connect(self.update_preview)
        self.cornerModeGroup.buttonClicked.connect(self.on_corner_mode_changed)

        # Метка для массивов отверстий
        controlsLayout.addWidget(QLabel("Массивы отверстий:"))

        # Прокручиваемая область для ввода массивов
        self.scrollArea = QScrollArea()
        self.scrollArea.setWidgetResizable(True)
        self.arraysContainer = QWidget()
        self.arraysLayout = QVBoxLayout(self.arraysContainer)
        self.arraysLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scrollArea.setWidget(self.arraysContainer)
        controlsLayout.addWidget(self.scrollArea)

        # Строка с кнопками "Добавить массив" и "Сгенерировать DXF"
        buttonsLayout = QHBoxLayout()
        self.addArrayButton = QPushButton("Добавить массив")
        self.addArrayButton.clicked.connect(self.add_array)
        buttonsLayout.addWidget(self.addArrayButton)
        self.generateButton = QPushButton("Сгенерировать DXF")
        self.generateButton.clicked.connect(self.generate_dxf)
        buttonsLayout.addWidget(self.generateButton)
        self.exportPng = QCheckBox("Вывести PNG")
        buttonsLayout.addWidget(self.exportPng)
        #self.btnCheckUpdate = QPushButton("Проверка обновления")
        #self.btnCheckUpdate.clicked.connect(self.check_update)
        #buttonsLayout.addWidget(self.btnCheckUpdate)
        controlsLayout.addLayout(buttonsLayout)

        previewControls = QHBoxLayout()
        previewControls.addWidget(QLabel("Шрифт:"))
        self.spinPreviewFont = QSpinBox()
        self.spinPreviewFont.setRange(6, 24)
        self.spinPreviewFont.setValue(9)
        self.spinPreviewFont.setToolTip("Размер шрифта подписей в предпросмотре")
        self.spinPreviewFont.valueChanged.connect(self.update_preview)
        previewControls.addWidget(self.spinPreviewFont)
        self.btnFitPreview = QPushButton("Вписать")
        self.btnFitPreview.setToolTip("Вписать чертёж в окно предпросмотра")
        self.btnFitPreview.clicked.connect(self.reset_preview_view)
        previewControls.addWidget(self.btnFitPreview)
        previewControls.addWidget(QLabel("ЛКМ: размер/сноска | колёсико: масштаб | ПКМ/фон: перемещение"))
        previewControls.addStretch()
        controlsLayout.addLayout(previewControls)

        mainLayout.addWidget(controlsWidget)

        self._dim_offsets = {}
        self._note_offsets = {}
        self._user_view = False

        # Предпросмотр (нижняя часть)
        self.previewScene = QGraphicsScene(self)
        self.previewView = PreviewView(self.previewScene, on_user_view=self._on_user_view)
        self.previewView.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.previewView.setMinimumHeight(400)
        self.previewView.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.previewView.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.previewView.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.previewView.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        mainLayout.addWidget(self.previewView, 1)

        # Список цветов для массивов (назначаются циклически)
        self.color_list = ["red", "blue", "green", "orange", "purple", "magenta", "cyan"]
        self.check_update()
        self.update_corner_size_limit()

    def max_corner_size(self):
        return min(self.spinWidth.value(), self.spinHeight.value()) * 0.5

    def corner_size_tooltip(self):
        max_size = self.max_corner_size()
        limit = f" (макс. {max_size:.2f} мм — 50% меньшей стороны)"
        if self.is_chamfer_mode():
            return "Задайте размер фаски углов прямоугольника" + limit
        return "Задайте радиус скругления углов прямоугольника" + limit

    def update_corner_size_limit(self):
        max_size = max(0.0, self.max_corner_size())
        self.spinCornerRadius.setMaximum(max_size)
        if self.spinCornerRadius.value() > max_size:
            self.spinCornerRadius.setValue(max_size)
        self.spinCornerRadius.setToolTip(self.corner_size_tooltip())
        self.update_preview()

    def is_chamfer_mode(self):
        return self.radioCornerChamfer.isChecked()

    def on_corner_mode_changed(self):
        self.spinCornerRadius.setToolTip(self.corner_size_tooltip())
        self.update_preview()

    def chamfered_rect_points(self, width, height, chamfer):
        if chamfer <= 0:
            return [(0, 0), (width, 0), (width, height), (0, height), (0, 0)]
        return [
            (chamfer, 0),
            (width - chamfer, 0),
            (width, chamfer),
            (width, height - chamfer),
            (width - chamfer, height),
            (chamfer, height),
            (0, height - chamfer),
            (0, chamfer),
            (chamfer, 0),
        ]

    def add_rectangle_to_scene(self, width, height, corner_size):
        pen_rect = QPen(Qt.GlobalColor.black)
        pen_rect.setCosmetic(True)

        if corner_size <= 0:
            self.previewScene.addRect(0, 0, width, height, pen_rect)
            return

        if self.is_chamfer_mode():
            path = QPainterPath()
            pts = self.chamfered_rect_points(width, height, corner_size)
            path.moveTo(*pts[0])
            for x, y in pts[1:]:
                path.lineTo(x, y)
            self.previewScene.addPath(path, pen_rect)
        else:
            path = QPainterPath()
            path.addRoundedRect(0, 0, width, height, corner_size, corner_size)
            self.previewScene.addPath(path, pen_rect)

    def add_rectangle_to_dxf(self, msp, width, height, corner_size):
        if corner_size <= 0:
            pts = [(0, 0), (width, 0), (width, height), (0, height), (0, 0)]
            msp.add_lwpolyline(pts, close=True)
            return

        if self.is_chamfer_mode():
            msp.add_lwpolyline(self.chamfered_rect_points(width, height, corner_size), close=True)
            return

        r = corner_size
        msp.add_line((r, 0), (width - r, 0))
        msp.add_arc(center=(width - r, r), radius=r, start_angle=270, end_angle=360)
        msp.add_line((width, r), (width, height - r))
        msp.add_arc(center=(width - r, height - r), radius=r, start_angle=0, end_angle=90)
        msp.add_line((width - r, height), (r, height))
        msp.add_arc(center=(r, height - r), radius=r, start_angle=90, end_angle=180)
        msp.add_line((0, height - r), (0, r))
        msp.add_arc(center=(r, r), radius=r, start_angle=180, end_angle=270)

    def add_array(self):
        array_entry = ArrayEntry(self.arraysContainer)
        self.arraysLayout.addWidget(array_entry)
        array_entry.spinOffsetLeft.valueChanged.connect(self.update_preview)
        array_entry.spinOffsetBottom.valueChanged.connect(self.update_preview)
        array_entry.spinHoleDiameter.valueChanged.connect(self.update_preview)
        array_entry.spinCountVert.valueChanged.connect(self.update_preview)
        array_entry.spinGapVert.valueChanged.connect(self.update_preview)
        array_entry.spinCountHorz.valueChanged.connect(self.update_preview)
        array_entry.spinGapHorz.valueChanged.connect(self.update_preview)
        array_entry.removeButton.clicked.connect(self.update_preview)
        self.update_preview()

    def _on_user_view(self):
        self._user_view = True

    def save_dim_offset(self, dim_id, offset):
        self._dim_offsets[dim_id] = offset

    def save_note_offset(self, note_id, offset):
        self._note_offsets[note_id] = QPointF(offset)

    def reset_preview_view(self):
        self._user_view = False
        self.previewView.resetTransform()
        self._fit_preview()

    def _preview_font(self):
        font = QFont()
        font.setPointSize(self.spinPreviewFont.value())
        return font

    def save_preview_image(self, file_path_without_ext):
        img = QImage(
            self.previewView.viewport().size(),
            QImage.Format.Format_ARGB32,
        )
        img.fill(Qt.GlobalColor.white)
        painter = QPainter(img)
        self.previewView.render(painter)
        painter.end()
        out_path = file_path_without_ext + ".png"
        img.save(out_path)
        return out_path

    def _fit_preview(self):
        rect = self.previewScene.sceneRect()
        if rect.isValid() and rect.width() > 0 and rect.height() > 0:
            self.previewView.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._user_view:
            self._fit_preview()

    def update_preview(self):
        saved_transform = self.previewView.transform() if self._user_view else None
        self.previewScene.clear()

        width = self.spinWidth.value()
        height = self.spinHeight.value()
        corner_radius = self.spinCornerRadius.value()
        font = self._preview_font()
        builder = PreviewBuilder(
            self.previewScene, width, height, font, self._dim_offsets, self._note_offsets
        )

        self.add_rectangle_to_scene(width, height, corner_radius)

        for idx in range(self.arraysLayout.count()):
            widget = self.arraysLayout.itemAt(idx).widget()
            if widget is None:
                continue

            values = widget.get_values()
            color = self.color_list[idx % len(self.color_list)]
            pen_arr = QPen(QColor(color))
            pen_arr.setCosmetic(True)
            widget.label.setStyleSheet(f"color: {color};")

            ox, oy, d, cv, gv, ch, gh = values
            rr = d / 2
            for i in range(cv):
                for j in range(ch):
                    cx = ox + j * gh
                    cy = oy + i * gv
                    self.previewScene.addEllipse(cx - rr, cy - rr, d, d, pen_arr)

            builder.add_center_lines(ox, oy, cv, gv, ch, gh, color)
            builder.array_dims(idx, ox, oy, cv, gv, ch, gh, color)
            builder.add_hole_note(f"n{idx}_dia", ox, oy, f"Ø{d:.1f}  {cv * ch} отв.", color)

        if corner_radius > 0:
            if self.is_chamfer_mode():
                corner_text = f"{corner_radius:.0f}x45°  4 фаски"
            else:
                corner_text = f"R{corner_radius:.1f}"
            builder.add_corner_note(
                "corner",
                width - corner_radius,
                height - corner_radius,
                corner_text,
                "black",
            )

        builder.overall_dims()

        bounds = self.previewScene.itemsBoundingRect()
        pad = 4
        self.previewScene.setSceneRect(bounds.adjusted(-pad, -pad, pad, pad))

        if saved_transform is not None:
            self.previewView.setTransform(saved_transform)
        else:
            self._fit_preview()

        self.lineName.setText(f"R_{width:.2f}x{height:.2f}")

    def generate_dxf(self):
        import ezdxf
        from ezdxf.math import Matrix44

        width = self.spinWidth.value()
        height = self.spinHeight.value()
        corner_radius = self.spinCornerRadius.value()

        # Создаем новый DXF
        doc = ezdxf.new(dxfversion="R2010")
        doc.header["$INSUNITS"] = 4  # миллиметры
        msp = doc.modelspace()

        # ------------------------------
        #   ПРЯМОУГОЛЬНИК / СКРУГЛЕНИЯ / ФАСКИ
        # ------------------------------
        self.add_rectangle_to_dxf(msp, width, height, corner_radius)

        # ------------------------------
        #       ОТВЕРСТИЯ
        # ------------------------------
        for idx in range(self.arraysLayout.count()):
            widget = self.arraysLayout.itemAt(idx).widget()
            if widget is None:
                continue

            (offset_left, offset_bottom, hole_diameter,
             count_vert, gap_vert, count_horz, gap_horz) = widget.get_values()

            r = hole_diameter / 2

            for i in range(count_vert):
                for j in range(count_horz):
                    cx = offset_left + j * gap_horz
                    cy = offset_bottom + i * gap_vert
                    msp.add_circle((cx, cy), r)

        # ------------------------------
        #     ЗЕРКАЛО ПО ГОРИЗОНТАЛИ
        # ------------------------------
        mirror = Matrix44([
             1, 0, 0, 0,         # X без изменений
             0,-1, 0, height,    # Y → -Y + height
             0, 0, 1, 0,
             0, 0, 0, 1
        ])

        for entity in list(msp):
            try:
                entity.transform(mirror)
            except ezdxf.lldxf.const.DXFError:
                pass

        # ------------------------------
        #    СОХРАНЕНИЕ ФАЙЛА
        # ------------------------------
        designation = self.lineDesignation.text().strip()
        name = self.lineName.text().strip() or f"R_{width:.2f}x{height:.2f}"

        if designation:
            default_filename = f"{designation}_{name}.dxf"
        else:
            default_filename = f"{name}.dxf"

        last_path = self.settings.value("lastSavePath", os.path.expanduser("~"))
        initial_path = os.path.join(last_path, default_filename)

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить DXF", initial_path, "DXF файлы (*.dxf)"
        )

        if not file_path:
            return

        if not file_path.lower().endswith(".dxf"):
            file_path += ".dxf"

        try:
            # === СОХРАНЕНИЕ DXF ===
            doc.saveas(file_path)
            self.settings.setValue("lastSavePath", os.path.dirname(file_path))
        
            # База имени файла без расширения
            file_base, _ = os.path.splitext(file_path)
        
            # === СОХРАНЕНИЕ PNG ===
            if self.exportPng.isChecked():
                try:
                    png_path = self.save_preview_image(file_base)      # создаёт PNG
                except Exception as e:
                    QMessageBox.warning(self, "PNG ошибка", f"Не удалось сохранить PNG:\n{str(e)}")
        
            # === ОКНО УСПЕХА ===
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Успех")
            msg_box.setText(f"Файл успешно сохранён:\n{file_path}")
            open_btn = msg_box.addButton("Открыть папку", QMessageBox.ButtonRole.ActionRole)
            msg_box.addButton("Закрыть", QMessageBox.ButtonRole.RejectRole)
            msg_box.exec()
        
            if msg_box.clickedButton() == open_btn:
                QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(file_path)))
        
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка при сохранении файла:\n{str(e)}")

    

    def check_update(self):
        """ Проверяет новую версию на GitHub и предлагает обновление """
        try:
            url = "https://api.github.com/repos/Jkl88/DXF-Rectangle-Creator/releases/latest"
            response = requests.get(url, timeout=5)
            data = response.json()
    
            latest = data["tag_name"].lstrip("v")
            release_url = data["html_url"]
    
            # ищем первый .exe в релизе
            assets = data.get("assets", [])
            exe_url = None
            for a in assets:
                if a["name"].lower().endswith(".exe"):
                    exe_url = a["browser_download_url"]
                    break
    
            if exe_url is None:
                QMessageBox.warning(self, "Ошибка", "В релизе нет exe-файла.")
                return
    
            if latest == CURRENT_VERSION:
                #QMessageBox.information(self, "Обновление", "У вас последняя версия.")
                return
    
            # --- найдено обновление ---
            reply = QMessageBox.question(
                self,
                "Доступно обновление",
                f"Доступна новая версия: {latest}\n"
                f"Текущая версия: {CURRENT_VERSION}\n\n"
                f"Обновить сейчас?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
    
            if reply == QMessageBox.StandardButton.Yes:
                self.perform_update(exe_url)
    
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось проверить обновление:\n{e}")
    
    
    def perform_update(self, download_url):
        """ Скачивает новый exe, заменяет текущий, запускает обновлённую """
        try:
            import requests
            import sys
            import tempfile
            import os
    
            current_path = sys.executable
            exe_name = os.path.basename(current_path)
    
            tmp_dir = tempfile.gettempdir()
            new_exe = os.path.join(tmp_dir, "update_new.exe")
    
            # === СКАЧИВАЕМ НОВУЮ ВЕРСИЮ ===
            r = requests.get(download_url, stream=True)
            with open(new_exe, "wb") as f:
                for chunk in r.iter_content(8192):
                    if chunk:
                        f.write(chunk)
    
            # === UPDATE.BAT (CP866 совместимый!) ===
            updater_path = os.path.join(tmp_dir, "update.bat")
    
            with open(updater_path, "w", encoding="cp866") as bat:
                bat.write(f"""@echo off
                    
                    title Updating...
                    
                    echo Waiting for {exe_name} to exit...
                    
                    :waitloop
                    tasklist | find /i "{exe_name}" >nul
                    if not errorlevel 1 (
                        timeout /t 1 >nul
                        goto waitloop
                    )
                    
                    echo Updating file...
                    copy /y "{new_exe}" "{current_path}" >nul
                                        
                    del "{new_exe}"
                    del "%~f0"
                    """)
    
            # === ЗАПУСК UPDATE.BAT ===
            os.startfile(updater_path)
    
            # === ЖЁСТКО ЗАКРЫВАЕМ ПРОЦЕСС ===
            os.system(f'taskkill /F /PID {os.getpid()}')
    
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось обновить программу:\n{e}")
    



def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(720, 700)
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
