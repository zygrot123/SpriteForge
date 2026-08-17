@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.13 -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
".venv\Scripts\python.exe" -m pip install pyinstaller
".venv\Scripts\python.exe" tools\make_icon.py
if not exist "tools\7zr.exe" (
  echo 7zr.exe missing
  exit /b 1
)
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean SpriteForge.spec
copy /Y "dist_readme.txt" "dist\SpriteForge\READ ME - extract the WHOLE zip.txt" >nul
copy /Y "Start SpriteForge.bat" "dist\SpriteForge\Start SpriteForge.bat" >nul
echo.
echo Built: dist\SpriteForge\SpriteForge.exe
echo Copy the whole dist\SpriteForge folder to another PC.
