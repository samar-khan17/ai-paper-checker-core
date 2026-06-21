@echo off
REM ============================================================
REM  Smart Paper Checker - one-click launcher
REM  Uses the bundled virtual environment (Python 3.14).
REM ============================================================
cd /d "%~dp0"

REM Check Python 3.14 is installed before proceeding
py -3.14 --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.14 was not found on this system.
    echo Please install Python 3.14 from https://www.python.org/downloads/
    echo and make sure "py launcher" is enabled during installation.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [setup] Creating virtual environment...
    py -3.14 -m venv .venv
    .venv\Scripts\python.exe -m pip install --upgrade pip
    .venv\Scripts\python.exe -m pip install -r requirements.txt
)

echo Starting Smart Paper Checker...
.venv\Scripts\python.exe main.py
pause

REM Build verified and packaged by Hussam