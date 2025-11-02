@echo off
title Lilith 🖤
echo 🌙 Waking up Lilith's mind...

REM Check if LM Studio server is running
curl -s http://localhost:1234/v1/models >nul 2>&1
if %errorlevel% neq 0 (
    echo Starting LM Studio...
    start "" "%LOCALAPPDATA%\Programs\LM Studio\LM Studio.exe" --enable-server
    timeout /t 10 /nobreak >nul
) else (
    echo LM Studio already running.
)

REM Activate virtual environment
if exist venv\Scripts\activate (
    call venv\Scripts\activate
) else (
    echo Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate
    pip install -r requirements.txt
)

REM Launch Lilith terminal version
echo 🖤 Lilith is awakening...
python lilith.py
pause
