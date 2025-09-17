@echo off
cls

REM Simple English-only version of RSS crawler runner
REM This version uses only basic English commands to avoid encoding issues

REM Step 1: Check if Python is installed
echo ==================================
echo RSS Crawler - English Version
echo ==================================
echo 

echo 1. Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed!
    echo Please install Python from https://www.python.org/downloads/
    echo IMPORTANT: Check "Add Python to PATH" during installation
    echo 
    pause
    exit /b 1
) else (
    echo Python is installed. Version:
    python --version
)

echo.

echo 2. Installing required packages (feedparser, requests)...
python -m pip install feedparser requests

if %errorlevel% neq 0 (
    echo WARNING: Failed to install packages.
    echo Try running this file as Administrator.
    echo 
    pause
)

echo.

echo 3. Running RSS crawler...
echo Please wait, this may take several minutes...

python rss_crawler.py

if %errorlevel% neq 0 (
    echo 
    echo ERROR: Crawler failed to run!
    echo Possible reasons: network issues or program errors
) else (
    echo 
    echo SUCCESS: Crawler completed!
    echo Links have been saved to current folder
)

echo 
echo Press any key to close this window...
pause >nul