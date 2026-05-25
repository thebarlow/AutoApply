from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt, pyqtSlot
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

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
        self._saved_size = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(4)

        # Drag-to-move header with minimize button
        header = QWidget()
        header.setStyleSheet("background: #e9ecef; border-radius: 6px;")
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(8, 4, 4, 4)
        title_label = QLabel("Auto Apply")
        title_label.setStyleSheet("font-size: 11px; font-weight: bold; color: #495057; background: transparent;")
        header_row.addWidget(title_label)
        header_row.addStretch()
        minimize_btn = QPushButton("−")
        minimize_btn.setFixedSize(22, 22)
        minimize_btn.setStyleSheet(
            "QPushButton { background: #adb5bd; color: white; border-radius: 11px; font-size: 14px; font-weight: bold; border: none; }"
            "QPushButton:hover { background: #6c757d; }"
        )
        minimize_btn.clicked.connect(self.showMinimized)
        header_row.addWidget(minimize_btn)
        outer.addWidget(header)
        self._header = header  # used for drag detection

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

    def changeEvent(self, event):
        if event.type() == QEvent.Type.WindowStateChange:
            if self.windowState() & Qt.WindowState.WindowMinimized:
                self._saved_size = self.size()
            elif self._saved_size is not None:
                self.resize(self._saved_size)
                self._saved_size = None
        super().changeEvent(event)

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
        job_id = payload.get("jobId")
        if not job_id:
            return
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
        card.dismissed.connect(self._remove_card)
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
