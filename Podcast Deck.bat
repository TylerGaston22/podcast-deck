@echo off
rem Launches the deck with no console window. Make a desktop shortcut to this file.
cd /d "%~dp0"
if not exist config.py copy config.example.py config.py >nul
start "" pythonw "%~dp0deck.py"
