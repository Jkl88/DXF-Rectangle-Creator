from PyQt6.QtWidgets import QGraphicsView, QWidget


def export_png(
    view: QGraphicsView,
    file_path: str,
    *,
    include_title_block: bool = True,
    editor_widget: QWidget | None = None,
    title_block_widget: QWidget | None = None,
) -> None:
    """Capture the editor exactly as shown on screen (viewport + optional title block)."""
    if include_title_block and editor_widget is not None:
        pixmap = editor_widget.grab()
    else:
        pixmap = view.viewport().grab()
    if pixmap.isNull():
        raise RuntimeError("Не удалось сформировать изображение")
    pixmap.save(file_path)
