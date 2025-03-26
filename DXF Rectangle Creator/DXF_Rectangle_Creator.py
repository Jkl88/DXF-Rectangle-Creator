import sys
import math
import os
import ezdxf
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QDoubleSpinBox, QSpinBox, QLineEdit, QPushButton, QFileDialog,
    QMessageBox, QScrollArea, QGraphicsView, QGraphicsScene
)
from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QPainter, QTransform, QColor, QPen, QDesktopServices, QPainterPath

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
        self.setWindowTitle("DXF Конструктор: Прямоугольник и Отверстия")

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
        row2.addWidget(QLabel("Радиус скругления:"))
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
        self.spinWidth.valueChanged.connect(self.update_preview)
        self.spinHeight.valueChanged.connect(self.update_preview)
        self.spinCornerRadius.valueChanged.connect(self.update_preview)

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
        controlsLayout.addLayout(buttonsLayout)

        mainLayout.addWidget(controlsWidget)

        # Предпросмотр (нижняя часть)
        self.previewScene = QGraphicsScene(self)
        self.previewView = QGraphicsView(self.previewScene)
        self.previewView.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.previewView.setMinimumHeight(400)
        # Инвертируем ось Y, чтобы (0,0) было в нижнем левом углу
        self.previewView.setTransform(QTransform().scale(1, -1))
        mainLayout.addWidget(self.previewView)

        # Список цветов для массивов (назначаются циклически)
        self.color_list = ["red", "blue", "green", "orange", "purple", "magenta", "cyan"]

        self.update_preview()

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

    def update_preview(self):
        self.previewScene.clear()
        margin = 10
        max_extent_x = 0
        max_extent_y = 0

        # Получаем размеры прямоугольника
        width = self.spinWidth.value()
        height = self.spinHeight.value()
        corner_radius = self.spinCornerRadius.value()
        pen_rect = QPen(Qt.GlobalColor.black)
        pen_rect.setCosmetic(True)
        if corner_radius > 0:
            # Рисуем скруглённый прямоугольник через QPainterPath
            path = QPainterPath()
            path.addRoundedRect(0, 0, width, height, corner_radius, corner_radius)
            self.previewScene.addPath(path, pen_rect)
        else:
            self.previewScene.addRect(0, 0, width, height, pen_rect)
        max_extent_x = max(max_extent_x, width)
        max_extent_y = max(max_extent_y, height)

        # Обрабатываем каждый массив отверстий
        for idx in range(self.arraysLayout.count()):
            widget = self.arraysLayout.itemAt(idx).widget()
            if widget is not None:
                (offset_left, offset_bottom, hole_diameter,
                 count_vert, gap_vert, count_horz, gap_horz) = widget.get_values()
                max_extent_x = max(max_extent_x, offset_left + (count_horz - 1) * gap_horz + hole_diameter)
                max_extent_y = max(max_extent_y, offset_bottom + (count_vert - 1) * gap_vert + hole_diameter)
                color_name = self.color_list[idx % len(self.color_list)]
                pen_array = QPen(QColor(color_name))
                pen_array.setCosmetic(True)
                widget.label.setStyleSheet(f"color: {color_name};")
                for i in range(count_vert):
                    for j in range(count_horz):
                        cx = offset_left + j * gap_horz
                        cy = offset_bottom + i * gap_vert
                        hole_radius = hole_diameter / 2.0
                        self.previewScene.addEllipse(cx - hole_radius, cy - hole_radius,
                                                     hole_diameter, hole_diameter, pen_array)

        self.previewScene.setSceneRect(0 - margin, 0 - margin,
                                       max_extent_x + 2 * margin, max_extent_y + 2 * margin)
        self.previewView.fitInView(self.previewScene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.lineName.setText(f"R_{self.spinWidth.value():.2f}x{self.spinHeight.value():.2f}")

    def generate_dxf(self):
        width = self.spinWidth.value()
        height = self.spinHeight.value()
        corner_radius = self.spinCornerRadius.value()
        doc = ezdxf.new(dxfversion="R2010")
        msp = doc.modelspace()

        if corner_radius > 0:
            # Создаем линии и дуги для скруглённого прямоугольника:
            # Нижняя линия:
            msp.add_line((corner_radius, 0), (width - corner_radius, 0))
            # Нижняя правая дуга: центр (width - r, r), от 270 до 360
            msp.add_arc(center=(width - corner_radius, corner_radius), radius=corner_radius, start_angle=270, end_angle=360)
            # Правая линия:
            msp.add_line((width, corner_radius), (width, height - corner_radius))
            # Верхняя правая дуга: центр (width - r, height - r), от 0 до 90
            msp.add_arc(center=(width - corner_radius, height - corner_radius), radius=corner_radius, start_angle=0, end_angle=90)
            # Верхняя линия:
            msp.add_line((width - corner_radius, height), (corner_radius, height))
            # Верхняя левая дуга: центр (r, height - r), от 90 до 180
            msp.add_arc(center=(corner_radius, height - corner_radius), radius=corner_radius, start_angle=90, end_angle=180)
            # Левая линия:
            msp.add_line((0, height - corner_radius), (0, corner_radius))
            # Нижняя левая дуга: центр (r, r), от 180 до 270
            msp.add_arc(center=(corner_radius, corner_radius), radius=corner_radius, start_angle=180, end_angle=270)
        else:
            # Обычный прямоугольник
            points = [(0, 0), (width, 0), (width, height), (0, height), (0, 0)]
            msp.add_lwpolyline(points, close=True)

        # Добавляем отверстия для каждого массива
        for idx in range(self.arraysLayout.count()):
            widget = self.arraysLayout.itemAt(idx).widget()
            if widget is not None:
                (offset_left, offset_bottom, hole_diameter,
                 count_vert, gap_vert, count_horz, gap_horz) = widget.get_values()
                for i in range(count_vert):
                    for j in range(count_horz):
                        cx = offset_left + j * gap_horz
                        cy = offset_bottom + i * gap_vert
                        msp.add_circle(center=(cx, cy), radius=hole_diameter / 2.0)

        designation = self.lineDesignation.text().strip()
        name = self.lineName.text().strip() if self.lineName.text().strip() else f"R_{self.spinWidth.value():.2f}x{self.spinHeight.value():.2f}"
        if designation:
            default_filename = f"{designation}_{name}.dxf"
        else:
            default_filename = f"{name}.dxf"

        file_path, _ = QFileDialog.getSaveFileName(self, "Сохранить DXF", default_filename, filter="DXF файлы (*.dxf)")
        if file_path:
            if not file_path.lower().endswith(".dxf"):
                file_path += ".dxf"
            try:
                doc.saveas(file_path)
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("Успех")
                msg_box.setText(f"Файл успешно сохранён:\n{file_path}")
                open_folder_button = msg_box.addButton("Открыть папку", QMessageBox.ButtonRole.ActionRole)
                msg_box.addButton("Закрыть", QMessageBox.ButtonRole.RejectRole)
                msg_box.exec()
                if msg_box.clickedButton() == open_folder_button:
                    folder = os.path.dirname(file_path)
                    QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Ошибка при сохранении файла:\n{str(e)}")

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(720, 700)
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
