@echo off
rem Double-click once: puts a PRINTYZ Clicker Studio icon on the Desktop and in the Start menu
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\create_shortcut.ps1"
pause
