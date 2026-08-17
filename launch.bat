@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo First run: creating Python environment...
  py -3.13 -m venv .venv
  if errorlevel 1 py -3 -m venv .venv
  if errorlevel 1 (
    echo Could not create a virtualenv. Install Python 3.13 from python.org
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

echo Starting SpriteForge...
".venv\Scripts\python.exe" app.py
if errorlevel 1 pause
