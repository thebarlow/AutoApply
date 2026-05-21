from __future__ import annotations

import asyncio
import json
import threading

import websockets
from PyQt6.QtCore import QObject, pyqtSignal

_WS_URL = "ws://localhost:8080/ws/tray"
_MAX_BACKOFF = 30


class WsClient(QObject):
    """Background thread that maintains a WebSocket connection to FastAPI.

    Emits `job_received` with the parsed payload dict whenever the server
    pushes a job. Emits `connection_state_changed` with a status string
    for tray icon tooltip updates.
    """

    job_received = pyqtSignal(dict)
    connection_state_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def _run(self):
        asyncio.run(self._connect_loop())

    async def _connect_loop(self):
        backoff = 1
        while not self._stop_event.is_set():
            try:
                self.connection_state_changed.emit("Connecting…")
                async with websockets.connect(_WS_URL) as ws:
                    backoff = 1
                    self.connection_state_changed.emit("Connected")
                    async for message in ws:
                        if self._stop_event.is_set():
                            return
                        try:
                            payload = json.loads(message)
                            self.job_received.emit(payload)
                        except json.JSONDecodeError:
                            pass
            except (websockets.exceptions.WebSocketException, OSError, asyncio.TimeoutError) as exc:
                if self._stop_event.is_set():
                    return
                print(f"[tray] WS connection error: {type(exc).__name__}: {exc}")
                self.connection_state_changed.emit(f"Reconnecting… (retry in {backoff}s)")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, _MAX_BACKOFF)
