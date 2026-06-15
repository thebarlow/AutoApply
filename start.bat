@echo off
cd /d "%~dp0"

if exist "%~dp0.dev" goto skip_setup
if exist "%~dp0setup.bat" (
    echo [start] First-time setup detected. Running setup.bat...
    call "%~dp0setup.bat"
    if errorlevel 1 (
        echo [start] Setup failed. Aborting.
        pause
        exit /b 1
    )
)
:skip_setup

call .venv\Scripts\activate.bat

start "Auto Apply Server" cmd /k "uvicorn web.main:app --host 0.0.0.0 --port 8080 --reload"

REM Forward Stripe webhook events to the local server. The first line of this
REM window prints the signing secret (whsec_...) — copy it into STRIPE_WEBHOOK_SECRET.
start "Stripe Webhooks" cmd /k "stripe listen --forward-to localhost:8080/api/payments/webhook"

REM Optional: `start.bat dev` also runs the Vite dev server (hot-reload frontend).
if /i "%~1"=="dev" (
    start "React Dev Server" cmd /k "cd react-dashboard && npm run dev"
)

python -m tray_app.main
