from __future__ import annotations

import signal
import sys
import urllib.request
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from tray_app.panel import TrayPanel
from tray_app.ws_client import WsClient


def _make_icon(_app: QApplication) -> QIcon:
    icon_path = Path(__file__).parent.parent / "assets" / "icon.png"
    return QIcon(str(icon_path))


def _make_heartbeat(app: QApplication) -> QTimer:
    """Exit the tray app when the FastAPI server is unreachable for 2 consecutive checks."""
    _misses: list[int] = [0]

    def _check() -> None:
        try:
            urllib.request.urlopen("http://localhost:8080/api/session-cost", timeout=1)
            _misses[0] = 0
        except Exception:
            _misses[0] += 1
            if _misses[0] >= 2:
                app.quit()

    t = QTimer()
    t.timeout.connect(_check)
    return t


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    panel = TrayPanel()

    ws = WsClient()
    ws.job_received.connect(panel.add_job)

    tray = QSystemTrayIcon(_make_icon(app), app)
    tray.setToolTip("Auto Apply — Connected")

    menu = QMenu()
    quit_action = menu.addAction("Quit")
    quit_action.triggered.connect(app.quit)
    tray.setContextMenu(menu)
    tray.show()

    ws.connection_state_changed.connect(tray.setToolTip)

    signal.signal(signal.SIGINT, lambda *_: app.quit())
    # Allow Python to process signals every 500ms while Qt event loop runs
    timer = QTimer()
    timer.start(500)
    timer.timeout.connect(lambda: None)

    ws.start()

    heartbeat = _make_heartbeat(app)
    # Delay 5 seconds to allow server startup before monitoring begins
    QTimer.singleShot(5000, lambda: heartbeat.start(2000))

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
