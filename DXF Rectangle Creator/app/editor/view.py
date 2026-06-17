from __future__ import annotations

import math
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QApplication, QGraphicsView, QLineEdit, QSpinBox, QDoubleSpinBox

from app.models.base import ContourKind
from app.ui.widgets import FocusDoubleSpinBox, FocusSpinBox


class EditorView(QGraphicsView):
    def __init__(self, scene, on_user_view=None, on_clear_selection=None, on_nudge=None,
                 on_space=None, on_measure_mode_changed=None, on_shutter_mode_changed=None,
                 on_aux_line_mode_changed=None, on_rectangle_mode_changed=None,
                 on_origin_placement_done=None, parent=None):
        super().__init__(scene, parent)
        self._on_user_view = on_user_view
        self._on_clear_selection = on_clear_selection
        self._on_nudge = on_nudge
        self._on_space = on_space
        self._on_measure_mode_changed = on_measure_mode_changed
        self._on_shutter_mode_changed = on_shutter_mode_changed
        self._on_aux_line_mode_changed = on_aux_line_mode_changed
        self._on_rectangle_mode_changed = on_rectangle_mode_changed
        self._on_origin_placement_done = on_origin_placement_done
        self._scene_ctrl = None
        self._panning = False
        self._rmb_pan = False
        self._pan_start = QPointF()
        self._left_press_pos = None
        self._shutter_drawing = False
        self._rectangle_drawing = False
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

    def set_scene_controller(self, ctrl) -> None:
        self._scene_ctrl = ctrl

    def _notify(self):
        if self._on_user_view:
            self._on_user_view()

    def _input_focused(self) -> bool:
        fw = QApplication.focusWidget()
        if fw is None:
            return False
        return isinstance(fw, (QLineEdit, QSpinBox, QDoubleSpinBox, FocusSpinBox, FocusDoubleSpinBox))

    def _view_scale(self) -> float:
        return self.transform().m11() or 1.0

    def _map_to_scene(self, pos) -> tuple[float, float]:
        pt = self.mapToScene(pos.toPoint())
        return pt.x(), pt.y()

    def wheelEvent(self, event):
        if event.angleDelta().y() == 0:
            return
        factor = 1.12 if event.angleDelta().y() > 0 else 1 / 1.12
        mouse = event.position()
        mouse_pt = mouse.toPoint()
        # mapToScene uses the view matrix only — not ItemIgnoresTransformations overlays.
        scene_anchor = self.mapToScene(mouse_pt)
        old_anchor = self.transformationAnchor()
        old_resize = self.resizeAnchor()
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.scale(factor, factor)
        view_pos = self.mapFromScene(scene_anchor)
        self.horizontalScrollBar().setValue(
            self.horizontalScrollBar().value() + int(view_pos.x() - mouse.x()),
        )
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value() + int(view_pos.y() - mouse.y()),
        )
        self.setTransformationAnchor(old_anchor)
        self.setResizeAnchor(old_resize)
        self._notify()
        event.accept()

    def mousePressEvent(self, event):
        ctrl = self._scene_ctrl
        if (
            ctrl is not None and ctrl.origin_placement_mode
            and event.button() == Qt.MouseButton.LeftButton
        ):
            x, y = self._map_to_scene(event.position())
            sx, sy, _ = ctrl.snap_origin_point(x, y, self._view_scale())
            done, px, py = ctrl.click_origin_point(sx, sy)
            if done and self._on_origin_placement_done:
                self._on_origin_placement_done(px, py)
            event.accept()
            return
        if (
            ctrl is not None and ctrl.aux_line_mode
            and event.button() == Qt.MouseButton.LeftButton
        ):
            x, y = self._map_to_scene(event.position())
            done = ctrl.aux_line_press(x, y, self._view_scale())
            if done and self._on_aux_line_mode_changed:
                self._on_aux_line_mode_changed(False)
            event.accept()
            return
        if (
            ctrl is not None and ctrl.rectangle_mode
            and event.button() == Qt.MouseButton.LeftButton
        ):
            x, y = self._map_to_scene(event.position())
            ctrl.rectangle_press(x, y)
            self._rectangle_drawing = True
            event.accept()
            return
        if (
            ctrl is not None and ctrl.shutter_mode
            and event.button() == Qt.MouseButton.LeftButton
        ):
            x, y = self._map_to_scene(event.position())
            ctrl.shutter_press(x, y)
            self._shutter_drawing = True
            event.accept()
            return
        if (
            ctrl is not None and ctrl.measure_mode
            and event.button() == Qt.MouseButton.LeftButton
        ):
            x, y = self._map_to_scene(event.position())
            sx, sy, snapped = ctrl.snap_measure_point(x, y, self._view_scale())
            done = ctrl.click_measure_point(x, y, sx, sy, snapped)
            if done and self._on_measure_mode_changed:
                self._on_measure_mode_changed(False)
            event.accept()
            return
        item = self.itemAt(event.position().toPoint())
        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            self._panning = True
            self._rmb_pan = event.button() == Qt.MouseButton.RightButton
            self._left_press_pos = None
            self._pan_start = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and item is None:
            ctrl = self._scene_ctrl
            if not (ctrl and (
                ctrl.measure_mode or ctrl.shutter_mode or ctrl.aux_line_mode
                or ctrl.rectangle_mode or ctrl.origin_placement_mode
            )):
                self._left_press_pos = event.position()
                self._pan_start = event.position()
                self._panning = False
            event.accept()
            return
        self._left_press_pos = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning:
            delta = event.position() - self._pan_start
            self._pan_start = event.position()
            hbar = self.horizontalScrollBar()
            vbar = self.verticalScrollBar()
            hbar.setValue(hbar.value() - int(delta.x()))
            vbar.setValue(vbar.value() - int(delta.y()))
            self._notify()
            event.accept()
            return
        ctrl = self._scene_ctrl
        if ctrl is not None and ctrl.origin_placement_mode:
            x, y = self._map_to_scene(event.position())
            sx, sy, _ = ctrl.snap_origin_point(x, y, self._view_scale())
            ctrl.update_origin_placement_cursor(sx, sy)
            event.accept()
            return
        if ctrl is not None and ctrl.aux_line_mode and self._aux_line_has_src(ctrl):
            x, y = self._map_to_scene(event.position())
            ctrl.aux_line_move(x, y)
            event.accept()
            return
        if ctrl is not None and ctrl.rectangle_mode and self._rectangle_drawing:
            x, y = self._map_to_scene(event.position())
            ctrl.rectangle_move(x, y)
            event.accept()
            return
        if ctrl is not None and ctrl.shutter_mode and self._shutter_drawing:
            x, y = self._map_to_scene(event.position())
            ctrl.shutter_move(x, y)
            event.accept()
            return
        if ctrl is not None and ctrl.measure_mode:
            x, y = self._map_to_scene(event.position())
            sx, sy, _ = ctrl.snap_measure_point(x, y, self._view_scale())
            ctrl.update_measure_cursor(sx, sy)
            event.accept()
            return
        if self._left_press_pos is not None and not self._panning:
            delta = event.position() - self._left_press_pos
            if math.hypot(delta.x(), delta.y()) > 4:
                self._panning = True
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mouseMoveEvent(event)

    def _aux_line_has_src(self, ctrl) -> bool:
        return ctrl._aux_src is not None

    def mouseReleaseEvent(self, event):
        ctrl = self._scene_ctrl
        if (
            self._rectangle_drawing
            and event.button() == Qt.MouseButton.LeftButton
            and ctrl is not None and ctrl.rectangle_mode
        ):
            x, y = self._map_to_scene(event.position())
            done = ctrl.rectangle_release(x, y)
            self._rectangle_drawing = False
            if done and self._on_rectangle_mode_changed:
                self._on_rectangle_mode_changed(False)
            event.accept()
            return
        if (
            self._shutter_drawing
            and event.button() == Qt.MouseButton.LeftButton
            and ctrl is not None and ctrl.shutter_mode
        ):
            x, y = self._map_to_scene(event.position())
            done = ctrl.shutter_release(x, y)
            self._shutter_drawing = False
            if done and self._on_shutter_mode_changed:
                self._on_shutter_mode_changed(False)
            event.accept()
            return
        if self._left_press_pos is not None and event.button() == Qt.MouseButton.LeftButton:
            if not self._panning and self._on_clear_selection:
                ctrl = self._scene_ctrl
                if not (ctrl and (
                ctrl.measure_mode or ctrl.shutter_mode or ctrl.aux_line_mode
                or ctrl.rectangle_mode or ctrl.origin_placement_mode
            )):
                    self._on_clear_selection()
            self._left_press_pos = None
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        if self._panning:
            self._panning = False
            self._rmb_pan = False
            self._left_press_pos = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape and self._scene_ctrl:
            if self._scene_ctrl.aux_line_mode:
                self._scene_ctrl.cancel_aux_line()
                if self._on_aux_line_mode_changed:
                    self._on_aux_line_mode_changed(False)
                event.accept()
                return
            if self._scene_ctrl.rectangle_mode:
                self._scene_ctrl.cancel_rectangle()
                self._rectangle_drawing = False
                if self._on_rectangle_mode_changed:
                    self._on_rectangle_mode_changed(False)
                event.accept()
                return
            if self._scene_ctrl.shutter_mode:
                self._scene_ctrl.cancel_shutter()
                self._shutter_drawing = False
                if self._on_shutter_mode_changed:
                    self._on_shutter_mode_changed(False)
                event.accept()
                return
            if self._scene_ctrl.origin_placement_mode:
                self._scene_ctrl.cancel_origin_placement()
                if (
                    self._scene_ctrl.document.contour_kind == ContourKind.DXF
                    and not self._scene_ctrl.document.dxf_contour.origin_set
                    and self._on_origin_placement_done
                ):
                    self._on_origin_placement_done(0.0, 0.0)
                else:
                    self.setCursor(Qt.CursorShape.ArrowCursor)
                event.accept()
                return
            if self._scene_ctrl.measure_mode:
                self._scene_ctrl.cancel_measure()
                if self._on_measure_mode_changed:
                    self._on_measure_mode_changed(False)
                event.accept()
                return
        if self._input_focused():
            super().keyPressEvent(event)
            return
        key = event.key()
        if key == Qt.Key.Key_Space and self._on_space:
            if self._on_space():
                event.accept()
                return
        step = 0.1 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0
        dx = dy = 0.0
        if key == Qt.Key.Key_Left:
            dx = -step
        elif key == Qt.Key.Key_Right:
            dx = step
        elif key == Qt.Key.Key_Up:
            dy = -step
        elif key == Qt.Key.Key_Down:
            dy = step
        else:
            super().keyPressEvent(event)
            return
        if self._on_nudge and self._on_nudge(dx, dy):
            event.accept()
            return
        super().keyPressEvent(event)

    def fit_document(self, rect):
        if not rect.isValid() or rect.width() <= 0 or rect.height() <= 0:
            return
        self.resetTransform()
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def reset_view(self):
        self.resetTransform()
