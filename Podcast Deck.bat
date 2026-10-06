@echo off
rem Launches the deck with no console window. Make a desktop shortcut to this file (Install.bat does).
cd /d "%~dp0"
where pyw >nul 2>nul
if errorlevel 1 (
  start "" pythonw "%~dp0deck.py"
) else (
  start "" pyw "%~dp0deck.py"
)
