@echo off
setlocal enabledelayedexpansion
title SOVEREIGN OS — Setup
color 0E

echo.
echo  ╔══════════════════════════════════════╗
echo  ║        SOVEREIGN OS  SETUP           ║
echo  ╚══════════════════════════════════════╝
echo.

:: ── Check Python ─────────────────────────────────────────────────────────────
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.11+ from https://python.org
    pause & exit /b 1
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER%

:: ── Check Node.js ────────────────────────────────────────────────────────────
node --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Install from https://nodejs.org
    pause & exit /b 1
)
for /f %%v in ('node --version') do set NODEVER=%%v
echo [OK] Node.js %NODEVER%

:: ── Check winget ─────────────────────────────────────────────────────────────
winget --version >nul 2>&1
if errorlevel 1 (
    echo [WARN] winget not available. You may need to install Tesseract and CMake manually.
) else (
    echo [OK] winget available

    :: Install Tesseract OCR
    echo.
    echo [1/5] Installing Tesseract OCR...
    winget install UB-Mannheim.TesseractOCR --silent --accept-package-agreements --accept-source-agreements >nul 2>&1
    echo [OK] Tesseract installed

    :: Install CMake
    echo [2/5] Installing CMake...
    winget install Kitware.CMake --silent --accept-package-agreements --accept-source-agreements >nul 2>&1
    echo [OK] CMake installed

    :: Install VS Build Tools (needed for dlib)
    echo [3/5] Installing Visual Studio Build Tools (C++ compiler for dlib)...
    echo       This may take a few minutes...
    winget install Microsoft.VisualStudio.2022.BuildTools --silent --accept-package-agreements --accept-source-agreements --override "--quiet --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended" >nul 2>&1
    echo [OK] Build tools installed
)

:: ── pip install ──────────────────────────────────────────────────────────────
echo.
echo [4/5] Installing Python packages...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt 2>&1 | findstr /C:"Successfully" /C:"already" /C:"ERROR"

:: ── Build dlib with MSVC ─────────────────────────────────────────────────────
echo.
echo [5/5] Building dlib (face recognition)...
set VCVARS="C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if exist %VCVARS% (
    call %VCVARS% >nul 2>&1
    python -m pip install dlib 2>&1 | findstr /C:"Successfully" /C:"already" /C:"ERROR"
    python -m pip install face-recognition 2>&1 | findstr /C:"Successfully" /C:"already" /C:"ERROR"
    echo [OK] dlib + face-recognition installed
) else (
    echo [WARN] MSVC not found — skipping dlib. Face recognition will be disabled.
    echo        Re-run setup after installing Visual Studio Build Tools.
)

:: ── Download Kokoro TTS model files ──────────────────────────────────────────
echo.
echo Downloading Kokoro TTS models (approx 340 MB)...
if not exist "data" mkdir data
python -c "
import requests, os, sys
base = 'https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/'
files = {'kokoro-v1.0.onnx': 310, 'voices-v1.0.bin': 27}
for fname, mb in files.items():
    dest = os.path.join('data', fname)
    if os.path.exists(dest):
        print(f'  [OK] {fname} already exists')
        continue
    print(f'  Downloading {fname} (~{mb} MB)...')
    r = requests.get(base + fname, stream=True)
    with open(dest, 'wb') as f:
        for chunk in r.iter_content(8192):
            f.write(chunk)
    print(f'  [OK] {fname} saved')
"

:: ── Install Playwright browser ───────────────────────────────────────────────
echo.
echo Installing Playwright browser (Chromium)...
python -m playwright install chromium >nul 2>&1
echo [OK] Chromium installed

:: ── Install UI dependencies ───────────────────────────────────────────────────
echo.
echo Installing UI dependencies...
cd ui
call npm install >nul 2>&1
cd ..
echo [OK] Node modules installed

:: ── Create .env if missing ────────────────────────────────────────────────────
echo.
if not exist ".env" (
    copy .env.example .env >nul
    echo [ACTION NEEDED] .env file created from template.
    echo.
    echo  Open .env and fill in your API keys:
    echo   - GROQ_API_KEY    ^> https://console.groq.com  (free)
    echo   - SOVEREIGN_USER_NAME ^> your name
    echo.
    notepad .env
) else (
    echo [OK] .env already exists
)

:: ── Done ─────────────────────────────────────────────────────────────────────
echo.
echo  ╔══════════════════════════════════════╗
echo  ║         SETUP COMPLETE!              ║
echo  ║  Run start.bat to launch SOVEREIGN   ║
echo  ╚══════════════════════════════════════╝
echo.
pause
