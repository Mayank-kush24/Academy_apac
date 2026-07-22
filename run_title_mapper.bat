@echo off
title Job Title Mapper
cd /d "%~dp0"
echo Starting Job Title Mapper...
python scripts\title_mapper_app.py
if errorlevel 1 (
    echo.
    echo Something went wrong. Make sure Python is installed and run:
    echo   pip install rapidfuzz pandas
    echo   python scripts/build_title_index.py
    pause
)
