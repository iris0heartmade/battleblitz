@echo off
chcp 65001 >nul
title BattleBlitz Stop
setlocal enabledelayedexpansion

REM ============================================================
REM  BattleBlitz Server - shutdown script
REM  Usage: double-click stop.bat to kill the running server
REM ============================================================

echo.
echo ============================================================
echo   BattleBlitz Server - Stop
echo ============================================================
echo.

set KILLED=0

REM Method 1: kill by window title
echo [1/2] Looking for window titled "BattleBlitz Server"...
tasklist /FI "WINDOWTITLE eq BattleBlitz Server*" /NH 2>nul | findstr /R ".\+" >nul
if !ERRORLEVEL! EQU 0 (
    taskkill /F /FI "WINDOWTITLE eq BattleBlitz Server*" >nul 2>&1
    echo       OK: window found and terminated.
    set KILLED=1
) else (
    echo       No matching window.
)

REM Method 2: kill whatever is listening on port 8000
echo [2/2] Looking for process listening on port 8000...
set FOUND_PORT=0
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo       Killing PID %%a ...
    taskkill /F /PID %%a >nul 2>&1
    if !ERRORLEVEL! EQU 0 (
        set KILLED=1
        set FOUND_PORT=1
    )
)
if "!FOUND_PORT!"=="0" echo       No process listening on 8000.

echo.
if "!KILLED!"=="1" (
    echo Server stopped.
) else (
    echo [INFO] No running BattleBlitz server found.
)
echo.
pause