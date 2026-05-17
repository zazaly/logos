@echo off
REM Quick launcher — run after setup_and_run.bat has been run once.

set PYTHON=
where py >nul 2>&1 && set PYTHON=py
if "%PYTHON%"=="" (
    where python >nul 2>&1 && set PYTHON=python
)
if "%PYTHON%"=="" (
    where python3 >nul 2>&1 && set PYTHON=python3
)
if "%PYTHON%"=="" (
    echo Python not found. Please run setup_and_run.bat first.
    pause
    exit /b 1
)

%PYTHON% main.py
