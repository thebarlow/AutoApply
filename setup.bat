@echo off
setlocal enabledelayedexpansion

echo [setup] Checking for Python 3.10+...

set PYTHON_OK=0
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do (
    for /f "tokens=1,2 delims=." %%a in ("%%v") do (
        if %%a GEQ 3 if %%b GEQ 10 set PYTHON_OK=1
    )
)

if "%PYTHON_OK%"=="0" (
    echo [setup] Python 3.10+ not found. Installing via winget...
    winget install --id Python.Python.3.13 --silent --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo [setup] ERROR: winget install failed.
        echo         Install Python 3.10+ manually from https://www.python.org/downloads/
        echo         then re-run this script.
        pause
        exit /b 1
    )
    echo [setup] Python installed. Refreshing PATH...
    call refreshenv 2>nul
    set PYTHON_OK=0
    for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do (
        for /f "tokens=1,2 delims=." %%a in ("%%v") do (
            if %%a GEQ 3 if %%b GEQ 10 set PYTHON_OK=1
        )
    )
    if "!PYTHON_OK!"=="0" (
        echo [setup] Python was installed but is not on PATH yet.
        echo         Please close this window, open a new terminal, and re-run setup.bat.
        pause
        exit /b 1
    )
)

echo [setup] Python OK. Running setup.py...
python setup.py
if errorlevel 1 (
    echo [setup] setup.py failed. Fix the errors above and re-run setup.bat.
    pause
    exit /b 1
)

echo [setup] Setup complete. Removing setup.bat...
(goto) 2>nul & del "%~f0"
