from __future__ import annotations

import httpx
import os
import threading
from pathlib import Path
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
)

from tray_app.drag_handle import DragHandle

_API_BASE = os.getenv("AUTO_APPLY_API_BASE", "http://localhost:8080")
_ASSETS = Path(__file__).parent / "assets"


class JobCard(QFrame):
    """Card representing one job in the tray panel."""

    confirmed = pyqtSignal(str)   # emits job_id when applied
    dismissed = pyqtSignal(str)   # emits job_id when X is clicked
    _confirm_result = pyqtSignal(bool, str)

    def __init__(self, job_id: str, role: str, company: str,
                 resume_path: str, cover_path: str, parent=None):
        super().__init__(parent)
        self._job_id = job_id
        self._setup_ui(role, company, resume_path, cover_path)
        self._confirm_result.connect(self._on_confirm_result)
        self._set_style(active=False)

    def _setup_ui(self, role: str, company: str, resume_path: str, cover_path: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # --- Label row ---
        label_row = QHBoxLayout()
        label_row.setSpacing(6)

        title_label = QLabel(f"<b>{role}</b>")
        title_label.setStyleSheet("color: #212529; background: transparent;")

        sep_label = QLabel("|")
        sep_label.setStyleSheet("color: #adb5bd; background: transparent;")

        company_label = QLabel(company)
        company_label.setStyleSheet("color: #495057; background: transparent;")

        label_row.addWidget(title_label)
        label_row.addWidget(sep_label)
        label_row.addWidget(company_label)
        label_row.addStretch()
        layout.addLayout(label_row)

        # --- Content row ---
        content_row = QHBoxLayout()
        content_row.setSpacing(6)

        self._resume_handle = DragHandle(
            resume_path,
            "📄 Resume",
            icon_path=str(_ASSETS / "resume_icon_64.png"),
        )
        self._cover_handle = DragHandle(
            cover_path,
            "📝 Cover Letter",
            icon_path=str(_ASSETS / "coverletter_icon_64.png"),
        )
        self._resume_handle.drag_started.connect(self._on_drag_started)
        self._cover_handle.drag_started.connect(self._on_drag_started)

        content_row.addWidget(self._resume_handle)
        content_row.addWidget(self._cover_handle)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet("color: red; font-size: 10px;")
        self._error_label.hide()
        content_row.addWidget(self._error_label)

        content_row.addStretch()

        self._check_btn = QPushButton("✓")
        self._check_btn.setFixedSize(28, 28)
        self._check_btn.setStyleSheet(
            "QPushButton { background: #198754; color: white; border-radius: 14px;"
            " font-weight: bold; border: none; }"
            "QPushButton:hover { background: #157347; }"
        )
        self._check_btn.clicked.connect(self._on_checkmark)

        self._dismiss_btn = QPushButton("✕")
        self._dismiss_btn.setFixedSize(28, 28)
        self._dismiss_btn.setStyleSheet(
            "QPushButton { background: #dc3545; color: white; border-radius: 14px;"
            " font-weight: bold; border: none; }"
            "QPushButton:hover { background: #b02a37; }"
        )
        self._dismiss_btn.clicked.connect(lambda: self.dismissed.emit(self._job_id))

        content_row.addWidget(self._check_btn)
        content_row.addWidget(self._dismiss_btn)

        layout.addLayout(content_row)

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
        self._check_btn.setEnabled(False)
        threading.Thread(target=self._do_confirm, daemon=True).start()

    def _do_confirm(self):
        try:
            resp = httpx.post(
                f"{_API_BASE}/api/jobs/{self._job_id}/confirm-applied",
                timeout=5,
            )
            if resp.status_code == 200:
                self._confirm_result.emit(True, "")
            else:
                self._confirm_result.emit(False, f"Server error {resp.status_code} — retry?")
        except httpx.TimeoutException:
            self._confirm_result.emit(False, "Request timed out — retry?")
        except httpx.RequestError as exc:
            print(f"[tray] Request failed: {exc}")
            self._confirm_result.emit(False, "Failed to connect — retry?")
        except Exception as exc:
            print(f"[tray] Unexpected error: {exc}")
            self._confirm_result.emit(False, "Failed to archive — retry?")

    def _on_confirm_result(self, success: bool, error_msg: str):
        self._check_btn.setEnabled(True)
        if success:
            self.confirmed.emit(self._job_id)
        else:
            self._show_error(error_msg)

    def _show_error(self, msg: str):
        self._error_label.setText(msg)
        self._error_label.show()
