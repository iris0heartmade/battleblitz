@echo off
REM play.bat — 一键启动 BattleBlitz 客户端(双击即可,不会弹编辑器)
REM 用 console 版 Godot 跑 main scene

set GODOT_EXE=D:\Python\godot\Godot_v4.7-stable_win64_console.exe
set PROJECT_DIR=%~dp0..

cd /d "%PROJECT_DIR%\.."
"%GODOT_EXE%" --rendering-driver opengl3 --path "%PROJECT_DIR%" res://scenes/main.tscn
pause