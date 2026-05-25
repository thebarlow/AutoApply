from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QMimeData, QSize, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QDrag, QPixmap
from PyQt6.QtWidgets import QLabel


class DragHandle(QLabel):
    """A label that initiates a native OS file drag when clicked and dragged."""

    drag_started = pyqtSignal()

    def __init__(
        self,
        file_path: str,
        label: str,
        icon_path: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._file_path = file_path
        self._exists = Path(file_path).exists()
        self._drag_start_pos = None

        if icon_path and Path(icon_path).exists():
            pixmap = QPixmap(icon_path).scaled(
                28, 28,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.setPixmap(pixmap)
            self.setFixedSize(QSize(28, 28))
        else:
            self.setText(label)

        if self._exists:
            self.setToolTip(file_path)
            if not icon_path:
                self.setStyleSheet("color: #0d6efd; text-decoration: underline;")
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            if icon_path:
                self.setOpacity(1.0)
        else:
            self.setEnabled(False)
            if not icon_path:
                self.setStyleSheet("color: #aaa;")
            else:
                self.setGraphicsEffect(self._make_disabled_effect())
            self.setToolTip(f"File not found: {file_path}")

    def _make_disabled_effect(self):
        from PyQt6.QtWidgets import QGraphicsOpacityEffect
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(0.35)
        return effect

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._exists:
            return
        if self._drag_start_pos is None:
            return
        if (event.pos() - self._drag_start_pos).manhattanLength() < 10:
            return
        self.drag_started.emit()
        drag = QDrag(self)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(self._file_path)])
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)
        self._drag_start_pos = None
