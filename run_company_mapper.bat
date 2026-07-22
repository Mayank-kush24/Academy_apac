@echo off
title Company Name Mapper
cd /d "%~dp0"
echo Starting Company Name Mapper...
python scripts\company_mapper_app.py
if errorlevel 1 (
    echo.
    echo Something went wrong. Make sure Python is installed and run:
    echo   pip install rapidfuzz pandas openpyxl
    echo   python scripts/build_company_index.py
    pause
)
