from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem

from app.models.base import ContourKind, SelectionKind
from app.models.document import Document


class ElementTree(QTreeWidget):
    def __init__(self, document: Document, parent=None):
        super().__init__(parent)
        self.document = document
        self.setHeaderLabel("Элементы")
        self.itemClicked.connect(self._on_click)
        document.subscribe(self.refresh)

    def refresh(self):
        self.clear()
        doc = self.document
        label = "нет" if doc.contour_kind == ContourKind.NONE else (
            "DXF" if doc.contour_kind == ContourKind.DXF else doc.contour_kind.value
        )
        if doc.contour_kind != ContourKind.NONE:
            contour = QTreeWidgetItem([f"Контур ({label})"])
            contour.setData(0, Qt.ItemDataRole.UserRole, ("contour", ""))
            self.addTopLevelItem(contour)
            if doc.contour_kind == ContourKind.DXF and doc.dxf_contour.origin_set:
                origin = QTreeWidgetItem(["Нулевая точка"])
                origin.setData(0, Qt.ItemDataRole.UserRole, ("origin", ""))
                contour.addChild(origin)

        if doc.holes:
            holes_root = QTreeWidgetItem(["Отверстия"])
            self.addTopLevelItem(holes_root)
            for i, hole in enumerate(doc.holes, 1):
                item = QTreeWidgetItem([hole.display_name(i)])
                item.setData(0, Qt.ItemDataRole.UserRole, ("hole", hole.id))
                for j, arr in enumerate(doc.arrays_for_hole(hole.id), 1):
                    arr_item = QTreeWidgetItem([arr.display_name(j)])
                    arr_item.setData(0, Qt.ItemDataRole.UserRole, ("array", arr.id))
                    item.addChild(arr_item)
                holes_root.addChild(item)
            holes_root.setExpanded(True)

        if doc.measures:
            measures_root = QTreeWidgetItem(["Размеры"])
            self.addTopLevelItem(measures_root)
            for i, m in enumerate(doc.measures, 1):
                m_item = QTreeWidgetItem([m.display_name(i)])
                m_item.setData(0, Qt.ItemDataRole.UserRole, ("measure", m.id))
                measures_root.addChild(m_item)
            measures_root.setExpanded(True)

        if doc.shutters:
            shutters_root = QTreeWidgetItem(["Шторки"])
            self.addTopLevelItem(shutters_root)
            for i, s in enumerate(doc.shutters, 1):
                s_item = QTreeWidgetItem([s.display_name(i)])
                s_item.setData(0, Qt.ItemDataRole.UserRole, ("shutter", s.id))
                shutters_root.addChild(s_item)
            shutters_root.setExpanded(True)

        if doc.infinite_lines:
            aux_root = QTreeWidgetItem(["Всп. линии"])
            self.addTopLevelItem(aux_root)
            for i, line in enumerate(doc.infinite_lines, 1):
                ln_item = QTreeWidgetItem([line.display_name(i)])
                ln_item.setData(0, Qt.ItemDataRole.UserRole, ("infinite_line", line.id))
                aux_root.addChild(ln_item)
            aux_root.setExpanded(True)

        if doc.drawn_rects:
            rects_root = QTreeWidgetItem(["Прямоугольники"])
            self.addTopLevelItem(rects_root)
            for i, r in enumerate(doc.drawn_rects, 1):
                r_item = QTreeWidgetItem([r.display_name(i)])
                r_item.setData(0, Qt.ItemDataRole.UserRole, ("drawn_rect", r.id))
                rects_root.addChild(r_item)
            rects_root.setExpanded(True)

        if doc.drawn_geometries:
            geom_root = QTreeWidgetItem(["Геометрия"])
            self.addTopLevelItem(geom_root)
            for i, g in enumerate(doc.drawn_geometries, 1):
                g_item = QTreeWidgetItem([g.display_name(i)])
                g_item.setData(0, Qt.ItemDataRole.UserRole, ("drawn_geometry", g.id))
                geom_root.addChild(g_item)
            geom_root.setExpanded(True)

        tb = QTreeWidgetItem(["Таблица"])
        tb.setData(0, Qt.ItemDataRole.UserRole, ("title_block", ""))
        self.addTopLevelItem(tb)

        self.expandAll()

    def _on_click(self, item, _col):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind, obj_id = data
        mapping = {
            "contour": SelectionKind.CONTOUR,
            "hole": SelectionKind.HOLE,
            "array": SelectionKind.ARRAY,
            "measure": SelectionKind.MEASURE,
            "shutter": SelectionKind.SHUTTER,
            "infinite_line": SelectionKind.INFINITE_LINE,
            "drawn_rect": SelectionKind.DRAWN_RECT,
            "drawn_geometry": SelectionKind.DRAWN_GEOMETRY,
            "title_block": SelectionKind.TITLE_BLOCK,
            "origin": SelectionKind.ORIGIN,
        }
        self.document.select(mapping.get(kind, SelectionKind.NONE), obj_id)
