import requests
import sys
import shutil
import tempfile
import math
import os
import ezdxf
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QDoubleSpinBox, QSpinBox, QLineEdit, QPushButton, QFileDialog,
    QMessageBox, QScrollArea, QGraphicsView, QGraphicsScene, QCheckBox
)
from PyQt6.QtCore import Qt, QUrl, QSettings
from PyQt6.QtGui import QPainter, QTransform, QColor, QPen, QDesktopServices, QPainterPath, QImage
from ezdxf.math import Matrix44

CURRENT_VERSION = "1.0.1"

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
        self.setWindowTitle(f"DXF Конструктор: Прямоугольник и Отверстия - v.{CURRENT_VERSION}")

        self.settings = QSettings("DXF", "DXFConstructor")

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
        self.exportPng = QCheckBox("Вывести PNG")
        buttonsLayout.addWidget(self.exportPng)
        self.btnCheckUpdate = QPushButton("Проверка обновления")
        self.btnCheckUpdate.clicked.connect(self.check_update)
        buttonsLayout.addWidget(self.btnCheckUpdate)
        controlsLayout.addLayout(buttonsLayout)

        mainLayout.addWidget(controlsWidget)

        # Предпросмотр (нижняя часть)
        self.previewScene = QGraphicsScene(self)
        self.previewView = QGraphicsView(self.previewScene)
        self.previewView.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.previewView.setMinimumHeight(400)
        # Инвертируем ось Y, чтобы (0,0) было в нижнем левом углу
        #self.previewView.setTransform(QTransform().scale(1, -1))
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

    def save_preview_image(self, file_path_without_ext):
        # получаем сцену
        scene = self.previewScene

        # границы сцены
        rect = scene.sceneRect()

        # создаём QImage подходящего размера
        img = QImage(int(rect.width()), int(rect.height()), QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.white)

        painter = QPainter(img)

        # Рисуем сцену в изображение
        scene.render(painter)
        painter.end()

        # сохраняем PNG
        out_path = file_path_without_ext + ".png"
        img.save(out_path)

        return out_path
    def update_preview(self):
        self.previewScene.clear()

        # -------------------------------
        #  ПАРАМЕТРЫ
        # -------------------------------
        width = self.spinWidth.value()
        height = self.spinHeight.value()
        corner_radius = self.spinCornerRadius.value()

        margin = 10     # большой отступ под размеры
        max_x = width
        max_y = height

        # -------------------------------
        #  ПРЯМОУГОЛЬНИК
        # -------------------------------
        pen_rect = QPen(Qt.GlobalColor.black)
        pen_rect.setCosmetic(True)

        if corner_radius > 0:
            path = QPainterPath()
            path.addRoundedRect(0, 0, width, height, corner_radius, corner_radius)
            self.previewScene.addPath(path, pen_rect)
        else:
            self.previewScene.addRect(0, 0, width, height, pen_rect)

        # -------------------------------
        #  ОТВЕРСТИЯ И ПОДПИСИ
        # -------------------------------
        for idx in range(self.arraysLayout.count()):
            widget = self.arraysLayout.itemAt(idx).widget()
            if widget is None:
                continue

            (ox, oy, d, cv, gv, ch, gh) = widget.get_values()
            rr = d/2
            color = QColor(self.color_list[idx % len(self.color_list)])
            pen_arr = QPen(color)
            pen_arr.setCosmetic(True)
            widget.label.setStyleSheet(f"color: {self.color_list[idx % len(self.color_list)]};")

            # Рисуем отверстия
            for i in range(cv):
                for j in range(ch):
                    cx = ox + j * gh
                    cy = oy + i * gv

                    self.previewScene.addEllipse(cx-rr, cy-rr, d, d, pen_arr)

                    max_x = max(max_x, cx + rr)
                    max_y = max(max_y, cy + rr)

            # ======= ПОДПИСИ (точная привязка) ========

            lx = ox
            ly = oy

            # 1) Отступ X — строго слева от отверстия

            self.previewScene.addLine(ox + rr + 2, oy, 0, oy, color)
            txt_x = self.previewScene.addText(f"{ox:.1f} мм")
            txt_x.setDefaultTextColor(color)
            rect = txt_x.boundingRect()
            txt_x.setPos(ox/2 - rect.width()/2, oy - 20)

            # 2) Отступ Y — строго над отверстием
            self.previewScene.addLine(ox, oy + rr + 2, ox, 0, color)
            txt_y = self.previewScene.addText(f"{oy:.1f} мм")
            txt_y.setDefaultTextColor(color)
            txt_y.setRotation(-90)
            rect = txt_y.boundingRect()
            txt_y.setPos(ox, oy/2 + rect.width()/2)

            # 3) Диаметр
            txt_d = self.previewScene.addText(f"Ø {d:.1f}")
            txt_d.setDefaultTextColor(color)
            txt_d.setPos(lx + rr - 5, ly + rr - 5)

            # 4) Шаг X — между отверстиями
            if ch > 1:
                mid_x = ox + gh * (ch - 1) / 2
                self.previewScene.addLine(ox + gh + rr + 2, oy, ox, oy, color)
                txt_sx = self.previewScene.addText(f"{gh:.1f} мм")
                txt_sx.setDefaultTextColor(color)
                rect = txt_sx.boundingRect()
                txt_sx.setPos((ox + gh)/2 - rect.width()/2, oy - 20)

            # 5) Шаг Y — между отверстиями
            if cv > 1:
                mid_y = oy + gv * (cv - 1) / 2
                self.previewScene.addLine(ox, oy + gv + rr + 2, ox, oy, color)
                txt_sy = self.previewScene.addText(f"{gv:.1f} мм")
                txt_sy.setDefaultTextColor(color)
                txt_sy.setRotation(-90)
                rect = txt_sy.boundingRect()
                txt_sy.setPos(ox, gv/2 + oy + rect.width()/2)

        # -------------------------------
        #  ГАБАРИТНЫЕ РАЗМЕРЫ
        # -------------------------------
        dim_pen = QPen(Qt.GlobalColor.black)
        dim_pen.setCosmetic(True)

        # --- ширина ---
        self.previewScene.addLine(0, height + 15, width, height + 15, dim_pen)
        self.previewScene.addLine(0, height + 10, 0, height + 20, dim_pen)
        self.previewScene.addLine(width, height + 10, width, height + 20, dim_pen)

        txt_w = self.previewScene.addText(f"{width:.2f} мм")
        txt_w.setPos(width/2 - 25, height + 15)

        # --- высота ---
        self.previewScene.addLine(-15, 0, -15, height, dim_pen)
        self.previewScene.addLine(-10, 0, -20, 0, dim_pen)
        self.previewScene.addLine(-10, height, -20, height, dim_pen)

        txt_h = self.previewScene.addText(f"{height:.2f} мм")
        txt_h.setRotation(-90)
        rect = txt_h.boundingRect()
        txt_h.setPos(-35-(rect.height()/2 - 10), height/2 + rect.width()/2)

        # --- радиус ---
        if corner_radius > 0:
            txt_r = self.previewScene.addText(f"R={corner_radius:.1f}")
            txt_r.setPos(width - corner_radius - 40, height - corner_radius + 20)

        # -------------------------------
        #  ГРАНИЦА СЦЕНЫ + fitInView
        # -------------------------------
        self.previewScene.setSceneRect(
            -margin - 50,
            -margin - 50,
            max_x + 2 * margin + 50,
            max_y + 2 * margin + 80,
        )

        self.previewView.fitInView(
            self.previewScene.sceneRect(),
            Qt.AspectRatioMode.KeepAspectRatio
        )

        # автоимя
        self.lineName.setText(f"R_{width:.2f}x{height:.2f}")

    def generate_dxf(self):
        import ezdxf
        from ezdxf.math import Matrix44

        width = self.spinWidth.value()
        height = self.spinHeight.value()
        corner_radius = self.spinCornerRadius.value()

        # Создаем новый DXF
        doc = ezdxf.new(dxfversion="R2010")
        doc.header["$INSUNITS"] = 4  # миллиметры
        msp = doc.modelspace()

        # ------------------------------
        #   ПРЯМОУГОЛЬНИК / СКРУГЛЕНИЯ
        # ------------------------------
        if corner_radius > 0:
            r = corner_radius

            # Нижняя линия
            msp.add_line((r, 0), (width - r, 0))

            # Нижняя правая дуга (270–360°)
            msp.add_arc(
                center=(width - r, r),
                radius=r,
                start_angle=270,
                end_angle=360
            )

            # Правая вертикаль
            msp.add_line((width, r), (width, height - r))

            # Верхняя правая дуга (0–90°)
            msp.add_arc(
                center=(width - r, height - r),
                radius=r,
                start_angle=0,
                end_angle=90
            )

            # Верхняя линия
            msp.add_line((width - r, height), (r, height))

            # Верхняя левая дуга (90–180°)
            msp.add_arc(
                center=(r, height - r),
                radius=r,
                start_angle=90,
                end_angle=180
            )

            # Левая вертикаль
            msp.add_line((0, height - r), (0, r))

            # Нижняя левая дуга (180–270°)
            msp.add_arc(
                center=(r, r),
                radius=r,
                start_angle=180,
                end_angle=270
            )

        else:
            # Обычный прямоугольник
            pts = [(0, 0), (width, 0), (width, height), (0, height), (0, 0)]
            msp.add_lwpolyline(pts, close=True)

        # ------------------------------
        #       ОТВЕРСТИЯ
        # ------------------------------
        for idx in range(self.arraysLayout.count()):
            widget = self.arraysLayout.itemAt(idx).widget()
            if widget is None:
                continue

            (offset_left, offset_bottom, hole_diameter,
             count_vert, gap_vert, count_horz, gap_horz) = widget.get_values()

            r = hole_diameter / 2

            for i in range(count_vert):
                for j in range(count_horz):
                    cx = offset_left + j * gap_horz
                    cy = offset_bottom + i * gap_vert
                    msp.add_circle((cx, cy), r)

        # ------------------------------
        #     ЗЕРКАЛО ПО ГОРИЗОНТАЛИ
        # ------------------------------
        mirror = Matrix44([
             1, 0, 0, 0,         # X без изменений
             0,-1, 0, height,    # Y → -Y + height
             0, 0, 1, 0,
             0, 0, 0, 1
        ])

        for entity in list(msp):
            try:
                entity.transform(mirror)
            except ezdxf.lldxf.const.DXFError:
                pass

        # ------------------------------
        #    СОХРАНЕНИЕ ФАЙЛА
        # ------------------------------
        designation = self.lineDesignation.text().strip()
        name = self.lineName.text().strip() or f"R_{width:.2f}x{height:.2f}"

        if designation:
            default_filename = f"{designation}_{name}.dxf"
        else:
            default_filename = f"{name}.dxf"

        last_path = self.settings.value("lastSavePath", os.path.expanduser("~"))
        initial_path = os.path.join(last_path, default_filename)

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить DXF", initial_path, "DXF файлы (*.dxf)"
        )

        if not file_path:
            return

        if not file_path.lower().endswith(".dxf"):
            file_path += ".dxf"

        try:
            # === СОХРАНЕНИЕ DXF ===
            doc.saveas(file_path)
            self.settings.setValue("lastSavePath", os.path.dirname(file_path))
        
            # База имени файла без расширения
            file_base, _ = os.path.splitext(file_path)
        
            # === СОХРАНЕНИЕ PNG ===
            if self.exportPng.isChecked():
                try:
                    png_path = self.save_preview_image(file_base)      # создаёт PNG
                except Exception as e:
                    QMessageBox.warning(self, "PNG ошибка", f"Не удалось сохранить PNG:\n{str(e)}")
        
            # === ОКНО УСПЕХА ===
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Успех")
            msg_box.setText(f"Файл успешно сохранён:\n{file_path}")
            open_btn = msg_box.addButton("Открыть папку", QMessageBox.ButtonRole.ActionRole)
            msg_box.addButton("Закрыть", QMessageBox.ButtonRole.RejectRole)
            msg_box.exec()
        
            if msg_box.clickedButton() == open_btn:
                QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(file_path)))
        
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Ошибка при сохранении файла:\n{str(e)}")

    

    def check_update(self):
        """ Проверяет новую версию на GitHub и предлагает обновление """
        try:
            url = "https://api.github.com/repos/Jkl88/DXF-Rectangle-Creator/releases/latest"
            response = requests.get(url, timeout=5)
            data = response.json()
    
            latest = data["tag_name"].lstrip("v")
            release_url = data["html_url"]
    
            # ищем первый .exe в релизе
            assets = data.get("assets", [])
            exe_url = None
            for a in assets:
                if a["name"].lower().endswith(".exe"):
                    exe_url = a["browser_download_url"]
                    break
    
            if exe_url is None:
                QMessageBox.warning(self, "Ошибка", "В релизе нет exe-файла.")
                return
    
            if latest == CURRENT_VERSION:
                QMessageBox.information(self, "Обновление", "У вас последняя версия.")
                return
    
            # --- найдено обновление ---
            reply = QMessageBox.question(
                self,
                "Доступно обновление",
                f"Доступна новая версия: {latest}\n"
                f"Текущая версия: {CURRENT_VERSION}\n\n"
                f"Обновить сейчас?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
    
            if reply == QMessageBox.StandardButton.Yes:
                self.perform_update(exe_url)
    
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось проверить обновление:\n{e}")
    
    
    def perform_update(self, download_url):
        """ Скачивает exe, заменяет текущий и запускает новый """
        try:
            # путь к текущему exe
            current_path = sys.executable
    
            # путь к временному файлу для загрузки
            tmp_dir = tempfile.gettempdir()
            new_exe = os.path.join(tmp_dir, "update_new.exe")
    
            # скачиваем новый файл
            r = requests.get(download_url, stream=True)
            total = int(r.headers.get("content-length", 0))
    
            with open(new_exe, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
    
            # создаём батник, который заменит EXE после выхода программы
            updater_path = os.path.join(tmp_dir, "update.bat")
    
            with open(updater_path, "w", encoding="utf-8") as bat:
                bat.write(f"""
    @echo off
    timeout /t 2 >nul
    copy /y "{new_exe}" "{current_path}"
    start "" "{current_path}"
    del "{new_exe}"
    del "%~f0"
                """)
    
            # запускаем апдейтер
            os.startfile(updater_path)
    
            # закрываем программу
            QApplication.instance().quit()
    
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось обновить:\n{e}")


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.resize(720, 700)
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()
