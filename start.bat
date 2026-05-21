@echo off
cd /d "%~dp0"
call .venv\Scripts\activate.bat

start "Auto Apply Server" cmd /k "uvicorn web.main:app --host 0.0.0.0 --port 8080 --reload"
python -m tray_app.main
