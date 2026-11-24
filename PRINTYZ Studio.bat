@echo off
rem PRINTYZ Clicker Studio - double-click to update and launch
setlocal
cd /d "%~dp0"
set "VENV=%LOCALAPPDATA%\PRINTYZ\ClickerV2\.venv"
echo Updating from GitHub...
git pull --ff-only
if not exist "%VENV%\Scripts\python.exe" (
  echo Creating Python 3.13 environment...
  py -3.13 -m venv "%VENV%" || (echo Python 3.13 was not found. & pause & exit /b 1)
)
echo Checking libraries...
"%VENV%\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt || (pause & exit /b 1)
"%VENV%\Scripts\python.exe" -m pip install -q --disable-pip-version-check -e . || (pause & exit /b 1)
echo Starting PRINTYZ Clicker Studio...
start "" "%VENV%\Scripts\pythonw.exe" -m printyz_clicker.ui
