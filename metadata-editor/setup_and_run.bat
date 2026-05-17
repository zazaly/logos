@echo off
setlocal enabledelayedexpansion

echo ============================================
echo  Comic Bulk Metadata Editor - Setup
echo ============================================
echo.

REM Find Python - try py launcher first (handles multiple versions), then python
set PYTHON=
where py >nul 2>&1 && set PYTHON=py
if "!PYTHON!"=="" (
    where python >nul 2>&1 && set PYTHON=python
)
if "!PYTHON!"=="" (
    where python3 >nul 2>&1 && set PYTHON=python3
)
if "!PYTHON!"=="" (
    echo ERROR: Python not found. Install from https://python.org
    pause
    exit /b 1
)

echo Using Python: !PYTHON!
!PYTHON! --version
echo.

REM Install dependencies
echo Installing dependencies...
!PYTHON! -m pip install --upgrade pip -q
!PYTHON! -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERROR: Failed to install dependencies.
    echo Try running as Administrator or check your internet connection.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Setup complete! Launching application...
echo ============================================
echo.

!PYTHON! main.py
if errorlevel 1 (
    echo.
    echo Application exited with an error.
    pause
)
