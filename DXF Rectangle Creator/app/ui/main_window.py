from __future__ import annotations

import os
import re
import sys

from PyQt6.QtCore import QSettings, QUrl, Qt
from PyQt6.QtGui import QAction, QDesktopServices, QKeySequence, QUndoStack
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QFileDialog, QHBoxLayout, QLabel,
    QMainWindow, QMessageBox, QPushButton, QGraphicsScene,
    QSplitter, QSpinBox, QVBoxLayout, QWidget,
)

from app.commands import (
    AddArrayCommand, AddDrawnRectCommand, AddHoleCommand, AddInfiniteLineCommand,
    AddShutterCommand, DeleteCommand, PropertyChangeCommand,
)
from app.editor.scene import EditorSceneController
from app.editor.title_block import TitleBlockWidget
from app.editor.view import EditorView
from app.export.dxf_exporter import export_dxf
from app.export.dxf_importer import apply_dxf_contour
from app.export.png_exporter import export_png
from app.models.base import ContourKind, SelectionKind
from app.models.document import Document
from app.ui.element_tree import ElementTree
from app.ui.properties_panel import PropertiesPanel
from app.ui.widgets import FocusSpinBox
from app.update_checker import check_update
from app.version import CURRENT_VERSION


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"DXF Конструктор v.{CURRENT_VERSION}")
        self.settings = QSettings("DXF", "DXFConstructor")
        self.document = Document()
        self.document.update_auto_name()
        self._load_title_block_settings()
        self._load_shutter_layout_settings()
        self._user_view = False
        self._undo_stack = QUndoStack(self)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        header = QHBoxLayout()
        header.addWidget(QLabel("Контур:"))
        self.btnContourRect = QPushButton("Прямоугольник")
        self.btnContourRect.setObjectName("contourToggle")
        self.btnContourRect.setCheckable(True)
        self.btnContourRect.setChecked(True)
        self.btnContourCircle = QPushButton("Круг")
        self.btnContourCircle.setObjectName("contourToggle")
        self.btnContourCircle.setCheckable(True)
        contour_grp = QButtonGroup(self)
        contour_grp.setExclusive(True)
        contour_grp.addButton(self.btnContourRect)
        contour_grp.addButton(self.btnContourCircle)
        self.btnContourRect.toggled.connect(self._on_contour_kind)
        header.addWidget(self.btnContourRect)
        header.addWidget(self.btnContourCircle)
        self.btnImportDxf = QPushButton("Импорт DXF")
        self.btnImportDxf.clicked.connect(self._import_dxf)
        header.addWidget(self.btnImportDxf)
        header.addStretch()
        root.addLayout(header)

        toolbar = QHBoxLayout()
        self.btnAddHole = QPushButton("+ Отверстие")
        self.btnAddHole.clicked.connect(self._add_hole)
        self.btnAddArray = QPushButton("+ Массив")
        self.btnAddArray.clicked.connect(self._add_array)
        self.btnAddArray.setEnabled(False)
        self.btnExportDxf = QPushButton("Экспорт DXF")
        self.btnExportDxf.clicked.connect(self._export_dxf)
        self.chkExportPng = QCheckBox("PNG")
        self.chkExportPng.setChecked(self.settings.value("exportPng", True, type=bool))
        self.chkExportPng.toggled.connect(
            lambda checked: self.settings.setValue("exportPng", checked),
        )
        self.btnFit = QPushButton("Вписать")
        self.btnFit.clicked.connect(self._fit_view)
        self.btnMeasure = QPushButton("Размер")
        self.btnMeasure.setObjectName("toolToggle")
        self.btnMeasure.setCheckable(True)
        self.btnMeasure.clicked.connect(self._toggle_measure)
        self.btnShutters = QPushButton("Шторки")
        self.btnShutters.setObjectName("toolToggle")
        self.btnShutters.setCheckable(True)
        self.btnShutters.clicked.connect(self._toggle_shutters)
        self.btnAuxLine = QPushButton("Всп. линия")
        self.btnAuxLine.setObjectName("toolToggle")
        self.btnAuxLine.setCheckable(True)
        self.btnAuxLine.clicked.connect(self._toggle_aux_line)
        self.btnRectangle = QPushButton("Прямоугольник")
        self.btnRectangle.setObjectName("toolToggle")
        self.btnRectangle.setCheckable(True)
        self.btnRectangle.clicked.connect(self._toggle_rectangle)
        toolbar.addWidget(self.btnAddHole)
        toolbar.addWidget(self.btnAddArray)
        toolbar.addWidget(self.btnMeasure)
        toolbar.addWidget(self.btnShutters)
        toolbar.addWidget(self.btnAuxLine)
        toolbar.addWidget(self.btnRectangle)
        toolbar.addWidget(self.btnExportDxf)
        toolbar.addWidget(self.chkExportPng)
        toolbar.addWidget(self.btnFit)
        toolbar.addWidget(QLabel("Шрифт:"))
        self.spinFont = FocusSpinBox()
        self.spinFont.setRange(4, 24)
        self.spinFont.setValue(self.document.default_font_size)
        self.spinFont.valueChanged.connect(self._on_font_changed)
        toolbar.addWidget(self.spinFont)
        toolbar.addStretch()
        root.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.element_tree = ElementTree(self.document)
        splitter.addWidget(self.element_tree)

        self.scene = QGraphicsScene(self)
        self.view = EditorView(
            self.scene,
            on_user_view=self._on_user_view,
            on_clear_selection=self._clear_selection,
            on_nudge=self._nudge_selection,
            on_space=self._toggle_dimension_visibility,
            on_measure_mode_changed=self._set_measure_mode,
            on_shutter_mode_changed=self._set_shutter_mode,
            on_aux_line_mode_changed=self._set_aux_line_mode,
            on_rectangle_mode_changed=self._set_rectangle_mode,
            on_origin_placement_done=self._on_origin_placed,
        )
        self.scene_ctrl = EditorSceneController(
            self.document, self.scene,
            on_edit_dimension=self._edit_dimension,
            on_add_shutter=self._add_shutter_from_draw,
            on_add_infinite_line=self._add_infinite_line_from_tool,
            on_add_rectangle=self._add_rectangle_from_draw,
        )
        self.view.set_scene_controller(self.scene_ctrl)

        editor_wrap = QWidget()
        self.editor_wrap = editor_wrap
        editor_lay = QVBoxLayout(editor_wrap)
        editor_lay.setContentsMargins(0, 0, 0, 0)
        editor_lay.setSpacing(0)
        editor_lay.addWidget(self.view, 1)
        self.title_block = TitleBlockWidget(
            self.document,
            on_select=self._select_title_block,
            on_edit_field=self._edit_title_block_field,
            on_edit_logo=self._edit_title_block_logo,
        )
        editor_lay.addWidget(self.title_block)
        splitter.addWidget(editor_wrap)

        self.properties = PropertiesPanel(
            self.document, self._apply_property_change, on_reorigin=self._begin_origin_placement,
        )
        splitter.addWidget(self.properties)

        splitter.setSizes([200, 700, 280])
        root.addWidget(splitter, 1)

        self.document.subscribe(self._on_document_changed)

        act_undo = QAction("Отменить", self)
        act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        act_undo.triggered.connect(self._undo_stack.undo)
        act_redo = QAction("Повторить", self)
        act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        act_redo.triggered.connect(self._undo_stack.redo)
        act_del = QAction("Удалить", self)
        act_del.setShortcut(QKeySequence.StandardKey.Delete)
        act_del.triggered.connect(self._delete_selected)
        act_save = QAction("Сохранить DXF", self)
        act_save.setShortcut(QKeySequence.StandardKey.Save)
        act_save.triggered.connect(self._export_dxf)
        self.addAction(act_undo)
        self.addAction(act_redo)
        self.addAction(act_del)
        self.addAction(act_save)

        self._rebuild_scene()
        self.title_block.refresh()
        check_update(self)

    def _load_title_block_settings(self) -> None:
        tb = self.document.title_block
        tb.developer = self.settings.value("developer", "", type=str)
        logo_path = self.settings.value("logoPath", "", type=str)
        if not logo_path:
            logo_path = self._default_logo_path()
        tb.logo_path = logo_path
        tb.logo_text = self.settings.value("logoText", "", type=str)
        tb.logo_mode = self.settings.value("logoMode", "image", type=str)

    def _load_shutter_layout_settings(self) -> None:
        from app.geometry.shutter import (
            GAP_HORIZONTAL, GAP_VERTICAL, SHUTTER_H, SHUTTER_THIN_W, SHUTTER_WIDE_W,
        )
        lp = self.document.shutter_layout
        lp.gap_horizontal = self.settings.value("shutterGapHorizontal", GAP_HORIZONTAL, type=float)
        lp.gap_vertical = self.settings.value("shutterGapVertical", GAP_VERTICAL, type=float)
        lp.wide_width = self.settings.value("shutterWideWidth", SHUTTER_WIDE_W, type=float)
        lp.thin_width = self.settings.value("shutterThinWidth", SHUTTER_THIN_W, type=float)
        lp.cell_height = self.settings.value("shutterCellHeight", SHUTTER_H, type=float)

    def _persist_shutter_layout_settings(self) -> None:
        lp = self.document.shutter_layout
        self.settings.setValue("shutterGapHorizontal", lp.gap_horizontal)
        self.settings.setValue("shutterGapVertical", lp.gap_vertical)
        self.settings.setValue("shutterWideWidth", lp.wide_width)
        self.settings.setValue("shutterThinWidth", lp.thin_width)
        self.settings.setValue("shutterCellHeight", lp.cell_height)

    def _on_contour_kind(self, rect_checked: bool):
        if self.document.contour_kind == ContourKind.DXF:
            return
        def apply():
            self.document.contour_kind = ContourKind.RECT if rect_checked else ContourKind.CIRCLE
            self.document.update_auto_name()
        self._undo_stack.push(PropertyChangeCommand(self.document, apply, "Тип контура"))

    def _on_font_changed(self, size: int):
        if size == self.document.default_font_size:
            return
        self.document.default_font_size = size
        self.document.apply_default_font_size(size)
        self.document.notify()

    def _persist_title_block_settings(self) -> None:
        tb = self.document.title_block
        self.settings.setValue("developer", tb.developer)
        self.settings.setValue("logoPath", tb.logo_path)
        self.settings.setValue("logoText", tb.logo_text)
        self.settings.setValue("logoMode", tb.logo_mode)

    def _select_title_block(self) -> None:
        self.document.select(SelectionKind.TITLE_BLOCK, "", notify=True)

    def _deactivate_tool_buttons(self) -> None:
        for btn in (self.btnMeasure, self.btnShutters, self.btnAuxLine, self.btnRectangle):
            btn.blockSignals(True)
            btn.setChecked(False)
            btn.blockSignals(False)

    def _set_measure_mode(self, active: bool) -> None:
        self.btnMeasure.blockSignals(True)
        self.btnMeasure.setChecked(active)
        self.btnMeasure.blockSignals(False)
        if active:
            self._deactivate_tool_buttons()
            self.btnMeasure.setChecked(True)
            self.scene_ctrl.cancel_shutter()
            self.scene_ctrl.cancel_aux_line()
            self.scene_ctrl.cancel_rectangle()
            self.scene_ctrl.set_measure_mode(True)
            self.view.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.scene_ctrl.cancel_measure()
            if not self.scene_ctrl.origin_placement_mode:
                self.view.setCursor(Qt.CursorShape.ArrowCursor)

    def _set_shutter_mode(self, active: bool) -> None:
        self.btnShutters.blockSignals(True)
        self.btnShutters.setChecked(active)
        self.btnShutters.blockSignals(False)
        if active:
            self._deactivate_tool_buttons()
            self.btnShutters.setChecked(True)
            self.scene_ctrl.cancel_measure()
            self.scene_ctrl.cancel_origin_placement()
            self.scene_ctrl.cancel_aux_line()
            self.scene_ctrl.cancel_rectangle()
            self.scene_ctrl.set_shutter_mode(True)
            self.view.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.scene_ctrl.cancel_shutter()
            if not self.scene_ctrl.origin_placement_mode:
                self.view.setCursor(Qt.CursorShape.ArrowCursor)

    def _set_aux_line_mode(self, active: bool) -> None:
        self.btnAuxLine.blockSignals(True)
        self.btnAuxLine.setChecked(active)
        self.btnAuxLine.blockSignals(False)
        if active:
            self._deactivate_tool_buttons()
            self.btnAuxLine.setChecked(True)
            self.scene_ctrl.cancel_measure()
            self.scene_ctrl.cancel_shutter()
            self.scene_ctrl.cancel_rectangle()
            self.scene_ctrl.cancel_origin_placement()
            self.scene_ctrl.set_aux_line_mode(True)
            self.view.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.scene_ctrl.cancel_aux_line()
            if not self.scene_ctrl.origin_placement_mode:
                self.view.setCursor(Qt.CursorShape.ArrowCursor)

    def _set_rectangle_mode(self, active: bool) -> None:
        self.btnRectangle.blockSignals(True)
        self.btnRectangle.setChecked(active)
        self.btnRectangle.blockSignals(False)
        if active:
            self._deactivate_tool_buttons()
            self.btnRectangle.setChecked(True)
            self.scene_ctrl.cancel_measure()
            self.scene_ctrl.cancel_shutter()
            self.scene_ctrl.cancel_aux_line()
            self.scene_ctrl.cancel_origin_placement()
            self.scene_ctrl.set_rectangle_mode(True)
            self.view.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.scene_ctrl.cancel_rectangle()
            if not self.scene_ctrl.origin_placement_mode:
                self.view.setCursor(Qt.CursorShape.ArrowCursor)

    def _on_origin_placed(self, x: float, y: float) -> None:
        def apply():
            self.document.place_dxf_origin(x, y)
            self.document.select(SelectionKind.ORIGIN, notify=False)

        self._undo_stack.push(PropertyChangeCommand(self.document, apply, "Базовая точка"))
        self._user_view = False
        self.view.setCursor(Qt.CursorShape.ArrowCursor)
        self.document.notify()

    def _begin_origin_placement(self) -> None:
        self.scene_ctrl.cancel_measure()
        self.scene_ctrl.cancel_shutter()
        self.scene_ctrl.cancel_aux_line()
        self.scene_ctrl.cancel_rectangle()
        self._deactivate_tool_buttons()
        self.scene_ctrl.start_origin_placement()
        self.view.setCursor(Qt.CursorShape.CrossCursor)

    def _toggle_measure(self, checked: bool) -> None:
        if checked:
            self.scene_ctrl.set_measure_mode(True)
            self._set_measure_mode(True)
        else:
            self.scene_ctrl.cancel_measure()
            self._set_measure_mode(False)

    def _toggle_shutters(self, checked: bool) -> None:
        if checked:
            self._set_shutter_mode(True)
        else:
            self._set_shutter_mode(False)

    def _toggle_aux_line(self, checked: bool) -> None:
        if checked:
            self._set_aux_line_mode(True)
        else:
            self._set_aux_line_mode(False)

    def _toggle_rectangle(self, checked: bool) -> None:
        if checked:
            self._set_rectangle_mode(True)
        else:
            self._set_rectangle_mode(False)

    def _add_shutter_from_draw(self, cx: float, cy: float, width: float, height: float) -> None:
        from app.models.base import ShutterRegion
        n = len(self.document.shutters)
        shutter = ShutterRegion(
            cx=cx, cy=cy, width=width, height=height,
            name=f"Шторки {n + 1}",
            color=self.document.next_hole_color(),
        )
        self._undo_stack.push(AddShutterCommand(self.document, shutter))

    def _add_infinite_line_from_tool(
        self, x1: float, y1: float, x2: float, y2: float, offset: float,
        source_anchor=None,
    ) -> None:
        from app.geometry.infinite_line_bind import init_infinite_geometry
        from app.models.base import InfiniteLine, MeasureAnchor
        line = InfiniteLine(
            name=f"Всп. линия {len(self.document.infinite_lines) + 1}",
            color=self.document.next_hole_color(),
            source_anchor=source_anchor or MeasureAnchor(),
        )
        init_infinite_geometry(line, x1, y1, x2, y2, offset)
        self._undo_stack.push(AddInfiniteLineCommand(self.document, line))

    def _add_rectangle_from_draw(self, cx: float, cy: float, width: float, height: float) -> None:
        from app.models.base import DrawnRectangle
        rect = DrawnRectangle(
            cx=cx, cy=cy, width=width, height=height,
            name=f"Прямоугольник {len(self.document.drawn_rects) + 1}",
            color=self.document.next_hole_color(),
        )
        self._undo_stack.push(AddDrawnRectCommand(self.document, rect))

    def _edit_title_block_field(self, field: str) -> None:
        from PyQt6.QtWidgets import QInputDialog
        doc = self.document
        labels = {
            "developer": "Разработал",
            "name": "Наименование",
            "designation": "Обозначение",
        }
        if field not in labels:
            return
        current = {
            "developer": doc.title_block.developer,
            "name": doc.name,
            "designation": doc.designation,
        }[field]
        text, ok = QInputDialog.getText(self, labels[field], f"{labels[field]}:", text=current)
        if not ok:
            return

        def apply():
            if field == "developer":
                doc.title_block.developer = text.strip()
                self._persist_title_block_settings()
            elif field == "name":
                doc.name = text.strip()
            else:
                doc.designation = text.strip()

        self._undo_stack.push(PropertyChangeCommand(doc, apply, "Таблица"))

    def _edit_title_block_logo(self) -> None:
        from PyQt6.QtWidgets import QInputDialog
        tb = self.document.title_block
        if tb.logo_mode == "text":
            text, ok = QInputDialog.getText(
                self, "Текст лого", "Текст:", text=tb.logo_text,
            )
            if not ok:
                return

            def apply():
                tb.logo_text = text.strip()
                self._persist_title_block_settings()

            self._undo_stack.push(PropertyChangeCommand(self.document, apply, "Текст лого"))
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбрать изображение", tb.logo_path,
            "Изображения (*.png *.jpg *.jpeg *.bmp *.svg)",
        )
        if not path:
            return

        def apply():
            tb.logo_path = path
            tb.logo_mode = "image"
            self._persist_title_block_settings()

        self._undo_stack.push(PropertyChangeCommand(self.document, apply, "Логотип"))

    def _on_user_view(self):
        self._user_view = True

    def _apply_property_change(self, fn):
        self._undo_stack.push(PropertyChangeCommand(self.document, fn, "Изменение свойства"))

    def _on_document_changed(self):
        sel = self.document.selection
        self.btnAddArray.setEnabled(sel.kind in (SelectionKind.HOLE, SelectionKind.ARRAY))
        is_dxf = self.document.contour_kind == ContourKind.DXF
        self.btnContourRect.setEnabled(not is_dxf)
        self.btnContourCircle.setEnabled(not is_dxf)
        self.btnContourRect.blockSignals(True)
        self.btnContourCircle.blockSignals(True)
        if is_dxf:
            self.btnContourRect.setChecked(False)
            self.btnContourCircle.setChecked(False)
        else:
            is_rect = self.document.contour_kind == ContourKind.RECT
            self.btnContourRect.setChecked(is_rect)
            self.btnContourCircle.setChecked(not is_rect)
        self.btnContourRect.blockSignals(False)
        self.btnContourCircle.blockSignals(False)
        self._persist_title_block_settings()
        self._persist_shutter_layout_settings()
        saved = self.view.transform() if self._user_view else None
        rect = self._rebuild_scene()
        self.title_block.refresh()
        if saved is not None:
            self.view.setTransform(saved)
        elif not self._user_view:
            self.view.fit_document(rect)

    def _rebuild_scene(self):
        return self.scene_ctrl.rebuild()

    def _add_hole(self):
        from app.models.base import Hole
        hole = Hole(
            cx=10.0, cy=10.0, diameter=6.0,
            color=self.document.next_hole_color(),
            name=f"Отверстие {len(self.document.holes) + 1}",
        )
        self._undo_stack.push(AddHoleCommand(self.document, hole))

    def _clear_selection(self):
        self.document.select(SelectionKind.NONE)

    def _nudge_selection(self, dx: float, dy: float) -> bool:
        return self.scene_ctrl.nudge_selection(dx, dy)

    def _toggle_dimension_visibility(self) -> bool:
        return self.scene_ctrl.toggle_selected_dimension_visibility()

    def _edit_dimension(self, dim_id: str) -> None:
        from app.models.base import HoleKind
        from app.ui.dim_dialogs import PolygonDiameterDialog, TwoSizeDialog

        doc = self.document
        if doc.is_annotation_locked(dim_id):
            return
        if dim_id.startswith("note_") and dim_id.endswith("_d"):
            hole = doc.get_hole(dim_id[5:-2])
            if hole is not None and hole.kind == HoleKind.POLYGON:
                dlg = PolygonDiameterDialog(hole.diameter, hole.sides, self)
                if dlg.exec() != dlg.DialogCode.Accepted:
                    return
                d, s = dlg.values()

                def apply():
                    doc.set_hole_polygon_dims(hole.id, d, s)

                self._undo_stack.push(PropertyChangeCommand(doc, apply, "Изменение размера"))
                return

        if dim_id.startswith("note_") and dim_id not in (
            "note_contour_corner", "note_contour_d",
        ) and not dim_id.endswith(("_r", "_a", "_s", "_ang", "_d")):
            hole = doc.get_hole(dim_id[5:])
            if hole is not None and hole.kind in (HoleKind.RECT, HoleKind.OVAL):
                w_lbl = "Длина:" if hole.kind == HoleKind.OVAL else "Ширина:"
                h_lbl = "Диаметр торца:" if hole.kind == HoleKind.OVAL else "Высота:"
                dlg = TwoSizeDialog(
                    "Изменить размер", w_lbl, h_lbl, hole.width, hole.height, self,
                )
                if dlg.exec() != dlg.DialogCode.Accepted:
                    return
                w, h = dlg.values()

                def apply():
                    doc.set_hole_leader_sizes(hole.id, w, h)

                self._undo_stack.push(PropertyChangeCommand(doc, apply, "Изменение размера"))
                return

        value = doc.get_dimension_value(dim_id)
        if value is None:
            return
        from PyQt6.QtWidgets import QInputDialog
        label = "Значение размера:"
        if dim_id.startswith("note_") and dim_id.endswith(("_a", "_s", "_ang")):
            label = "Угол, °:"
        new_val, ok = QInputDialog.getDouble(
            self, "Изменить размер", label, value, -100000.0, 100000.0, 2,
        )
        if not ok:
            return

        def apply():
            doc.set_dimension_value(dim_id, new_val)

        self._undo_stack.push(PropertyChangeCommand(doc, apply, "Изменение размера"))

    def _add_array(self):
        sel = self.document.selection
        hole_id = ""
        if sel.kind == SelectionKind.HOLE:
            hole_id = sel.object_id
        elif sel.kind == SelectionKind.ARRAY:
            arr = self.document.get_array(sel.object_id)
            if arr:
                hole_id = arr.source_hole_id
        if not hole_id:
            return
        from app.models.base import HoleArray
        hole = self.document.get_hole(hole_id)
        if hole is None:
            return
        cx, cy = self.document.contour_center()
        import math
        n = len(self.document.arrays_for_hole(hole_id)) + 1
        arr = HoleArray(
            source_hole_id=hole_id,
            name=f"Массив {n}",
            center_x=cx, center_y=cy,
            radius=math.hypot(hole.cx - cx, hole.cy - cy) or 30.0,
        )
        self._undo_stack.push(AddArrayCommand(self.document, arr))

    def _delete_selected(self):
        if self.document.selection.kind == SelectionKind.NONE:
            return
        if self.document.selection.kind == SelectionKind.TITLE_BLOCK:
            return
        self._undo_stack.push(DeleteCommand(self.document))

    def _fit_view(self):
        self._user_view = False
        self.view.fit_document(self.scene_ctrl.content_rect())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._user_view:
            self.view.fit_document(self.scene_ctrl.content_rect())

    @staticmethod
    def _project_root() -> str:
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    @classmethod
    def _default_logo_path(cls) -> str:
        path = os.path.join(cls._project_root(), "АКОЛЕД.jpg")
        return path if os.path.isfile(path) else ""

    @staticmethod
    def _sanitize_export_name(text: str) -> str:
        cleaned = re.sub(r'[\\/:*?"<>|]', "_", text.strip())
        return cleaned or "part"

    def _export_basename(self) -> str:
        des_raw = self.document.designation.strip()
        name = self._sanitize_export_name(self.document.name or "part")
        if des_raw:
            designation = self._sanitize_export_name(des_raw)
            return f"{designation} _ {name}"
        return name

    def _import_dxf(self):
        last = self.settings.value("lastSavePath", os.path.expanduser("~"))
        path, _ = QFileDialog.getOpenFileName(
            self, "Импорт DXF", last, "DXF (*.dxf);;Все файлы (*.*)",
        )
        if not path:
            return
        try:
            def apply():
                apply_dxf_contour(self.document, path)
                self.document.update_auto_name()
                self.document.select(SelectionKind.CONTOUR, notify=False)

            self._undo_stack.push(PropertyChangeCommand(self.document, apply, "Импорт DXF"))
            self._user_view = False
            self.document.notify()
            self.settings.setValue("lastSavePath", os.path.dirname(path))
            QMessageBox.information(
                self,
                "Базовая точка",
                "Установите базовую точку.\n\n"
                "Кликните по нужному месту на контуре — координаты будут "
                "отсчитываться от этой точки.",
            )
            self._begin_origin_placement()
        except Exception as e:
            QMessageBox.critical(self, "Импорт DXF", str(e))

    def _export_dxf(self):
        default = f"{self._export_basename()}.dxf"
        last = self.settings.value("lastSavePath", os.path.expanduser("~"))
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить DXF", os.path.join(last, default), "DXF (*.dxf)")
        if not path:
            return
        if not path.lower().endswith(".dxf"):
            path += ".dxf"
        try:
            export_dxf(self.document, path)
            self.settings.setValue("lastSavePath", os.path.dirname(path))
            self.settings.setValue("lastExportBase", os.path.splitext(path)[0])
            saved = [path]
            if self.chkExportPng.isChecked():
                png_path = os.path.splitext(path)[0] + ".png"
                export_png(
                    self.view, png_path,
                    include_title_block=self.document.title_block.include_in_png,
                    editor_widget=self.editor_wrap,
                )
                saved.append(png_path)
            QMessageBox.information(self, "Успех", "Сохранено:\n" + "\n".join(saved))
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))


def main():
    import sys
    from PyQt6.QtWidgets import QApplication
    from app.theme import apply_theme
    app = QApplication(sys.argv)
    apply_theme(app)
    window = MainWindow()
    window.resize(1200, 800)
    window.show()
    sys.exit(app.exec())
