@echo off
REM ── Spear launcher ───────────────────────────────────────────────────────────
REM Activates the project venv and runs the app.
REM Exit code 100 = update yt-dlp, then restart automatically.
REM
REM Venv resolution order:
REM   1. SPEAR_VENV environment variable (set this on machines with a global venv)
REM   2. .venv\ folder in the repo root  (standard, works on a fresh clone)

cd /d "%~dp0"

REM ── Locate venv ──────────────────────────────────────────────────────────────
if defined SPEAR_VENV (
    if not exist "%SPEAR_VENV%\Scripts\activate.bat" (
        echo ERROR: SPEAR_VENV is set but "%SPEAR_VENV%\Scripts\activate.bat" was not found.
        pause
        exit /b 1
    )
    call "%SPEAR_VENV%\Scripts\activate.bat"
) else if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
) else (
    echo ERROR: No virtual environment found.
    echo.
    echo Either:
    echo   a^) Create a local venv:   python -m venv .venv
    echo              then install:   .venv\Scripts\pip install -r requirements.txt
    echo   b^) Set the SPEAR_VENV environment variable to your existing venv path.
    pause
    exit /b 1
)

REM ── Run loop ─────────────────────────────────────────────────────────────────
:run_script
python main.py
set "EC=%ERRORLEVEL%"

if %EC% EQU 100 (
    echo.
    echo Updating yt-dlp...
    pip install -U yt-dlp
    if %ERRORLEVEL% NEQ 0 (
        echo.
        echo WARNING: yt-dlp update failed. Check your internet connection.
        pause
        exit /b 1
    )
    echo.
    echo yt-dlp updated. Restarting Spear...
    echo.
    goto run_script
)

if %EC% NEQ 0 (
    echo.
    echo Spear exited with error code %EC%.
    pause
)
exit /b %EC%
