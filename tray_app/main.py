from __future__ import annotations

import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from tray_app.panel import TrayPanel
from tray_app.ws_client import WsClient


def _make_icon(app: QApplication) -> QIcon:
    from PyQt6.QtWidgets import QStyle
    return app.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogStart)


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

    ws.start()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
