from __future__ import annotations

import httpx
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from tray_app.drag_handle import DragHandle

_API_BASE = "http://localhost:8080"


class JobCard(QFrame):
    """Card representing one job in the tray panel."""

    confirmed = pyqtSignal(str)  # emits job_id on checkmark click

    def __init__(self, job_id: str, role: str, company: str,
                 resume_path: str, cover_path: str, parent=None):
        super().__init__(parent)
        self._job_id = job_id
        self._setup_ui(role, company, resume_path, cover_path)
        self._set_style(active=False)

    def _setup_ui(self, role: str, company: str, resume_path: str, cover_path: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        header = QLabel(f"<b>{role}</b><br><small>{company}</small>")
        layout.addWidget(header)

        handles_row = QHBoxLayout()
        self._resume_handle = DragHandle(resume_path, "📄 Resume")
        self._cover_handle = DragHandle(cover_path, "📝 Cover Letter")
        self._resume_handle.drag_started.connect(self._on_drag_started)
        self._cover_handle.drag_started.connect(self._on_drag_started)
        handles_row.addWidget(self._resume_handle)
        handles_row.addWidget(self._cover_handle)
        handles_row.addStretch()
        layout.addLayout(handles_row)

        footer = QHBoxLayout()
        self._error_label = QLabel("")
        self._error_label.setStyleSheet("color: red; font-size: 10px;")
        self._error_label.hide()
        footer.addWidget(self._error_label)
        footer.addStretch()

        self._check_btn = QPushButton("✓")
        self._check_btn.setFixedSize(28, 28)
        self._check_btn.setStyleSheet(
            "QPushButton { background: #198754; color: white; border-radius: 14px; font-weight: bold; }"
            "QPushButton:hover { background: #157347; }"
        )
        self._check_btn.clicked.connect(self._on_checkmark)
        footer.addWidget(self._check_btn)
        layout.addLayout(footer)

    def _set_style(self, active: bool):
        border_color = "#0d6efd" if active else "#dee2e6"
        self.setStyleSheet(
            f"JobCard {{ border: 2px solid {border_color}; border-radius: 6px;"
            f" background: #ffffff; }}"
        )

    def _on_drag_started(self):
        self._set_style(active=True)
        parent = self.parent()
        if parent and hasattr(parent, "set_active_card"):
            parent.set_active_card(self)

    def deactivate(self):
        self._set_style(active=False)

    def _on_checkmark(self):
        try:
            resp = httpx.post(
                f"{_API_BASE}/api/jobs/{self._job_id}/confirm-applied",
                timeout=5,
            )
            if resp.status_code == 200:
                self.confirmed.emit(self._job_id)
            else:
                self._show_error(f"Server error {resp.status_code} — retry?")
        except Exception:
            self._show_error("Failed to archive — retry?")

    def _show_error(self, msg: str):
        self._error_label.setText(msg)
        self._error_label.show()
