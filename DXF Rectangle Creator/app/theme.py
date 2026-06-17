from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPalette, QPen, QPixmap
from PyQt6.QtWidgets import QApplication

_CHECK_ICON_FILE = Path(__file__).with_name("check_indicator.png")


def _make_check_icon(color: str) -> QIcon:
    pm = QPixmap(16, 16)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color))
    pen.setWidthF(2.2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.drawLine(3, 8, 6, 11)
    painter.drawLine(6, 11, 13, 4)
    painter.end()
    return QIcon(pm)


def _check_icon_url() -> str:
    if not _CHECK_ICON_FILE.exists():
        _make_check_icon("#ffffff").pixmap(16, 16).save(str(_CHECK_ICON_FILE), "PNG")
    return _CHECK_ICON_FILE.as_posix()


def _checkbox_qss(checked_bg: str, unchecked_bg: str, border: str) -> str:
    url = _check_icon_url()
    return f"""
QCheckBox {{
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {border};
    border-radius: 3px;
    background: {unchecked_bg};
}}
QCheckBox::indicator:hover {{
    border-color: {checked_bg};
}}
QCheckBox::indicator:checked {{
    background: {checked_bg};
    border-color: {checked_bg};
    image: url({_check_icon_url()});
}}
"""


LIGHT_QSS = """
QMainWindow, QWidget {
    background-color: #f5f6f8;
    color: #1a1a1a;
    font-size: 13px;
}
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {
    background: #ffffff;
    border: 1px solid #c8ccd4;
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 24px;
}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {
    border-color: #3d7eff;
}
QPushButton, QToolButton {
    background: #ffffff;
    border: 1px solid #c8ccd4;
    border-radius: 6px;
    padding: 6px 12px;
    min-height: 28px;
}
QPushButton:hover, QToolButton:hover {
    background: #eef3ff;
    border-color: #3d7eff;
}
QPushButton:pressed, QToolButton:pressed {
    background: #dce8ff;
}
QPushButton:disabled, QToolButton:disabled {
    color: #9aa0aa;
    background: #f0f1f3;
}
QPushButton#contourToggle, QPushButton#toolToggle {
    min-width: 108px;
    font-weight: 600;
}
QPushButton#contourToggle:checked, QPushButton#toolToggle:checked {
    background: #3d7eff;
    color: #ffffff;
    border-color: #2f6fe0;
}
QPushButton#contourToggle:checked:hover, QPushButton#toolToggle:checked:hover {
    background: #2f6fe0;
}
QGroupBox {
    border: 1px solid #d8dce3;
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 8px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QTreeWidget, QListWidget {
    background: #ffffff;
    border: 1px solid #d8dce3;
    border-radius: 8px;
}
QSplitter::handle {
    background: #e2e5eb;
    width: 2px;
}
QScrollArea {
    border: none;
    background: transparent;
}
""" + _checkbox_qss("#3d7eff", "#ffffff", "#8a919d")

DARK_QSS = """
QMainWindow, QWidget {
    background-color: #1e1f24;
    color: #e8eaed;
    font-size: 13px;
}
QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {
    background: #2b2d34;
    border: 1px solid #454955;
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 24px;
    color: #e8eaed;
}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {
    border-color: #5b9aff;
}
QPushButton, QToolButton {
    background: #2b2d34;
    border: 1px solid #454955;
    border-radius: 6px;
    padding: 6px 12px;
    min-height: 28px;
    color: #e8eaed;
}
QPushButton:hover, QToolButton:hover {
    background: #353842;
    border-color: #5b9aff;
}
QPushButton:pressed, QToolButton:pressed {
    background: #3d4250;
}
QPushButton:disabled, QToolButton:disabled {
    color: #6b7280;
    background: #25262b;
}
QPushButton#contourToggle, QPushButton#toolToggle {
    min-width: 108px;
    font-weight: 600;
}
QPushButton#contourToggle:checked, QPushButton#toolToggle:checked {
    background: #5b9aff;
    color: #ffffff;
    border-color: #4a8ae8;
}
QPushButton#contourToggle:checked:hover, QPushButton#toolToggle:checked:hover {
    background: #4a8ae8;
}
QGroupBox {
    border: 1px solid #454955;
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 8px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QTreeWidget, QListWidget {
    background: #2b2d34;
    border: 1px solid #454955;
    border-radius: 8px;
    color: #e8eaed;
}
QSplitter::handle {
    background: #454955;
    width: 2px;
}
QScrollArea {
    border: none;
    background: transparent;
}
""" + _checkbox_qss("#5b9aff", "#1e1f24", "#8b93a1")


def is_dark_mode() -> bool:
    app = QApplication.instance()
    if app is None:
        return False
    hints = app.styleHints()
    if hasattr(hints, "colorScheme"):
        return hints.colorScheme() == Qt.ColorScheme.Dark
    return app.palette().color(app.palette().ColorRole.Window).lightness() < 128


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    dark = is_dark_mode()
    app.setStyleSheet(DARK_QSS if dark else LIGHT_QSS)
    pal = app.palette()
    if dark:
        pal.setColor(QPalette.ColorRole.Window, QColor("#1e1f24"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#e8eaed"))
        pal.setColor(QPalette.ColorRole.Base, QColor("#2b2d34"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#e8eaed"))
        pal.setColor(QPalette.ColorRole.Button, QColor("#2b2d34"))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor("#e8eaed"))
        pal.setColor(QPalette.ColorRole.Highlight, QColor("#5b9aff"))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    else:
        pal.setColor(QPalette.ColorRole.Highlight, QColor("#3d7eff"))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(pal)


def canvas_colors() -> dict:
    if is_dark_mode():
        return {
            "background": QColor("#25262b"),
            "grid": QColor("#353842"),
            "contour": QColor("#e8eaed"),
            "selection": QColor("#5b9aff"),
            "hole": QColor("#ff6b6b"),
            "dim": QColor("#9aa0aa"),
            "contour_dim": QColor("#ffffff"),
            "dim_locked": QColor("#e8a317"),
        }
    return {
        "background": QColor("#ffffff"),
        "grid": QColor("#eef0f4"),
        "contour": QColor("#1a1a1a"),
        "selection": QColor("#3d7eff"),
        "hole": QColor("#e03131"),
        "dim": QColor("#495057"),
        "contour_dim": QColor("#1a1a1a"),
        "dim_locked": QColor("#c92a2a"),
    }
