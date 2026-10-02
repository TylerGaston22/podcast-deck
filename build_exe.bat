@echo off
rem Builds a single-file PodcastDeck.exe in dist\ so others don't need Python.
cd /d "%~dp0"
py -m pip install pyinstaller
py -m PyInstaller --onefile --noconsole --name PodcastDeck --add-data "config.example.py;." deck.py
echo.
echo Done: %~dp0dist\PodcastDeck.exe  (keep a config.py next to it)
pause
