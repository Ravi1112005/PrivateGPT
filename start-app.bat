@echo off
echo ═══════════════════════════════════════════════════
echo   PrivateGPT v2.0 — Electron Desktop App
echo ═══════════════════════════════════════════════════
echo.

:: Check if venv exists
if not exist "%~dp0venv\Scripts\python.exe" (
    echo [ERROR] Python venv not found at venv\
    echo Run: python -m venv venv
    echo Then: venv\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

:: Check if Electron is installed
if not exist "%~dp0electron\node_modules\electron" (
    echo [INFO] Installing Electron...
    cd /d "%~dp0electron"
    npm install
    cd /d "%~dp0"
)

echo [1/2] Starting FastAPI backend...
start /b "" "%~dp0venv\Scripts\python.exe" -m uvicorn backend.server:app --port 8765 --host 127.0.0.1

:: Wait for backend
echo [2/2] Waiting for backend to be ready...
timeout /t 5 /nobreak > nul

echo [OK] Launching Electron app...
cd /d "%~dp0electron"
npx electron .
