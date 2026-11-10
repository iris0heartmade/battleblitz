@echo off
chcp 65001 >nul
powershell -NoProfile -File "%~dp0tools\run_height_demo.ps1"
if errorlevel 1 pause
