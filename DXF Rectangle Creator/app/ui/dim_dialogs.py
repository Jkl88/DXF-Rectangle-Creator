from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout,
)

from app.ui.widgets import FocusDoubleSpinBox, FocusSpinBox


class TwoSizeDialog(QDialog):
    def __init__(self, title: str, label_a: str, label_b: str,
                 value_a: float, value_b: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(title))
        form = QFormLayout()
        self.spin_a = FocusDoubleSpinBox()
        self.spin_a.setRange(0.1, 100000.0)
        self.spin_a.setDecimals(2)
        self.spin_a.setValue(value_a)
        self.spin_b = FocusDoubleSpinBox()
        self.spin_b.setRange(0.1, 100000.0)
        self.spin_b.setDecimals(2)
        self.spin_b.setValue(value_b)
        form.addRow(label_a, self.spin_a)
        form.addRow(label_b, self.spin_b)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[float, float]:
        return self.spin_a.value(), self.spin_b.value()


class PolygonDiameterDialog(QDialog):
    def __init__(self, diameter: float, sides: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Многоугольное отверстие")
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Диаметр вписанной окружности и число граней"))
        form = QFormLayout()
        self.spin_d = FocusDoubleSpinBox()
        self.spin_d.setRange(0.1, 100000.0)
        self.spin_d.setDecimals(2)
        self.spin_d.setValue(diameter)
        self.spin_s = FocusSpinBox()
        self.spin_s.setRange(3, 64)
        self.spin_s.setValue(sides)
        form.addRow("Вписанный Ø:", self.spin_d)
        form.addRow("Граней:", self.spin_s)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[float, int]:
        return self.spin_d.value(), int(self.spin_s.value())
