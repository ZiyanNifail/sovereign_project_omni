@echo off
echo Starting SOVEREIGN OS...

:: Kill any existing instances
powershell -Command "Get-NetTCPConnection -LocalPort 8765 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
timeout /t 1 /nobreak >nul

:: Start Python backend (hidden window)
start "" /min python "%~dp0main.py"

:: Wait for backend to boot
timeout /t 3 /nobreak >nul

:: Start UI dev server and open browser
start "" /min cmd /c "cd /d %~dp0ui && npm run dev"
timeout /t 2 /nobreak >nul

:: Open browser
start "" "http://localhost:5173"

echo SOVEREIGN OS is running.
echo Backend: ws://localhost:8765
echo UI: http://localhost:5173
echo.
echo To stop: close this window or press Ctrl+C
pause
