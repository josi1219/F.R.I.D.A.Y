@echo off
setlocal EnableDelayedExpansion

echo ============================================================
echo   F.R.I.D.A.Y. -- Windows Autostart Setup
echo   Registers watchdog.py to run automatically on login
echo ============================================================
echo.

REM ── Resolve paths ────────────────────────────────────────────────────────────
set "SCRIPT_DIR=%~dp0"
REM Remove trailing backslash
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

set "VENV_PYTHON=%SCRIPT_DIR%\venv\Scripts\pythonw.exe"
set "WATCHDOG=%SCRIPT_DIR%\watchdog.py"
set "TASK_NAME=FRIDAY Watchdog"

REM Use venv pythonw if it exists; fall back to system pythonw
if exist "%VENV_PYTHON%" (
    set "PYTHON=%VENV_PYTHON%"
    echo Python  : %VENV_PYTHON% (venv^)
) else (
    set "PYTHON=pythonw.exe"
    echo Python  : pythonw.exe (system PATH^)
)

echo Script  : %WATCHDOG%
echo Task    : %TASK_NAME%
echo.

if not exist "%WATCHDOG%" (
    echo [ERROR] watchdog.py not found at: %WATCHDOG%
    echo         Run this script from the Friday project folder.
    pause
    exit /b 1
)

REM ── Register with Task Scheduler ─────────────────────────────────────────────
schtasks /create ^
    /tn "%TASK_NAME%" ^
    /tr "\"%PYTHON%\" \"%WATCHDOG%\"" ^
    /sc onlogon ^
    /rl limited ^
    /f

if %ERRORLEVEL% EQU 0 (
    echo.
    echo [OK] Task Scheduler entry created.
    echo      FRIDAY will start automatically on next login.
    echo.
    echo Useful commands:
    echo   Start now  :  schtasks /run /tn "%TASK_NAME%"
    echo   Remove task:  schtasks /delete /tn "%TASK_NAME%" /f
) else (
    echo.
    echo [WARN] schtasks failed ^(error %ERRORLEVEL%^).
    echo        Trying Startup folder fallback...
    echo.
    set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
    set "SHORTCUT=!STARTUP!\FRIDAY.bat"
    (
        echo @echo off
        echo start "" "%PYTHON%" "%WATCHDOG%"
    ) > "!SHORTCUT!"
    if exist "!SHORTCUT!" (
        echo [OK] Startup shortcut created:
        echo      !SHORTCUT!
    ) else (
        echo [ERROR] Could not create startup shortcut either.
        echo         Try running this script as Administrator.
    )
)

echo.
pause
endlocal
