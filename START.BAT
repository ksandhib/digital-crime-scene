@echo off
setlocal EnableDelayedExpansion
title DIGITAL CRIME SCENE AI
cd /d "%~dp0"
set "PORT=8047"
set "URL=http://127.0.0.1:%PORT%"

echo.
echo   ============================================
echo     DIGITAL CRIME SCENE AI
echo     Investigate. Connect. Reason. Solve.
echo   ============================================
echo.

REM ---- 1. Python -------------------------------------------------------
set "PY="
where py >nul 2>&1 && (py -3 -c "import sys" >nul 2>&1 && set "PY=py -3")
if not defined PY (
  where python >nul 2>&1 && (python -c "import sys" >nul 2>&1 && set "PY=python")
)
if not defined PY (
  echo [X] Python 3.9 or newer was not found.
  echo     Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause
  exit /b 1
)
%PY% -c "import sys; sys.exit(0 if sys.version_info>=(3,9) else 1)" >nul 2>&1
if errorlevel 1 (
  echo [X] Python 3.9 or newer is required.
  pause
  exit /b 1
)
echo [OK] Python found: %PY%

REM ---- 2. Virtual environment -----------------------------------------
if not exist ".venv\Scripts\python.exe" (
  echo [..] Creating virtual environment ^(first run only^)...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo [X] Could not create the virtual environment.
    pause
    exit /b 1
  )
)
set "VPY=.venv\Scripts\python.exe"

REM ---- 3. Packages -----------------------------------------------------
"%VPY%" -c "import fastapi, uvicorn" >nul 2>&1
if errorlevel 1 (
  echo [..] Installing packages ^(first run only, needs internet^)...
  "%VPY%" -m pip install --disable-pip-version-check -q -r requirements.txt
  if errorlevel 1 (
    echo [X] Package installation failed. Check your internet connection and run START.BAT again.
    pause
    exit /b 1
  )
)
echo [OK] Packages ready

REM ---- 4. Ollama (optional) -------------------------------------------
set "OLLAMA_UP=0"
curl -s -m 2 http://127.0.0.1:11434/api/tags >nul 2>&1 && set "OLLAMA_UP=1"
if "!OLLAMA_UP!"=="0" (
  where ollama >nul 2>&1
  if not errorlevel 1 (
    echo [..] Ollama is installed but not running - starting it...
    start "" /min ollama serve
    timeout /t 3 /nobreak >nul
    curl -s -m 2 http://127.0.0.1:11434/api/tags >nul 2>&1 && set "OLLAMA_UP=1"
  )
)
if "!OLLAMA_UP!"=="1" (
  echo [OK] Ollama is running - NEXUS will use your local model
) else (
  echo [--] Ollama not available - NEXUS will use deterministic evidence answers ^(fully playable^)
)

REM ---- 5. Already running? --------------------------------------------
netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo [OK] Server already running - opening the game
  start "" "%URL%"
  exit /b 0
)

REM ---- 6. Start server (also serves the frontend) and open the browser ---
echo [..] Starting DIGITAL CRIME SCENE AI at %URL%
echo      Close this window to stop the game.
echo.
set "DCS_OPEN_BROWSER=1"
set "DCS_PORT=%PORT%"
"%VPY%" -m uvicorn backend.main:app --host 127.0.0.1 --port %PORT% --log-level warning
echo.
echo Server stopped.
pause
