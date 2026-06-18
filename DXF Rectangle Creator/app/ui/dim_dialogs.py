from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout,
)

from app.ui.widgets import FocusDoubleSpinBox, FocusNumericLineEdit, FocusSpinBox


class ValueInputDialog(QDialog):
    def __init__(
        self, title: str, label: str, value: float = 0.0,
        minimum: float = 0.0, maximum: float = 100000.0,
        seed_text: str | None = None, parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        initial = seed_text if seed_text is not None else str(value)
        self.field = FocusNumericLineEdit(
            minimum=minimum, maximum=maximum, text=initial,
        )
        form.addRow(label, self.field)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def showEvent(self, event):
        super().showEvent(event)
        self.field.setFocus()
        self.field.deselect()
        self.field.setCursorPosition(len(self.field.text()))

    def value(self) -> float:
        return self.field.numeric_value()


class TwoSizeDialog(QDialog):
    def __init__(self, title: str, label_a: str, label_b: str,
                 value_a: float, value_b: float, parent=None,
                 seed_text_a: str | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(title))
        form = QFormLayout()
        self._seeded_a = seed_text_a is not None
        if self._seeded_a:
            self.field_a = FocusNumericLineEdit(text=seed_text_a or "")
            self.spin_b = FocusDoubleSpinBox()
            self.spin_b.setRange(0.1, 100000.0)
            self.spin_b.setDecimals(2)
            self.spin_b.setValue(value_b)
            form.addRow(label_a, self.field_a)
            form.addRow(label_b, self.spin_b)
        else:
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

    def showEvent(self, event):
        super().showEvent(event)
        if self._seeded_a:
            self.field_a.setFocus()
            self.field_a.deselect()
            self.field_a.setCursorPosition(len(self.field_a.text()))

    def values(self) -> tuple[float, float]:
        if self._seeded_a:
            return self.field_a.numeric_value(), self.spin_b.value()
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
