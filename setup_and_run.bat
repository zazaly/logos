@echo off
setlocal enabledelayedexpansion

echo ============================================
echo  Bulk Rename Utility + Metadata Editor Setup
echo ============================================
echo.

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

echo Installing dependencies...
!PYTHON! -m pip install --upgrade pip -q
!PYTHON! -m pip install -e ".[dev]"
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

!PYTHON! -m studio
if errorlevel 1 (
    echo.
    echo Application exited with an error.
    pause
)
