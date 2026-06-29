"""Startup splash screen (animated fade-out like DXF SkyView)."""

from __future__ import annotations

from PyQt6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QVariantAnimation,
    Qt,
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QGraphicsOpacityEffect, QSplashScreen

from app.resources import logo_path


def show_splash(app) -> QSplashScreen | None:
    path = logo_path()
    if not path:
        return None
    pixmap = QPixmap(path)
    if pixmap.isNull():
        return None
    scaled = pixmap.scaled(
        360,
        160,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    splash = QSplashScreen(scaled)
    splash._base_pixmap = scaled  # type: ignore[attr-defined]
    splash.show()
    app.processEvents()
    splash._splash_center = splash.geometry().center()  # type: ignore[attr-defined]
    return splash


def finish_splash_animated(splash: QSplashScreen, window) -> None:
    duration_ms = 700
    grow = 1.5
    base = getattr(splash, "_base_pixmap", None)
    if base is None or base.isNull():
        splash.finish(window)
        return

    center = getattr(splash, "_splash_center", splash.geometry().center())

    opacity_effect = QGraphicsOpacityEffect(splash)
    splash.setGraphicsEffect(opacity_effect)

    scale_anim = QVariantAnimation(splash)
    scale_anim.setDuration(duration_ms)
    scale_anim.setStartValue(1.0)
    scale_anim.setEndValue(grow)
    scale_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _on_scale_changed(value) -> None:
        scale = float(value)
        scaled = base.scaled(
            int(base.width() * scale),
            int(base.height() * scale),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        splash.setPixmap(scaled)
        splash.move(
            int(center.x() - scaled.width() / 2),
            int(center.y() - scaled.height() / 2),
        )

    scale_anim.valueChanged.connect(_on_scale_changed)

    fade_anim = QPropertyAnimation(opacity_effect, b"opacity", splash)
    fade_anim.setDuration(duration_ms)
    fade_anim.setStartValue(1.0)
    fade_anim.setEndValue(0.0)
    fade_anim.setEasingCurve(QEasingCurve.Type.InCubic)

    group = QParallelAnimationGroup(splash)
    group.addAnimation(scale_anim)
    group.addAnimation(fade_anim)

    def _finalize() -> None:
        splash.finish(window)
        splash.deleteLater()

    group.finished.connect(_finalize)
    group.start()
