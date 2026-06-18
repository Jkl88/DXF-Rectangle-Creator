from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import QDoubleSpinBox, QLineEdit, QSpinBox


class FocusSpinBox(QSpinBox):
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            self.stepBy(1 if event.key() == Qt.Key.Key_Up else -1)
            event.accept()
            return
        super().keyPressEvent(event)


class FocusNumericLineEdit(QLineEdit):
    """Plain numeric field for keyboard entry (no 2 -> 2,00 formatting)."""

    def __init__(
        self, parent=None, minimum: float = 0.0, maximum: float = 100000.0,
        text: str = "",
    ):
        super().__init__(text, parent)
        validator = QDoubleValidator(minimum, maximum, 6, self)
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        self.setValidator(validator)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.deselect()
        self.setCursorPosition(len(self.text()))

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            try:
                val = float(self.text().replace(",", "."))
            except ValueError:
                val = 0.0
            val += 1.0 if event.key() == Qt.Key.Key_Up else -1.0
            self.setText(str(val))
            self.setCursorPosition(len(self.text()))
            event.accept()
            return
        super().keyPressEvent(event)

    def numeric_value(self) -> float:
        text = self.text().strip().replace(",", ".")
        if not text:
            return 0.0
        return float(text)


class FocusDoubleSpinBox(QDoubleSpinBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._preserve_typed_text = False

    def focusInEvent(self, event):
        super().focusInEvent(event)
        if not self._preserve_typed_text:
            return
        self._preserve_typed_text = False
        le = self.lineEdit()
        if le is None:
            return
        pos = len(le.text())
        le.deselect()
        le.setCursorPosition(pos)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            self.stepBy(1 if event.key() == Qt.Key.Key_Up else -1)
            event.accept()
            return
        super().keyPressEvent(event)
