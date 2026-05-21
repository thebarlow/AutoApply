from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QMimeData, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QDrag
from PyQt6.QtWidgets import QLabel


class DragHandle(QLabel):
    """A label that initiates a native OS file drag when clicked and dragged."""

    drag_started = pyqtSignal()

    def __init__(self, file_path: str, label: str, parent=None):
        super().__init__(label, parent)
        self._file_path = file_path
        self._exists = Path(file_path).exists()
        self._drag_start_pos = None

        if self._exists:
            self.setToolTip(file_path)
            self.setStyleSheet("color: #0d6efd; text-decoration: underline; cursor: grab;")
        else:
            self.setEnabled(False)
            self.setStyleSheet("color: #aaa;")
            self.setToolTip(f"File not found: {file_path}")

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
