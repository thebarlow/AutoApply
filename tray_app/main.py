from __future__ import annotations

import signal
import sys
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from tray_app.panel import TrayPanel
from tray_app.ws_client import WsClient


def _make_icon(_app: QApplication) -> QIcon:
    icon_path = Path(__file__).parent.parent / "assets" / "icon.png"
    return QIcon(str(icon_path))


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
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
