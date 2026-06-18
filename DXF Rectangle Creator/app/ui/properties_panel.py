from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from app.formatting import format_dim
from app.models.base import (
    ArrayKind, ContourKind, CornerMode, HoleKind, MirrorAxis, SelectionKind,
    ShutterLayoutParams,
)
from app.models.document import Document
from app.ui.widgets import FocusDoubleSpinBox, FocusSpinBox


class PropertiesPanel(QScrollArea):
    def __init__(self, document: Document, on_change, on_reorigin=None, parent=None):
        super().__init__(parent)
        self.document = document
        self.on_change = on_change
        self.on_reorigin = on_reorigin
        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setWidget(self._container)
        self.setWidgetResizable(True)
        self.setMinimumWidth(260)
        document.subscribe(self._on_doc_changed)
        self._block = False
        self.refresh()

    def _on_doc_changed(self):
        fw = QApplication.focusWidget()
        if fw and self.isAncestorOf(fw) and isinstance(fw, (FocusSpinBox, FocusDoubleSpinBox, QLineEdit)):
            return
        self.refresh()

    def refresh(self):
        sel = self.document.selection
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if sel.kind == SelectionKind.CONTOUR:
            self._build_contour()
        elif sel.kind == SelectionKind.HOLE:
            hole = self.document.get_hole(sel.object_id)
            if hole:
                self._build_hole(hole)
        elif sel.kind == SelectionKind.ARRAY:
            arr = self.document.get_array(sel.object_id)
            if arr:
                self._build_array(arr, sel.instance_index)
        elif sel.kind == SelectionKind.DIMENSION:
            self._build_dimension(sel.object_id)
        elif sel.kind == SelectionKind.TITLE_BLOCK:
            self._build_title_block()
        elif sel.kind == SelectionKind.MEASURE:
            m = self.document.get_measure(sel.object_id)
            if m:
                self._build_measure(m)
        elif sel.kind == SelectionKind.SHUTTER:
            s = self.document.get_shutter(sel.object_id)
            if s:
                self._build_shutter(s)
        elif sel.kind == SelectionKind.INFINITE_LINE:
            line = self.document.get_infinite_line(sel.object_id)
            if line:
                self._build_infinite_line(line)
        elif sel.kind == SelectionKind.DRAWN_RECT:
            r = self.document.get_drawn_rect(sel.object_id)
            if r:
                self._build_drawn_rect(r)
        elif sel.kind == SelectionKind.ORIGIN:
            self._build_origin()
        else:
            self._layout.addWidget(QLabel("Выберите элемент"))
        self._layout.addStretch()

    def _spin_f(self, val, mn=-10000, mx=10000, dec=2, suffix=" мм", on_apply=None):
        s = FocusDoubleSpinBox()
        s.setRange(mn, mx)
        s.setDecimals(dec)
        s.setValue(val)
        s.setSuffix(suffix)
        if on_apply:
            s.valueChanged.connect(on_apply)
        return s

    def _spin_i(self, val, mn=-10000, mx=10000, on_apply=None):
        s = FocusSpinBox()
        s.setRange(mn, mx)
        s.setValue(val)
        if on_apply:
            s.valueChanged.connect(on_apply)
        return s

    def _set_attr(self, getter, attr, value, after=None):
        def apply():
            obj = getter()
            if obj is None:
                return
            setattr(obj, attr, value)
            if after:
                after()
        self._chg(apply)

    def _set_hole_attr(self, hole_id: str, attr: str, value):
        def apply():
            hole = self.document.get_hole(hole_id)
            if hole is None:
                return
            if attr == "cx":
                self.document.move_primary_hole(hole_id, value, hole.cy)
            elif attr == "cy":
                self.document.move_primary_hole(hole_id, hole.cx, value)
            else:
                setattr(hole, attr, value)
        self._chg(apply)

    def _set_instance_show(self, hole_id: str, index: int, value: bool):
        def apply():
            self.document.get_instance_state(hole_id, index).always_show = value
        self._chg(apply)

    def _set_object_show_dims(self, kind: str, object_id: str, value: bool):
        def apply():
            self.document.set_object_show_dims(kind, object_id, value)
        self._chg(apply)

    def _add_show_dims_row(self, form: QFormLayout, kind: str, object_id: str = "") -> None:
        st = self.document.get_object_state(kind, object_id)
        vis = QCheckBox()
        vis.setChecked(st.show_dims)
        vis.toggled.connect(
            lambda v, k=kind, oid=object_id: self._set_object_show_dims(k, oid, v),
        )
        form.addRow("Показать размеры:", vis)

    def _set_font_size(self, dim_id: str, is_leader: bool, value: int) -> None:
        def apply():
            if is_leader:
                st = self.document.get_leader_state(dim_id)
            else:
                st = self.document.get_dim_state(dim_id)
            st.font_size = value
            st.font_size_custom = True
        self._chg(apply)

    def _add_annotation_lock_row(self, form: QFormLayout, ann_id: str, is_leader: bool) -> None:
        locked = QCheckBox()
        if is_leader:
            st = self.document.get_leader_state(ann_id)
            locked.setChecked(st.locked)
            locked.toggled.connect(
                lambda v, aid=ann_id: self._set_attr(
                    lambda: self.document.get_leader_state(aid), "locked", v,
                ),
            )
        else:
            st = self.document.get_dim_state(ann_id)
            locked.setChecked(st.locked)
            locked.toggled.connect(
                lambda v, aid=ann_id: self._set_attr(
                    lambda: self.document.get_dim_state(aid), "locked", v,
                ),
            )
        form.addRow("Зафиксировать:", locked)

    def _build_title_block(self) -> None:
        from datetime import date
        g = QGroupBox("Таблица")
        form = QFormLayout(g)
        doc = self.document
        tb = doc.title_block

        dev = QLineEdit(tb.developer)
        dev.editingFinished.connect(
            lambda: self._chg(lambda: setattr(doc.title_block, "developer", dev.text())),
        )
        form.addRow("Разработал:", dev)

        form.addRow("Дата:", QLabel(date.today().strftime("%d.%m.%Y")))

        name = QLineEdit(doc.name)
        name.editingFinished.connect(lambda: self._chg(lambda: setattr(doc, "name", name.text())))
        form.addRow("Наименование:", name)

        des = QLineEdit(doc.designation)
        des.editingFinished.connect(lambda: self._chg(lambda: setattr(doc, "designation", des.text())))
        form.addRow("Обозначение:", des)

        logo_mode = QComboBox()
        logo_mode.addItems(["Изображение", "Текст"])
        logo_mode.setCurrentIndex(0 if tb.logo_mode == "image" else 1)
        logo_mode.currentIndexChanged.connect(
            lambda i: self._set_attr(
                lambda: doc.title_block, "logo_mode", "image" if i == 0 else "text",
            ),
        )
        form.addRow("Лого:", logo_mode)

        logo_text = QLineEdit(tb.logo_text)
        logo_text.editingFinished.connect(
            lambda: self._chg(lambda: setattr(doc.title_block, "logo_text", logo_text.text())),
        )
        form.addRow("Текст лого:", logo_text)

        logo_path = QLabel(tb.logo_path or "—")
        logo_path.setWordWrap(True)
        btn_logo = QPushButton("Выбрать изображение…")
        btn_logo.clicked.connect(self._pick_logo)
        form.addRow("Файл лого:", logo_path)
        form.addRow("", btn_logo)

        png = QCheckBox()
        png.setChecked(tb.include_in_png)
        png.toggled.connect(
            lambda v: self._set_attr(lambda: doc.title_block, "include_in_png", v),
        )
        form.addRow("Выводить в PNG:", png)
        self._layout.addWidget(g)

    def _pick_logo(self) -> None:
        from PyQt6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "Выбрать изображение", self.document.title_block.logo_path,
            "Изображения (*.png *.jpg *.jpeg *.bmp)",
        )
        if path:
            self._chg(lambda: setattr(self.document.title_block, "logo_path", path))

    def _build_measure(self, m) -> None:
        g = QGroupBox("Измерение")
        form = QFormLayout(g)
        mid = m.id
        if m.kind == "diameter":
            form.addRow("Тип:", QLabel("Диаметр"))
            form.addRow("Значение:", QLabel(f"Ø{format_dim(m.size)} мм"))
        elif m.kind == "radius":
            form.addRow("Тип:", QLabel("Радиус"))
            form.addRow("Значение:", QLabel(f"R{format_dim(m.size)} мм"))
        else:
            dist = ((m.p2x - m.p1x) ** 2 + (m.p2y - m.p1y) ** 2) ** 0.5
            form.addRow("ΔX:", QLabel(f"{format_dim(abs(m.p2x - m.p1x))} мм"))
            form.addRow("ΔY:", QLabel(f"{format_dim(abs(m.p2y - m.p1y))} мм"))
            form.addRow("Расстояние:", QLabel(f"{format_dim(dist)} мм"))
        st = self.document.get_object_state("measure", mid)
        vis = QCheckBox()
        vis.setChecked(st.show_dims)
        vis.toggled.connect(
            lambda v, oid=mid: self._set_object_show_dims("measure", oid, v),
        )
        form.addRow("Показать размеры:", vis)
        self._layout.addWidget(g)

    def _build_shutter(self, s) -> None:
        from app.geometry.shutter import SHUTTER_ANGLES, layout_shutters, normalize_shutter_angle
        g = QGroupBox("Шторки")
        form = QFormLayout(g)
        sid = s.id
        lp = self.document.shutter_layout
        angle_box = QComboBox()
        angle_box.addItems([f"{a}°" for a in SHUTTER_ANGLES])
        current = normalize_shutter_angle(s.angle)
        if current in SHUTTER_ANGLES:
            angle_box.setCurrentIndex(SHUTTER_ANGLES.index(current))
        angle_box.currentIndexChanged.connect(
            lambda i, oid=sid: self._set_shutter_angle(oid, SHUTTER_ANGLES[i]),
        )
        form.addRow("Угол:", angle_box)
        sp_x = self._spin_f(s.cx, on_apply=lambda v: self._set_shutter_attr(sid, "cx", v))
        sp_y = self._spin_f(s.cy, on_apply=lambda v: self._set_shutter_attr(sid, "cy", v))
        sp_w = self._spin_f(s.width, 1, 10000, on_apply=lambda v: self._set_shutter_attr(sid, "width", v))
        sp_h = self._spin_f(s.height, 1, 10000, on_apply=lambda v: self._set_shutter_attr(sid, "height", v))
        form.addRow("Центр X:", sp_x)
        form.addRow("Центр Y:", sp_y)
        form.addRow("Ширина:", sp_w)
        form.addRow("Высота:", sp_h)

        form.addRow(QLabel(""))
        form.addRow(QLabel("Параметры ячейки"))
        sp_gap_h = self._spin_f(
            lp.gap_horizontal, 0, 1000, 2,
            on_apply=lambda v: self._set_shutter_layout_attr("gap_horizontal", v),
        )
        sp_gap_v = self._spin_f(
            lp.gap_vertical, 0, 1000, 2,
            on_apply=lambda v: self._set_shutter_layout_attr("gap_vertical", v),
        )
        sp_wide = self._spin_f(
            lp.wide_width, 0.1, 1000, 2,
            on_apply=lambda v: self._set_shutter_layout_attr("wide_width", v),
        )
        sp_thin = self._spin_f(
            lp.thin_width, 0.1, 1000, 2,
            on_apply=lambda v: self._set_shutter_layout_attr("thin_width", v),
        )
        sp_cell_h = self._spin_f(
            lp.cell_height, 0.1, 1000, 2,
            on_apply=lambda v: self._set_shutter_layout_attr("cell_height", v),
        )
        form.addRow("Интервал горизонт.:", sp_gap_h)
        form.addRow("Интервал вертик.:", sp_gap_v)
        form.addRow("Широкая часть:", sp_wide)
        form.addRow("Часть DXF:", sp_thin)
        form.addRow("Высота ячейки:", sp_cell_h)
        form.addRow(
            "Ячейка:",
            QLabel(f"{format_dim(lp.cell_width)} × {format_dim(lp.cell_height)}"),
        )
        if current in (0, 180):
            dxf_size = f"{format_dim(lp.thin_width)} × {format_dim(lp.cell_height)}"
        else:
            dxf_size = f"{format_dim(lp.cell_height)} × {format_dim(lp.thin_width)}"
        parts = layout_shutters(s.cx, s.cy, s.width, s.height, s.angle, lp)
        thin = sum(1 for p in parts if p.thin)
        form.addRow(f"Элементов DXF ({dxf_size}):", QLabel(str(thin)))
        btn_reset = QPushButton("По умолчанию")
        btn_reset.clicked.connect(self._reset_shutter_layout)
        form.addRow("", btn_reset)

        st = self.document.get_object_state("shutter", sid)
        vis = QCheckBox()
        vis.setChecked(st.show_dims)
        vis.toggled.connect(lambda v, oid=sid: self._set_object_show_dims("shutter", oid, v))
        form.addRow("Показать размеры:", vis)
        self._layout.addWidget(g)

    def _set_shutter_layout_attr(self, attr: str, value: float) -> None:
        def apply():
            v = max(0.0, value) if attr.startswith("gap_") else max(0.1, value)
            setattr(self.document.shutter_layout, attr, v)
        self._chg(apply)

    def _reset_shutter_layout(self) -> None:
        def apply():
            self.document.shutter_layout = ShutterLayoutParams.defaults()
        self._chg(apply)

    def _set_shutter_angle(self, shutter_id: str, angle: float) -> None:
        def apply():
            s = self.document.get_shutter(shutter_id)
            if s is None:
                return
            s.angle = float(angle)
        self._chg(apply)

    def _set_shutter_attr(self, shutter_id: str, attr: str, value: float) -> None:
        def apply():
            s = self.document.get_shutter(shutter_id)
            if s is None:
                return
            setattr(s, attr, value)
        self._chg(apply)

    def _build_infinite_line(self, line) -> None:
        g = QGroupBox("Вспомогательная линия")
        form = QFormLayout(g)
        lid = line.id
        sp_off = self._spin_f(
            line.offset, -10000, 10000,
            on_apply=lambda v: self._set_infinite_line_offset(lid, v),
        )
        form.addRow("Смещение:", sp_off)
        form.addRow("Расстояние:", QLabel(format_dim(abs(line.offset))))
        locked = QCheckBox()
        locked.setChecked(line.locked)
        locked.toggled.connect(lambda v, oid=lid: self._set_infinite_line_locked(oid, v))
        form.addRow("Зафиксировать:", locked)
        st = self.document.get_object_state("infinite_line", lid)
        vis = QCheckBox()
        vis.setChecked(st.show_dims)
        vis.toggled.connect(lambda v, oid=lid: self._set_object_show_dims("infinite_line", oid, v))
        form.addRow("Показать размер:", vis)
        self._layout.addWidget(g)

    def _set_infinite_line_offset(self, line_id: str, value: float) -> None:
        def apply():
            line = self.document.get_infinite_line(line_id)
            if line is None:
                return
            from app.geometry.infinite_line_bind import set_infinite_line_distance
            set_infinite_line_distance(line, self.document, abs(value))
        self._chg(apply)

    def _set_infinite_line_locked(self, line_id: str, value: bool) -> None:
        def apply():
            line = self.document.get_infinite_line(line_id)
            if line is None:
                return
            line.locked = value
        self._chg(apply)

    def _set_infinite_line_attr(self, line_id: str, attr: str, value: float) -> None:
        def apply():
            line = self.document.get_infinite_line(line_id)
            if line is None:
                return
            setattr(line, attr, value)
        self._chg(apply)

    def _build_drawn_rect(self, r) -> None:
        g = QGroupBox("Прямоугольник")
        form = QFormLayout(g)
        rid = r.id
        sp_x = self._spin_f(r.cx, on_apply=lambda v: self._set_drawn_rect_attr(rid, "cx", v))
        sp_y = self._spin_f(r.cy, on_apply=lambda v: self._set_drawn_rect_attr(rid, "cy", v))
        sp_w = self._spin_f(r.width, 1, 10000, on_apply=lambda v: self._set_drawn_rect_attr(rid, "width", v))
        sp_h = self._spin_f(r.height, 1, 10000, on_apply=lambda v: self._set_drawn_rect_attr(rid, "height", v))
        form.addRow("Центр X:", sp_x)
        form.addRow("Центр Y:", sp_y)
        form.addRow("Ширина:", sp_w)
        form.addRow("Высота:", sp_h)
        self._add_show_dims_row(form, "drawn_rect", rid)
        self._layout.addWidget(g)

    def _set_drawn_rect_attr(self, rect_id: str, attr: str, value: float) -> None:
        def apply():
            r = self.document.get_drawn_rect(rect_id)
            if r is None:
                return
            setattr(r, attr, value)
        self._chg(apply)

    def _build_contour(self):
        g = QGroupBox("Контур")
        form = QFormLayout(g)
        doc = self.document
        if doc.contour_kind == ContourKind.DXF:
            form.addRow("Тип:", QLabel("Импортированный DXF"))
            if doc.dxf_contour.source_file:
                form.addRow("Файл:", QLabel(doc.dxf_contour.source_file))
            form.addRow("Элементов:", QLabel(str(len(doc.dxf_contour.entities))))
            _, _, w, h = doc.contour_bounds()
            form.addRow("Габариты:", QLabel(f"{w:.1f} × {h:.1f} мм"))
            self._add_show_dims_row(form, "contour")
            self._layout.addWidget(g)
            return
        if doc.contour_kind == ContourKind.CIRCLE:
            sp = self._spin_f(
                doc.circle.diameter, 1, 10000,
                on_apply=lambda v: self._set_attr(
                    lambda: self.document.circle, "diameter", v, after=self.document.update_auto_name,
                ),
            )
            form.addRow("Диаметр:", sp)
        else:
            sp_w = self._spin_f(
                doc.rect.width, 1, 10000,
                on_apply=lambda v: self._chg(lambda: (
                    setattr(self.document.rect, "width", v),
                    self.document.rect.clamp_corner(),
                    self.document.update_auto_name(),
                )),
            )
            sp_h = self._spin_f(
                doc.rect.height, 1, 10000,
                on_apply=lambda v: self._chg(lambda: (
                    setattr(self.document.rect, "height", v),
                    self.document.rect.clamp_corner(),
                    self.document.update_auto_name(),
                )),
            )
            form.addRow("Ширина:", sp_w)
            form.addRow("Высота:", sp_h)
            mode = QComboBox()
            mode.addItems(["Радиус", "Фаска"])
            mode.setCurrentIndex(0 if doc.rect.corner_mode == CornerMode.RADIUS else 1)
            mode.currentIndexChanged.connect(
                lambda i: self._set_attr(
                    lambda: self.document.rect, "corner_mode",
                    CornerMode.RADIUS if i == 0 else CornerMode.CHAMFER,
                ),
            )
            form.addRow("Угол:", mode)
            sp_c = self._spin_f(
                doc.rect.corner_size, 0, doc.rect.max_corner_size(),
                on_apply=lambda v: self._set_attr(lambda: self.document.rect, "corner_size", v),
            )
            form.addRow("Размер:", sp_c)
        self._add_show_dims_row(form, "contour")
        self._layout.addWidget(g)

    def _build_origin(self):
        g = QGroupBox("Нулевая точка")
        form = QFormLayout(g)
        ox, oy = self.document.datum_origin()
        form.addRow("X:", QLabel(format_dim(ox)))
        form.addRow("Y:", QLabel(format_dim(oy)))
        form.addRow("", QLabel("Координаты отверстий отсчитываются от этой точки."))
        if self.on_reorigin is not None:
            btn = QPushButton("Переустановка 0")
            btn.clicked.connect(self._on_reorigin)
            form.addRow("", btn)
        self._layout.addWidget(g)

    def _on_reorigin(self):
        if self.on_reorigin is not None:
            self.on_reorigin()

    def _build_hole(self, hole):
        g = QGroupBox("Отверстие")
        form = QFormLayout(g)
        hole_id = hole.id
        kind = QComboBox()
        kind.addItems(["Круглое", "Квадратное", "Овальное", "Многоугольное"])
        kind.setCurrentIndex(list(HoleKind).index(hole.kind))
        kind.currentIndexChanged.connect(
            lambda i: self._set_attr(
                lambda: self.document.get_hole(hole_id), "kind", list(HoleKind)[i],
            ),
        )
        form.addRow("Тип:", kind)
        ccx, ccy = self.document.contour_center()
        is_circle = self.document.contour_kind == ContourKind.CIRCLE
        ox, oy = self.document.datum_origin()
        if is_circle:
            sp_x = self._spin_f(
                hole.cx - ccx,
                on_apply=lambda v: self._set_hole_attr(
                    hole_id, "cx", v + self.document.contour_center()[0],
                ),
            )
            sp_y = self._spin_f(
                hole.cy - ccy,
                on_apply=lambda v: self._set_hole_attr(
                    hole_id, "cy", v + self.document.contour_center()[1],
                ),
            )
            form.addRow("X от центра:", sp_x)
            form.addRow("Y от центра:", sp_y)
        elif self.document.contour_kind == ContourKind.DXF:
            sp_x = self._spin_f(
                hole.cx - ox,
                on_apply=lambda v: self._set_hole_attr(hole_id, "cx", v + ox),
            )
            sp_y = self._spin_f(
                hole.cy - oy,
                on_apply=lambda v: self._set_hole_attr(hole_id, "cy", v + oy),
            )
            form.addRow("X от нуля:", sp_x)
            form.addRow("Y от нуля:", sp_y)
        else:
            sp_x = self._spin_f(hole.cx, on_apply=lambda v: self._set_hole_attr(hole_id, "cx", v))
            sp_y = self._spin_f(hole.cy, on_apply=lambda v: self._set_hole_attr(hole_id, "cy", v))
            form.addRow("Центр X:", sp_x)
            form.addRow("Центр Y:", sp_y)
        if hole.kind == HoleKind.CIRCLE:
            sp_d = self._spin_f(
                hole.diameter, 0.1, 10000,
                on_apply=lambda v: self._set_attr(lambda: self.document.get_hole(hole_id), "diameter", v),
            )
            form.addRow("Диаметр:", sp_d)
        elif hole.kind == HoleKind.POLYGON:
            sp_d = self._spin_f(
                hole.diameter, 0.1, 10000,
                on_apply=lambda v: self._set_attr(lambda: self.document.get_hole(hole_id), "diameter", v),
            )
            sp_s = self._spin_i(
                hole.sides, 3, 64,
                on_apply=lambda v: self._set_attr(lambda: self.document.get_hole(hole_id), "sides", v),
            )
            sp_a = self._spin_f(
                hole.angle, -360, 360, 1, "°",
                on_apply=lambda v: self._set_attr(lambda: self.document.get_hole(hole_id), "angle", v),
            )
            form.addRow("Вписанный Ø:", sp_d)
            form.addRow("Граней:", sp_s)
            form.addRow("Угол:", sp_a)
        else:
            sp_w = self._spin_f(
                hole.width, 0.1, 10000,
                on_apply=lambda v: self._set_attr(lambda: self.document.get_hole(hole_id), "width", v),
            )
            sp_h = self._spin_f(
                hole.height, 0.1, 10000,
                on_apply=lambda v: self._set_attr(lambda: self.document.get_hole(hole_id), "height", v),
            )
            sp_a = self._spin_f(
                hole.angle, -360, 360, 1, "°",
                on_apply=lambda v: self._set_attr(lambda: self.document.get_hole(hole_id), "angle", v),
            )
            if hole.kind == HoleKind.OVAL:
                form.addRow("Длина:", sp_w)
                form.addRow("Диаметр торца:", sp_h)
            else:
                form.addRow("Ширина:", sp_w)
                form.addRow("Высота:", sp_h)
            form.addRow("Угол:", sp_a)
        self._add_show_dims_row(form, "hole", hole_id)
        self._layout.addWidget(g)

    def _build_array(self, arr, instance_index: int = -1):
        g = QGroupBox("Массив")
        form = QFormLayout(g)
        arr_id = arr.id
        kind = QComboBox()
        kind.addItems(["По сетке", "Зеркальный", "По окружности"])
        kind.setCurrentIndex(list(ArrayKind).index(arr.kind))
        kind.currentIndexChanged.connect(
            lambda i: self._set_attr(
                lambda: self.document.get_array(arr_id), "kind", list(ArrayKind)[i],
            ),
        )
        form.addRow("Тип:", kind)
        self._add_show_dims_row(form, "array", arr_id)
        if arr.kind == ArrayKind.GRID:
            doc = self.document
            for label, attr, is_int in [
                ("Кол-во X:", "count_x", True), ("Кол-во Y:", "count_y", True),
            ]:
                sp = self._spin_i(
                    getattr(arr, attr), 1, 1000,
                    on_apply=lambda v, a=attr: self._set_attr(
                        lambda: self.document.get_array(arr_id), a, v,
                    ),
                )
                form.addRow(label, sp)
            span_x = doc.grid_array_span_x(arr)
            span_y = doc.grid_array_span_y(arr)
            sp_sx = self._spin_f(
                arr.step_x, -100000, 100000, 2,
                on_apply=lambda v: self._chg(
                    lambda: doc.set_grid_array_step_x(doc.get_array(arr_id), v),
                ),
            )
            sp_sy = self._spin_f(
                arr.step_y, -100000, 100000, 2,
                on_apply=lambda v: self._chg(
                    lambda: doc.set_grid_array_step_y(doc.get_array(arr_id), v),
                ),
            )
            sp_lx = self._spin_f(
                span_x, 0, 100000, 2,
                on_apply=lambda v: self._chg(
                    lambda: doc.set_grid_array_span_x(doc.get_array(arr_id), v),
                ),
            )
            sp_lx.setEnabled(arr.count_x > 1)
            sp_ly = self._spin_f(
                span_y, 0, 100000, 2,
                on_apply=lambda v: self._chg(
                    lambda: doc.set_grid_array_span_y(doc.get_array(arr_id), v),
                ),
            )
            sp_ly.setEnabled(arr.count_y > 1)
            form.addRow("Шаг X:", sp_sx)
            form.addRow("Длина X:", sp_lx)
            form.addRow("Шаг Y:", sp_sy)
            form.addRow("Длина Y:", sp_ly)
            sp_ang = self._spin_f(
                arr.grid_angle, -10000, 10000, 1, "°",
                on_apply=lambda v: self._set_attr(
                    lambda: self.document.get_array(arr_id), "grid_angle", v,
                ),
            )
            form.addRow("Угол:", sp_ang)
        elif arr.kind == ArrayKind.MIRROR:
            axis = QComboBox()
            axis.addItems(["Горизонталь", "Вертикаль"])
            axis.setCurrentIndex(0 if arr.mirror_axis == MirrorAxis.HORIZONTAL else 1)
            axis.currentIndexChanged.connect(
                lambda i: self._set_attr(
                    lambda: self.document.get_array(arr_id), "mirror_axis",
                    MirrorAxis.HORIZONTAL if i == 0 else MirrorAxis.VERTICAL,
                ),
            )
            form.addRow("Ось:", axis)
        if arr.kind == ArrayKind.CIRCULAR:
            sp_cx = self._spin_f(
                arr.center_x,
                on_apply=lambda v: self._chg(lambda: (
                    setattr(self.document.get_array(arr_id), "center_x", v),
                    self.document.sync_circular_array_radius(self.document.get_array(arr_id)),
                )),
            )
            sp_cy = self._spin_f(
                arr.center_y,
                on_apply=lambda v: self._chg(lambda: (
                    setattr(self.document.get_array(arr_id), "center_y", v),
                    self.document.sync_circular_array_radius(self.document.get_array(arr_id)),
                )),
            )
            sp_r = self._spin_f(
                arr.radius, 0, 10000,
                on_apply=lambda v: self._chg(
                    lambda: self.document.move_circular_array_radius(self.document.get_array(arr_id), v),
                ),
            )
            sp_n = self._spin_i(
                arr.count, 2, 360,
                on_apply=lambda v: self._set_attr(lambda: self.document.get_array(arr_id), "count", v),
            )
            sp_a = self._spin_f(
                arr.step_angle, 0, 360, 1, "°",
                on_apply=lambda v: self._set_attr(lambda: self.document.get_array(arr_id), "step_angle", v),
            )
            form.addRow("Центр X:", sp_cx)
            form.addRow("Центр Y:", sp_cy)
            form.addRow("Радиус:", sp_r)
            form.addRow("Кол-во:", sp_n)
            form.addRow("Шаг:", sp_a)
            fixed = QCheckBox()
            fixed.setChecked(arr.center_fixed)
            fixed.toggled.connect(
                lambda v: self._set_attr(
                    lambda: self.document.get_array(arr_id), "center_fixed", v,
                ),
            )
            form.addRow("Зафиксировать:", fixed)
        self._layout.addWidget(g)

        if instance_index > 0:
            hole_id = arr.source_hole_id
            st = self.document.get_instance_state(hole_id, instance_index)
            g_inst = QGroupBox(f"Экземпляр {instance_index}")
            form_inst = QFormLayout(g_inst)
            vis = QCheckBox()
            vis.setChecked(st.always_show)
            vis.toggled.connect(
                lambda v, hid=hole_id, idx=instance_index: self._set_instance_show(hid, idx, v),
            )
            form_inst.addRow("Показать:", vis)
            self._layout.addWidget(g_inst)

    def _build_dimension(self, dim_id: str):
        g = QGroupBox("Размер / сноска")
        form = QFormLayout(g)
        doc = self.document
        if dim_id.startswith("note_"):
            st = doc.get_leader_state(dim_id)
            if dim_id.endswith("_r"):
                arr_id = dim_id[5:-2]
                arr = doc.get_array(arr_id)
                if arr is not None and arr.kind == ArrayKind.CIRCULAR:
                    sp_r = self._spin_f(
                        arr.radius, 0, 10000,
                        on_apply=lambda v, aid=arr_id: self._chg(
                            lambda: self.document.move_circular_array_radius(
                                self.document.get_array(aid), v,
                            ),
                        ),
                    )
                    form.addRow("Радиус:", sp_r)
            elif dim_id.endswith("_a"):
                arr_id = dim_id[5:-2]
                arr = doc.get_array(arr_id)
                angle = doc.circular_array_spoke_angle(arr) if arr else None
                if arr is not None and arr.kind == ArrayKind.CIRCULAR and angle is not None:
                    sp_a = self._spin_f(
                        angle, 0, 360, 1, "°",
                        on_apply=lambda v, aid=arr_id: self._chg(
                            lambda: self.document.set_circular_array_spoke_angle(
                                self.document.get_array(aid), v,
                            ),
                        ),
                    )
                    form.addRow("Угол:", sp_a)
            elif dim_id.endswith("_s"):
                arr_id = dim_id[5:-2]
                arr = doc.get_array(arr_id)
                step = doc.circular_array_step_angle(arr) if arr else None
                if arr is not None and arr.kind == ArrayKind.CIRCULAR and step is not None:
                    sp_s = self._spin_f(
                        step, 0.1, 360, 1, "°",
                        on_apply=lambda v, aid=arr_id: self._chg(
                            lambda: self.document.set_circular_array_step_angle(
                                self.document.get_array(aid), v,
                            ),
                        ),
                    )
                    form.addRow("Шаг:", sp_s)
            elif dim_id == "note_contour_d":
                sp_d = self._spin_f(
                    doc.circle.diameter, 1, 10000,
                    on_apply=lambda v: self._chg(
                        lambda: doc.set_dimension_value("note_contour_d", v),
                    ),
                )
                form.addRow("Диаметр:", sp_d)
            elif dim_id.endswith("_d"):
                hole_id = dim_id[5:-2]
                hole = doc.get_hole(hole_id)
                if hole is not None and hole.kind == HoleKind.POLYGON:
                    sp_d = self._spin_f(
                        hole.diameter, 0.1, 10000,
                        on_apply=lambda v, hid=hole_id: self._set_hole_attr(hid, "diameter", v),
                    )
                    sp_s = self._spin_i(
                        hole.sides, 3, 64,
                        on_apply=lambda v, hid=hole_id: self._set_hole_attr(hid, "sides", v),
                    )
                    form.addRow("Вписанный Ø:", sp_d)
                    form.addRow("Граней:", sp_s)
                elif hole is not None:
                    sp_d = self._spin_f(
                        doc.hole_display_diameter(hole), 0.1, 10000,
                        on_apply=lambda v, d=dim_id: self._chg(
                            lambda: doc.set_dimension_value(d, v),
                        ),
                    )
                    form.addRow("Диаметр:", sp_d)
            elif dim_id.endswith("_ang"):
                hole_id = dim_id[5:-4]
                hole = doc.get_hole(hole_id)
                if hole is not None:
                    sp_a = self._spin_f(
                        hole.angle, -360, 360, 1, "°",
                        on_apply=lambda v, hid=hole_id: self._set_hole_attr(hid, "angle", v),
                    )
                    form.addRow("Угол:", sp_a)
            elif dim_id not in ("note_contour_corner", "note_contour_d"):
                hole_id = dim_id[len("note_"):]
                hole = doc.get_hole(hole_id)
                if hole is not None and hole.kind in (HoleKind.RECT, HoleKind.OVAL):
                    w_lbl = "Длина:" if hole.kind == HoleKind.OVAL else "Ширина:"
                    h_lbl = "Диаметр торца:" if hole.kind == HoleKind.OVAL else "Высота:"
                    sp_w = self._spin_f(
                        hole.width, 0.1, 10000,
                        on_apply=lambda v, hid=hole_id: self._set_hole_attr(hid, "width", v),
                    )
                    sp_h = self._spin_f(
                        hole.height, 0.1, 10000,
                        on_apply=lambda v, hid=hole_id: self._set_hole_attr(hid, "height", v),
                    )
                    form.addRow(w_lbl, sp_w)
                    form.addRow(h_lbl, sp_h)
            vis = QCheckBox()
            vis.setChecked(st.always_show)
            vis.toggled.connect(
                lambda v: self._set_attr(lambda: doc.get_leader_state(dim_id), "always_show", v),
            )
            sp_f = FocusSpinBox()
            sp_f.setRange(2, 60)
            sp_f.setValue(st.font_size)
            sp_f.valueChanged.connect(
                lambda v, d=dim_id: self._set_font_size(d, True, v),
            )
            form.addRow("Показать:", vis)
            form.addRow("Шрифт:", sp_f)
            self._add_annotation_lock_row(form, dim_id, is_leader=True)
        else:
            st = doc.get_dim_state(dim_id)
            value = doc.get_dimension_value(dim_id)
            if value is not None:
                if dim_id in ("w_all", "h_all"):
                    label = "Размер:"
                    mn, dec = 1.0, 2
                else:
                    label = "Размер:"
                    mn, dec = -10000.0, 2
                sp_v = self._spin_f(
                    value, mn, 10000, dec,
                    on_apply=lambda v, d=dim_id: self._chg(lambda: doc.set_dimension_value(d, v)),
                )
                sp_v.setEnabled(not st.locked)
                form.addRow(label, sp_v)
            vis = QCheckBox()
            vis.setChecked(st.always_show)
            vis.toggled.connect(
                lambda v: self._set_attr(lambda: doc.get_dim_state(dim_id), "always_show", v),
            )
            sp_f = FocusSpinBox()
            sp_f.setRange(2, 60)
            sp_f.setValue(st.font_size)
            sp_f.valueChanged.connect(
                lambda v, d=dim_id: self._set_font_size(d, False, v),
            )
            form.addRow("Показать:", vis)
            form.addRow("Шрифт:", sp_f)
            self._add_annotation_lock_row(form, dim_id, is_leader=False)
        self._layout.addWidget(g)

    def _chg(self, fn):
        if self._block:
            return
        self.on_change(fn)
