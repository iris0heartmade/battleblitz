@echo off
chcp 65001 >nul
title BattleBlitz Server

REM ============================================================
REM  BattleBlitz Server - startup script
REM  Usage: double-click start.bat
REM         close this window to stop the server
REM ============================================================

cd /d "%~dp0"

echo.
echo ============================================================
echo   BattleBlitz Server
echo ============================================================
echo.

REM Check virtualenv
if not exist "venv\Scripts\activate.bat" (
    echo [ERROR] venv not found at venv\Scripts\activate.bat
    echo.
    echo First-time setup:
    echo   python -m venv venv
    echo   venv\Scripts\activate.bat
    echo   pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

REM Activate virtualenv
call venv\Scripts\activate.bat

REM Check if port 8000 is already taken
set PORT=8000
netstat -ano | findstr ":%PORT%" | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo [WARN] Port %PORT% is already in use.
    echo        An older server may still be running.
    echo.
    echo To stop it, run stop.bat, or end the process manually.
    echo.
    pause
    exit /b 1
)

echo Starting on http://localhost:%PORT%/
echo.
echo Tip: press Ctrl+C to stop, or close this window.
echo      You can also run stop.bat from another terminal.
echo ============================================================
echo.

REM Run uvicorn (foreground; closing window ends the process)
python -m uvicorn app.main:app --host 0.0.0.0 --port %PORT%

pause