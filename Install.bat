@echo off
rem One-click setup: installs Python if it's missing, the deck's add-ons, and a desktop shortcut,
rem then opens the deck. Safe to run again.
cd /d "%~dp0"
set "PY=py"
where py >nul 2>nul
if errorlevel 1 (
  echo Installing Python. This takes a minute or two...
  winget install -e --id Python.Python.3.13 --scope user --accept-package-agreements --accept-source-agreements
  set "PY=%LOCALAPPDATA%\Programs\Python\Launcher\py.exe"
)
"%PY%" --version >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python couldn't be installed automatically.
  echo Install it from https://www.python.org/downloads ^(tick "Add python.exe to PATH"^),
  echo then double-click Install.bat again.
  pause
  exit /b 1
)
echo Installing the deck's add-ons...
"%PY%" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
  echo Couldn't install the add-ons. Check your internet connection and try again.
  pause
  exit /b 1
)
echo Making the desktop shortcut...
powershell -NoProfile -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Podcast Deck.lnk'); $s.TargetPath = '%~dp0Podcast Deck.bat'; $s.WorkingDirectory = '%~dp0'; $s.WindowStyle = 7; $s.Description = 'Podcast Deck'; $s.Save()"
echo Done. Opening the deck...
start "" "%~dp0Podcast Deck.bat"
