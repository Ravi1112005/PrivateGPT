@echo off
setlocal enabledelayedexpansion

set RESOURCES_DIR=%~1
if "%RESOURCES_DIR%"=="" set RESOURCES_DIR=%~dp0

echo [INFO] Setting up PrivateGPT Environment in %RESOURCES_DIR%...
cd /d "%RESOURCES_DIR%"

:: 1. Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10+ and try again.
    exit /b 1
)

:: 2. Setup Virtual Environment
if not exist "venv\Scripts\python.exe" (
    echo [INFO] Creating Python virtual environment...
    python -m venv venv
)

:: 3. Install Python Dependencies
echo [INFO] Installing Python requirements...
"venv\Scripts\pip.exe" install -r requirements.txt --quiet

:: 4. Download Embedding Model
echo [INFO] Pre-downloading Embedding Model for offline use...
"venv\Scripts\python.exe" download_embeddings.py

:: 5. Check for Ollama
ollama --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Downloading Ollama installer...
    curl -L https://ollama.com/download/OllamaSetup.exe -o OllamaSetup.exe
    if exist OllamaSetup.exe (
        echo [INFO] Installing Ollama (Silent)...
        OllamaSetup.exe /S
        del OllamaSetup.exe
    ) else (
        echo [ERROR] Failed to download Ollama.
    )
) else (
    echo [INFO] Ollama is already installed.
)

echo [INFO] Setup completed successfully!
exit /b 0
