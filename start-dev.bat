@echo off
echo ═══════════════════════════════════════════════════════
echo   PrivateGPT v2.0 — Development Mode
echo   Backend: http://localhost:8765
echo   Frontend: Electron (auto-reload)
echo ═══════════════════════════════════════════════════════
echo.

echo [1/2] Starting FastAPI backend (hot-reload)...
start "PrivateGPT Backend" /min "%~dp0venv\Scripts\python.exe" -m uvicorn backend.server:app --port 8765 --host 127.0.0.1 --reload

echo Waiting for backend startup...
timeout /t 8 /nobreak > nul

echo [2/2] Starting Electron...
cd /d "%~dp0electron"
npx electron . --dev
