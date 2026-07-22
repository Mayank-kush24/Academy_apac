@echo off
title External Company Mapper
cd /d "%~dp0"

if "%~1"=="" (
    echo Usage:
    echo   run_external_company_mapper.bat input.csv
    echo   run_external_company_mapper.bat input.csv output.csv
    echo.
    echo Or single row:
    echo   python scripts\external_company_mapper.py --email user@example.com --company "TCS"
    pause
    exit /b 1
)

if "%~2"=="" (
    python scripts\external_company_mapper.py "%~1"
) else (
    python scripts\external_company_mapper.py "%~1" -o "%~2"
)

if errorlevel 1 pause
