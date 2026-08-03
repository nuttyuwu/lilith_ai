@echo off
REM ==========================================================================
REM  Lilith launcher for Windows 10 / 11
REM
REM  Fixes over the previous version:
REM    * chcp 65001 so Lilith's hearts and moon render instead of mojibake.
REM    * Runs from the folder this file lives in (%~dp0), so it works from a
REM      desktop shortcut, from Explorer, or from any cwd.
REM    * Falls back to the 'py' launcher when 'python' is not on PATH, which
REM      is the default state after a Microsoft Store install.
REM    * Checks that Python is actually present and reports how to fix it,
REM      instead of failing with "python is not recognized" and vanishing.
REM    * Only pauses on error, so a normal exit does not leave a dead window.
REM    * Passes your arguments through:  lilith.bat edit   /   lilith.bat doctor
REM ==========================================================================

chcp 65001 >nul 2>&1
setlocal
cd /d "%~dp0"
title Lilith

echo Waking up Lilith's mind...
echo.

REM --- Find a Python interpreter ------------------------------------------
REM Order matters. The py launcher is tried FIRST because on Windows 11
REM "where python" usually finds the Microsoft Store App Execution Alias:
REM a 0-byte stub under \WindowsApps\ that opens the Store instead of
REM running Python. Any python.exe on that path is skipped.
REM Ask for 3.12 downwards before falling back to "newest 3.x". llama-cpp-python
REM only publishes wheels for CPython 3.10-3.12, and "py -3" resolves to the
REM NEWEST install -- so on a machine with 3.14 alongside 3.12, a plain "py -3"
REM builds the venv on 3.14 and pip silently starts a 15-minute source build
REM that needs Visual Studio Build Tools.
REM The interpreter is kept as EXE + ARGS rather than one string, because the
REM two branches below produce different shapes: "py" plus "-3.12", versus a
REM bare path that can contain spaces (C:\Program Files\Python312\python.exe).
REM Storing both in one variable meant it could not be quoted, so the
REM fallback path died with "'C:\Program' is not recognized" and reported the
REM misleading "Could not create the virtual environment".
set "PY_EXE="
set "PY_ARGS="
for %%V in (3.12 3.11 3.10 3) do (
    if not defined PY_EXE (
        py -%%V -c "import sys" >nul 2>&1
        if not errorlevel 1 (
            set "PY_EXE=py"
            set "PY_ARGS=-%%V"
        )
    )
)

if not defined PY_EXE (
    for /f "delims=" %%I in ('where python 2^>nul') do (
        if not defined PY_EXE (
            echo %%I | find /i "\WindowsApps\" >nul
            if errorlevel 1 set "PY_EXE=%%I"
        )
    )
)

if not defined PY_EXE (
    where python >nul 2>&1 && (
        echo [ERROR] The only "python" found is the Microsoft Store placeholder.
        echo.
        echo Windows ships a stub that opens the Store rather than running
        echo Python. Install the real thing from python.org, or disable the
        echo stub under: Settings ^> Apps ^> Advanced app settings ^>
        echo App execution aliases ^> turn off "python.exe".
        echo.
        pause
        exit /b 1
    )
)

if not defined PY_EXE (
    echo [ERROR] Python was not found on this system.
    echo.
    echo Install Python 3.10 or newer from https://www.python.org/downloads/
    echo During installation, tick BOTH:
    echo    [x] Add python.exe to PATH
    echo    [x] tcl/tk and IDLE          ^(required for Lilith's portrait^)
    echo.
    pause
    exit /b 1
)

REM --- Virtual environment ------------------------------------------------
if not exist "venv\Scripts\activate.bat" (
    echo First run: creating a virtual environment...
    "%PY_EXE%" %PY_ARGS% -m venv venv
    if errorlevel 1 (
        echo [ERROR] Could not create the virtual environment.
        pause
        exit /b 1
    )
    call "venv\Scripts\activate.bat"
    echo Installing dependencies...
    "venv\Scripts\python.exe" -m pip install --upgrade pip
    if errorlevel 1 (
        echo [ERROR] Could not upgrade pip. See the messages above.
        pause
        exit /b 1
    )
    "venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed. See the messages above.
        pause
        exit /b 1
    )
    "venv\Scripts\python.exe" -c "from pathlib import Path;import hashlib;p=Path('requirements.txt');Path('venv/.requirements-sha256').write_text(hashlib.sha256(p.read_bytes()).hexdigest()+'\n',encoding='ascii')"
    echo.
    echo Setup complete.
    echo.
) else (
    call "venv\Scripts\activate.bat"
    REM Dependencies used to be installed only when the venv was first
    REM created, so pulling a commit that adds a requirement gave an
    REM ImportError at startup instead of an install. Compare a content hash,
    REM because checkout timestamps can move backwards or remain unchanged.
    "venv\Scripts\python.exe" -c "from pathlib import Path;import hashlib,sys;p=Path('requirements.txt');s=Path('venv/.requirements-sha256');h=hashlib.sha256(p.read_bytes()).hexdigest();sys.exit(0 if s.exists() and s.read_text(encoding='ascii').strip()==h else 1)"
    if errorlevel 1 (
        echo requirements.txt changed; updating dependencies...
        "venv\Scripts\python.exe" -m pip install -r requirements.txt
        if errorlevel 1 (
            echo [ERROR] Dependency installation failed. See the messages above.
            pause
            exit /b 1
        )
        "venv\Scripts\python.exe" -c "from pathlib import Path;import hashlib;p=Path('requirements.txt');Path('venv/.requirements-sha256').write_text(hashlib.sha256(p.read_bytes()).hexdigest()+'\n',encoding='ascii')"
    )
)

REM --- Run ----------------------------------------------------------------
echo Lilith is awakening...
echo.
"venv\Scripts\python.exe" lilith.py %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo.
    echo Lilith exited with code %RC%.
    echo Run  lilith.bat doctor  for a setup check.
    pause
)

REM %RC% must be expanded on the SAME line as endlocal. On its own line it is
REM read after endlocal has already discarded the variable, so the command
REM degrades to a bare "exit /b" and the launcher always reports success.
endlocal & exit /b %RC%
