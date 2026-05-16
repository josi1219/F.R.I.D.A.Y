@echo off
title F.R.I.D.A.Y. — AI Assistant
color 0B
cls

echo.
echo  ▄████████    ▄████████  ▄█  ████████▄     ▄████████ ▄██   ▄
echo  ███    ███   ███    ███ ███  ███   ▀███   ███    ███ ███   ██▄
echo  ███    █▀    ███    ███ ███▌ ███    ███   ███    ███ ███▄▄▄███
echo  ███         ▄███▄▄▄▄██▀ ███▌ ███    ███   ███    ███ ▀▀▀▀▀▀███
echo  ███        ▀▀███▀▀▀▀▀   ███▌ ███    ███ ▀███████████ ▄██   ███
echo  ███    █▄  ▀███████████ ███  ███    ███   ███    ███ ███   ███
echo  ███    ███   ███    ███ ███  ███   ▄███   ███    ███ ███   ███
echo  ████████▀    ███    ███ █▀   ████████▀    ███    █▀   ▀█████▀
echo               ███    ███
echo.
echo  Female Replacement Intelligent Digital Assistant Youth
echo  ═══════════════════════════════════════════════════════
echo.

:: ── Check venv ────────────────────────────────────────────
if not exist "venv\Scripts\activate.bat" (
    echo  Virtual environment not found.
    echo  Running setup first...
    echo.
    call setup.bat
    if %errorlevel% neq 0 (
        echo  Setup failed. Please run setup.bat manually.
        pause
        exit /b 1
    )
)

:: ── Activate ──────────────────────────────────────────────
call venv\Scripts\activate.bat

echo  Systems coming online...
echo  Friday will open in your browser in a moment.
echo.
echo  ► Browser: http://127.0.0.1:5000
echo  ► To shut down: press Ctrl+C in this window
echo.

:: ── Open browser after 4 seconds ─────────────────────────
:: (gives Flask time to start)
start /b cmd /c "timeout /t 4 /nobreak >nul 2>&1 && start http://127.0.0.2:5000"

:: ── Launch Flask ──────────────────────────────────────────
python app.py

pause
