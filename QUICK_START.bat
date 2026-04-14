@echo off
chcp 65001 >nul
echo =========================================
echo    FinRAG Quick Start
echo =========================================
echo.

set "BACKEND_DIR=c:\Users\Admin\OneDrive\Documents\fin_rag\backend"
set "FRONTEND_DIR=c:\Users\Admin\OneDrive\Documents\fin_rag\frontend"

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python first.
    pause
    exit /b 1
)
echo [OK] Python found

REM Install core dependencies first (no Redis needed)
echo.
echo Installing dependencies...
cd /d "%BACKEND_DIR%"
pip install -q fastapi uvicorn python-dotenv sqlalchemy pydantic requests beautifulsoup4 lxml pandas openpyxl pypdf python-docx python-multipart sentence-transformers faiss-cpu anthropic yfinance sec-edgar-downloader 2>nul
echo [OK] Dependencies installed

REM Check if ports are free
netstat -ano | findstr ":9000" >nul
if %errorlevel% == 0 (
    echo [WARNING] Port 9000 is in use. Killing process...
    for /f "tokens=5" %%a in ('netstat -aon ^| find ":9000"') do taskkill /F /PID %%a >nul 2>&1
)

netstat -ano | findstr ":9001" >nul
if %errorlevel% == 0 (
    echo [WARNING] Port 9001 is in use. Killing process...
    for /f "tokens=5" %%a in ('netstat -aon ^| find ":9001"') do taskkill /F /PID %%a >nul 2>&1
)

echo.
echo =========================================
echo Starting Backend (Port 9000)...
echo =========================================
start "FinRAG Backend" cmd /k "cd /d %BACKEND_DIR% && python -m uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload"

timeout /t 3 /nobreak >nul

echo.
echo =========================================
echo Starting Frontend (Port 9001)...
echo =========================================
start "FinRAG Frontend" cmd /k "cd /d %FRONTEND_DIR% && python server.py"

timeout /t 2 /nobreak >nul

echo.
echo =========================================
echo Testing connection...
echo =========================================
curl -s http://localhost:9000/health >nul 2>&1
if %errorlevel% == 0 (
    echo [OK] Backend is running!
) else (
    echo [WARNING] Backend may still be starting...
)

echo.
echo =========================================
echo    Servers Started!
echo =========================================
echo.
echo Backend API:  http://localhost:9000
echo Frontend UI:  http://localhost:9001
echo Health Check: http://localhost:9000/health
echo.
echo Press any key to exit this window...
echo (Servers will keep running in their windows)
pause >nul
