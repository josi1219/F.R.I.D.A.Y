@echo off
title F.R.I.D.A.Y. — Setup
color 0B
cls

echo.
echo  ███████╗██████╗ ██╗██████╗  █████╗ ██╗   ██╗
echo  ██╔════╝██╔══██╗██║██╔══██╗██╔══██╗╚██╗ ██╔╝
echo  █████╗  ██████╔╝██║██║  ██║███████║ ╚████╔╝
echo  ██╔══╝  ██╔══██╗██║██║  ██║██╔══██║  ╚██╔╝
echo  ██║     ██║  ██║██║██████╔╝██║  ██║   ██║
echo  ╚═╝     ╚═╝  ╚═╝╚═╝╚═════╝ ╚═╝  ╚═╝   ╚═╝
echo.
echo  Female Replacement Intelligent Digital Assistant Youth
echo  Setup Script
echo  ═══════════════════════════════════════════════════════
echo.

:: ── Check Python ──────────────────────────────────────────
echo [STEP 1/4] Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Python is not installed or not in your PATH.
    echo.
    echo  Please do the following:
    echo    1. Go to  https://www.python.org/downloads/
    echo    2. Download the latest Python 3 installer
    echo    3. Run the installer
    echo    4. IMPORTANT: Check "Add Python to PATH" before installing
    echo    5. Re-run this setup.bat
    echo.
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('python --version') do set PYVER=%%i
echo  [OK] %PYVER% found
echo.

:: ── Create virtual environment ────────────────────────────
echo [STEP 2/4] Creating virtual environment...
if exist "venv" (
    echo  [INFO] Virtual environment already exists, skipping.
) else (
    python -m venv venv
    if %errorlevel% neq 0 (
        echo  [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo  [OK] Virtual environment created.
)
echo.

:: ── Activate venv ─────────────────────────────────────────
call venv\Scripts\activate.bat

:: ── Upgrade pip ───────────────────────────────────────────
echo [STEP 3/4] Upgrading pip...
python -m pip install --upgrade pip -q
echo  [OK] pip upgraded
echo.

:: ── Install packages ──────────────────────────────────────
echo [STEP 4/4] Installing packages (this may take a few minutes)...
echo  Installing: flask, edge-tts, requests, psutil, python-dotenv, google-generativeai
echo.

pip install flask edge-tts requests psutil python-dotenv google-generativeai

if %errorlevel% neq 0 (
    echo.
    echo  [WARNING] Some packages had install issues.
    echo  Friday will still run — check the output above for details.
)

echo.
echo  Configuring environment...
if not exist ".env" (
    copy .env.example .env
    echo  [OK] Created .env from template. Add your GEMINI_API_KEY to enable Gemini AI.
) else (
    echo  [INFO] .env already exists — skipping.
)

echo.
echo ═══════════════════════════════════════════════════════
echo  SETUP COMPLETE!
echo.
echo  To launch Friday, double-click:  run_friday.bat
echo ═══════════════════════════════════════════════════════
echo.
pause
