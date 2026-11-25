@echo off
rem Builds the customer edition installer (customer\output\PRINTYZ-Clicker-Setup-*.exe)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0customer\build_customer.ps1"
pause
