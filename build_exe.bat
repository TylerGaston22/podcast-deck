@echo off
rem Builds the app like GitHub's release build (.github/workflows/release.yml): dist\PodcastDeck\ with
rem PodcastDeck.exe, and dist\PodcastDeck-Setup.exe too if Inno Setup 6 is installed.
cd /d "%~dp0"
py -m pip install -r requirements.txt pyinstaller
py -m PyInstaller --noconfirm --onedir --noconsole --name PodcastDeck --hidden-import build_scenes deck.py
for %%f in (config.example.py NOTES.md player.html bg_player.html bg_frame.html bg_control.html) do copy /y %%f dist\PodcastDeck\ >nul
set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" "%ISCC%" installer\PodcastDeck.iss
echo.
echo Done: %~dp0dist\PodcastDeck\PodcastDeck.exe
if exist dist\PodcastDeck-Setup.exe echo Installer: %~dp0dist\PodcastDeck-Setup.exe
pause
