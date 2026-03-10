@echo off
cd /d "%~dp0"
echo Starting Gen AI Academy APAC server...
python run.py
if errorlevel 1 (
    echo.
    echo Server exited with an error. Press any key to close.
    pause >nul
)
