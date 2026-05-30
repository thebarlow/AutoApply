# tray_app/ Context

PyQt6 system tray application. Runs as the foreground process when `start.bat` launches the pipeline — the FastAPI server starts in a separate console window first, then `python -m tray_app.main` runs in the foreground.

## Entry Point

`tray_app/main.py` → `main()` — constructs the `QApplication`, tray icon, context menu, `TrayPanel`, and `WsClient`, then enters the Qt event loop.

## Files

```
tray_app/
├── main.py          # Entry point; builds QApplication, tray icon, heartbeat timer
├── ws_client.py     # Background WebSocket client; connects to ws://localhost:8080/ws/tray
├── panel.py         # TrayPanel: frameless floating window that stacks JobCards
├── job_card.py      # JobCard: one card per pending job with drag handles + confirm/dismiss
├── drag_handle.py   # DragHandle: QLabel subclass; initiates native OS file drag on mouse move
└── assets/
    ├── resume_icon_64.png       # Icon shown on resume drag handle
    └── coverletter_icon_64.png  # Icon shown on cover letter drag handle
```

## Routing Rules

| Task | File |
|---|---|
| App startup, tray icon, heartbeat, signal wiring | `main.py` |
| WebSocket connection to FastAPI, reconnect backoff | `ws_client.py` → `WsClient` |
| Floating panel; add/remove job cards | `panel.py` → `TrayPanel` |
| Per-job card UI; drag handles, confirm/dismiss buttons | `job_card.py` → `JobCard` |
| Native file drag from a PDF path | `drag_handle.py` → `DragHandle` |

## Pipeline Integration

- `start.bat` launches the FastAPI server (`uvicorn`, port 8080) in a new console window, then starts the tray app in the foreground. The tray app exits when the Qt window closes.
- `WsClient` connects to `ws://localhost:8080/ws/tray`. The server pushes a JSON payload when a job's resume and cover letter are ready; `WsClient` emits `job_received`, which `TrayPanel.add_job` receives.
- `JobCard` presents draggable PDF handles (resume + cover letter) and two buttons:
  - **✓ (confirm)** — POSTs to `POST /api/jobs/{job_id}/confirm-applied`; removes the card on success.
  - **✕ (dismiss)** — removes the card locally with no API call.
- The heartbeat timer (`main.py`) polls `GET /api/session-cost` every 2 seconds (after a 5-second startup delay). Two consecutive failures cause `app.quit()`, so the tray app shuts itself down if the server dies.
- The tray icon tooltip reflects WebSocket state ("Connecting…", "Connected", "Reconnecting…") via `WsClient.connection_state_changed`.

## Known Issues / Future Improvements

- No known bugs at time of writing.
- Dismiss (✕) does not notify the server — dismissed jobs stay in `state=generated` indefinitely. A `/api/jobs/{id}/dismiss` endpoint and matching API call could address this.
- `AUTO_APPLY_API_BASE` env var is read in `job_card.py` but not in `ws_client.py` or `main.py`; those are hardcoded to `localhost:8080`. All three should use the same env var.
- No per-card timeout or expiry — cards accumulate if the user never acts on them.
