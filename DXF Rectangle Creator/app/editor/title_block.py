from __future__ import annotations

from datetime import date

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QSizePolicy, QWidget

from app.models.base import SelectionKind
from app.models.document import Document
from app.theme import is_dark_mode

NOTE_MAX_LEN = 150


class TitleBlockWidget(QWidget):
    """Fixed title block below the editor viewport (does not pan/zoom)."""

    ROW_H = 56.0
    LOGO_W = 112.0
    COL_LABEL_W = 200.0
    DATE_W = 144.0
    DES_W = 180.0
    PAD = 12.0
    LABEL_H = 24.0
    FONT_PT = 18

    def __init__(
        self, document: Document, on_select, on_edit_field, on_edit_logo, parent=None,
    ):
        super().__init__(parent)
        self.document = document
        self.on_select = on_select
        self.on_edit_field = on_edit_field
        self.on_edit_logo = on_edit_logo
        self._session_note = ""
        self.setFixedHeight(int(self.ROW_H * 2))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self._logo: QPixmap | None = None
        self._reload_logo()

    def _reload_logo(self) -> None:
        tb = self.document.title_block
        if tb.logo_mode != "image":
            self._logo = None
            return
        path = tb.logo_path
        if path:
            pm = QPixmap(path)
            if not pm.isNull():
                self._logo = pm.scaled(
                    int(self.LOGO_W - 8), int(self.ROW_H - 8),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                return
        self._logo = None

    def refresh(self) -> None:
        self._reload_logo()
        self.update()

    def edit_note(self) -> None:
        from PyQt6.QtWidgets import (
            QDialog, QDialogButtonBox, QLabel, QTextEdit, QVBoxLayout,
        )
        dlg = QDialog(self)
        dlg.setWindowTitle("Примечание")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(f"Текст (до {NOTE_MAX_LEN} символов, не сохраняется):"))
        te = QTextEdit()
        te.setPlainText(self._session_note)
        te.setAcceptRichText(False)
        lay.addWidget(te)

        def limit_len():
            text = te.toPlainText()
            if len(text) > NOTE_MAX_LEN:
                te.blockSignals(True)
                te.setPlainText(text[:NOTE_MAX_LEN])
                te.blockSignals(False)

        te.textChanged.connect(limit_len)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._session_note = te.toPlainText()[:NOTE_MAX_LEN]
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        doc = self.document
        tb = doc.title_block
        dark = is_dark_mode()
        border = QColor("#8a919d") if not dark else QColor("#6b7280")
        bg = QColor("#ffffff") if not dark else QColor("#2b2d34")
        text_c = QColor("#1a1a1a") if not dark else QColor("#e8eaed")
        sel = doc.selection.kind == SelectionKind.TITLE_BLOCK
        if sel:
            border = QColor("#3d7eff") if not dark else QColor("#5b9aff")

        w = self.width()
        row_h = self.ROW_H
        total_h = row_h * 2

        font = QFont()
        font.setPointSize(self.FONT_PT)
        painter.setFont(font)
        fm = QFontMetrics(font)

        painter.setPen(QPen(border, 1.0))
        painter.setBrush(bg)
        painter.drawRect(QRectF(0, 0, w, total_h))

        des_w = self.DES_W
        name_w = max(0.0, w - des_w)
        self._paint_cell(
            painter, border, text_c, fm,
            0, 0, des_w, row_h,
            "Обозначение", doc.designation or "—",
        )
        self._paint_cell(
            painter, border, text_c, fm,
            des_w, 0, name_w, row_h,
            "Наименование", doc.name or "—",
        )

        y2 = row_h
        self._paint_logo_cell(painter, border, text_c, fm, 0, y2, self.LOGO_W, row_h, tb)
        self._paint_cell(
            painter, border, text_c, fm,
            self.LOGO_W, y2, self.COL_LABEL_W, row_h,
            "Разработал", tb.developer or "—",
        )
        self._paint_cell(
            painter, border, text_c, fm,
            self.LOGO_W + self.COL_LABEL_W, y2, self.DATE_W, row_h,
            "Дата", date.today().strftime("%d.%m.%Y"),
        )
        rest_w = max(0.0, w - self.LOGO_W - self.COL_LABEL_W - self.DATE_W)
        if rest_w > 0:
            self._paint_note_cell(painter, border, text_c, rest_w, y2, row_h)

    def _paint_cell(
        self, painter, border, text_c, fm,
        x: float, y: float, cw: float, ch: float,
        label: str, value: str,
    ) -> None:
        painter.setPen(QPen(border, 1.0))
        painter.drawRect(QRectF(x, y, cw, ch))
        painter.setPen(QColor("#6b7280"))
        painter.drawText(
            QRectF(x + self.PAD, y + 2, cw - self.PAD * 2, self.LABEL_H),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            label,
        )
        painter.setPen(text_c)
        val_rect = QRectF(x + self.PAD, y + self.LABEL_H + 1, cw - self.PAD * 2, ch - self.LABEL_H - 3)
        elided = fm.elidedText(value, Qt.TextElideMode.ElideRight, int(val_rect.width()))
        painter.drawText(
            val_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            elided,
        )

    def _paint_note_cell(self, painter, border, text_c, cw: float, y: float, ch: float) -> None:
        x = self.LOGO_W + self.COL_LABEL_W + self.DATE_W
        painter.setPen(QPen(border, 1.0))
        painter.drawRect(QRectF(x, y, cw, ch))
        text = self._session_note.strip()
        if not text:
            return
        val_rect = QRectF(x + self.PAD, y + self.PAD, cw - self.PAD * 2, ch - self.PAD * 2)
        font = QFont()
        for pt in range(self.FONT_PT, 5, -1):
            font.setPointSize(pt)
            fm = QFontMetrics(font)
            bounds = fm.boundingRect(
                val_rect.toRect(),
                int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap),
                text,
            )
            if bounds.height() <= val_rect.height() and bounds.width() <= val_rect.width():
                break
        painter.setFont(font)
        painter.setPen(text_c)
        painter.drawText(
            val_rect,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
            text,
        )

    def _paint_logo_cell(self, painter, border, text_c, fm, x, y, cw, ch, tb) -> None:
        painter.setPen(QPen(border, 1.0))
        painter.drawRect(QRectF(x, y, cw, ch))
        if tb.logo_mode == "text" and tb.logo_text:
            painter.setPen(text_c)
            painter.drawText(
                QRectF(x + 2, y + 2, cw - 4, ch - 4),
                Qt.AlignmentFlag.AlignCenter,
                fm.elidedText(tb.logo_text, Qt.TextElideMode.ElideRight, int(cw - 4)),
            )
        elif self._logo is not None:
            lx = x + (cw - self._logo.width()) / 2
            ly = y + (ch - self._logo.height()) / 2
            painter.drawPixmap(int(lx), int(ly), self._logo)
        else:
            painter.setPen(QColor("#6b7280"))
            painter.drawText(
                QRectF(x + 2, y + 2, cw - 4, self.LABEL_H),
                Qt.AlignmentFlag.AlignCenter,
                "Лого",
            )
            hint = tb.logo_text if tb.logo_mode == "text" else "—"
            painter.setPen(text_c)
            painter.drawText(
                QRectF(x + 2, y + self.LABEL_H + 2, cw - 4, ch - self.LABEL_H - 4),
                Qt.AlignmentFlag.AlignCenter,
                fm.elidedText(hint, Qt.TextElideMode.ElideRight, int(cw - 4)),
            )

    def _field_at(self, pos) -> str | None:
        x, y = pos.x(), pos.y()
        w, h = self.width(), self.height()
        if x < 0 or x > w or y < 0 or y > h:
            return None
        row_h = self.ROW_H
        if y < row_h:
            if x < self.DES_W:
                return "designation"
            return "name"
        y -= row_h
        if x < self.LOGO_W:
            return "logo"
        x -= self.LOGO_W
        if x < self.COL_LABEL_W:
            return "developer"
        x -= self.COL_LABEL_W
        if x < self.DATE_W:
            return "date"
        return "note"

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.on_select:
            self.on_select()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseDoubleClickEvent(event)
            return
        field = self._field_at(event.position())
        if field == "date":
            event.accept()
            return
        if field == "note":
            self.edit_note()
        elif field == "logo" and self.on_edit_logo:
            self.on_edit_logo()
        elif field and self.on_edit_field:
            self.on_edit_field(field)
        event.accept()
