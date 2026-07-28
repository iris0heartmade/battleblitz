@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title BattleBlitz Launcher

cd /d "%~dp0"

set PORT=8000
set GAME_DIR=%~dp0game
set GODOT_EXE=D:\Python\godot\Godot_v4.7-stable_win64_console.exe
set GODOT_PROJECT=%~dp0godot-client

echo ============================================================
echo   BattleBlitz Launcher
echo ============================================================
echo.

if not exist "%GAME_DIR%\venv\Scripts\activate.bat" (
    echo [ERROR] venv not found at game\venv\Scripts\activate.bat
    pause
    exit /b 1
)

echo [1/3] Checking port %PORT% ...
set PORT_PIDS=
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
    set PORT_PIDS=!PORT_PIDS! %%a
)

if not "!PORT_PIDS!"=="" (
    echo       Port %PORT% is in use by PID:!PORT_PIDS!
    set /p KILL=      Kill the old process? [y/n]:
    if /i "!KILL!"=="y" (
        for %%p in (!PORT_PIDS!) do (
            taskkill /F /PID %%p >nul 2>&1
            echo       Killed PID %%p
        )
        ping -n 2 127.0.0.1 >nul
    ) else (
        echo       Aborted. Free port %PORT% and try again.
        pause
        exit /b 1
    )
) else (
    echo       Port %PORT% is free.
)

echo.
echo [2/3] Starting backend server ...
start "BattleBlitz Server" cmd /k "cd /d "%GAME_DIR%" && call venv\Scripts\activate.bat && python -m uvicorn app.main:app --host 0.0.0.0 --port %PORT%"

echo       Waiting for server to come up ...
powershell -NoProfile -Command "for($i=0;$i -lt 40;$i++){try{$c=New-Object Net.Sockets.TcpClient;$c.Connect('127.0.0.1',%PORT%);$c.Close();exit 0}catch{Start-Sleep -Milliseconds 750}};exit 1"
if errorlevel 1 (
    echo       [WARN] Server not detected yet; opening client anyway.
) else (
    echo       Server is up on http://localhost:%PORT%/
)

echo.
echo [3/3] Launching Godot client (debug) ...
if not exist "%GODOT_EXE%" (
    echo       [ERROR] Godot not found at %GODOT_EXE%
    pause
    exit /b 1
)
start "BattleBlitz Godot" "%GODOT_EXE%" --path "%GODOT_PROJECT%" --debug

echo.
echo Done. Server window and Godot client launched.
echo Close the server window to stop the backend.
ping -n 4 127.0.0.1 >nul
endlocal
