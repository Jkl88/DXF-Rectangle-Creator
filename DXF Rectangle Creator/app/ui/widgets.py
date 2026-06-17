from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDoubleSpinBox, QSpinBox


class FocusSpinBox(QSpinBox):
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            self.stepBy(1 if event.key() == Qt.Key.Key_Up else -1)
            event.accept()
            return
        super().keyPressEvent(event)


class FocusDoubleSpinBox(QDoubleSpinBox):
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            self.stepBy(1 if event.key() == Qt.Key.Key_Up else -1)
            event.accept()
            return
        super().keyPressEvent(event)
