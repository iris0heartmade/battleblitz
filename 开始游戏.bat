@echo off
chcp 65001 >nul
powershell -NoProfile -File "%~dp0tools\run_godot.ps1" -FormalGame
if errorlevel 1 pause
