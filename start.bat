@echo off
cd /d "%~dp0"

if exist "%~dp0setup.bat" (
    echo [start] First-time setup detected. Running setup.bat...
    call "%~dp0setup.bat"
    if errorlevel 1 (
        echo [start] Setup failed. Aborting.
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate.bat

start "Auto Apply Server" cmd /k "uvicorn web.main:app --host 0.0.0.0 --port 8080 --reload"
python -m tray_app.main
