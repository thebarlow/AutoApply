from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from tray_app.job_card import JobCard


class TrayPanel(QWidget):
    """Frameless always-on-top floating panel that stacks job cards."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setMinimumWidth(280)
        self.setMaximumWidth(360)

        self._drag_pos = None
        self._cards: dict[str, JobCard] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._inner = QWidget()
        self._layout = QVBoxLayout(self._inner)
        self._layout.setSpacing(6)
        self._layout.addStretch()
        self._scroll.setWidget(self._inner)
        outer.addWidget(self._scroll)

        self.setStyleSheet("background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 8px;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_pos is not None and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        super().mouseReleaseEvent(event)

    @pyqtSlot(dict)
    def add_job(self, payload: dict):
        job_id = payload["jobId"]
        if job_id in self._cards:
            return
        card = JobCard(
            job_id=job_id,
            role=payload.get("role", ""),
            company=payload.get("company", ""),
            resume_path=payload.get("resume_path", ""),
            cover_path=payload.get("cover_path", ""),
            parent=self._inner,
        )
        card.confirmed.connect(self._remove_card)
        self._cards[job_id] = card
        self._layout.insertWidget(self._layout.count() - 1, card)
        self.adjustSize()
        self.show()

    def set_active_card(self, active_card: JobCard):
        for card in self._cards.values():
            if card is not active_card:
                card.deactivate()

    @pyqtSlot(str)
    def _remove_card(self, job_id: str):
        card = self._cards.pop(job_id, None)
        if card:
            self._layout.removeWidget(card)
            card.deleteLater()
        self.adjustSize()
        if not self._cards:
            self.hide()
