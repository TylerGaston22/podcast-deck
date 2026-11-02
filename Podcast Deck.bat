@echo off
rem Launches the deck with no console window. Make a desktop shortcut to this file (Install.bat does).
rem First it gets the newest version from GitHub (only when this folder was cloned with git). If that
rem doesn't work (offline, or files edited here), the deck just opens as it is.
rem Everything is in one ( ) block: Windows reads the block before running it, so the update can
rem replace this file safely. If the new version needs new add-ons, they're installed before the deck starts.
setlocal EnableDelayedExpansion
cd /d "%~dp0"
(
  if exist ".git" where git >nul 2>nul && (
    set "GIT_TERMINAL_PROMPT=0"
    set "OLD="
    for /f %%h in ('git rev-parse HEAD 2^>nul') do set "OLD=%%h"
    git -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=10 pull --ff-only -q >nul 2>nul && (
      git diff --quiet !OLD! HEAD -- requirements.txt >nul 2>nul || (
        where py >nul 2>nul && (
          py -m pip install --disable-pip-version-check -q -r requirements.txt >nul 2>nul
        ) || (
          python -m pip install --disable-pip-version-check -q -r requirements.txt >nul 2>nul
        )
      )
    )
  )
  where pyw >nul 2>nul && (
    start "" pyw "%~dp0deck.py"
  ) || (
    start "" pythonw "%~dp0deck.py"
  )
  exit /b
)
