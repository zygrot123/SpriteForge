@echo off
cd /d "%~dp0"
if exist "dist\SpriteForge\SpriteForge.exe" cd /d "%~dp0dist\SpriteForge"
if not exist "_internal" (
  echo Missing _internal folder.
  echo Extract the FULL SpriteForge-Windows.zip first.
  echo Do not run the exe from inside the zip.
  pause
  exit /b 1
)
start "" "%cd%\SpriteForge.exe"
