@echo off
echo =========================================
echo    FinRAG - Single Port Mode (9000)
echo =========================================
echo.
echo Frontend and Backend both on port 9000
echo.

set "BACKEND_DIR=c:\Users\Admin\OneDrive\Documents\fin_rag\backend"

REM Kill any existing processes on 9000 and 9001
netstat -ano | findstr ":9000" >nul
if %errorlevel% == 0 (
    echo Stopping existing server on port 9000...
    for /f "tokens=5" %%a in ('netstat -aon ^| find ":9000"') do taskkill /F /PID %%a >nul 2>&1
)

netstat -ano | findstr ":9001" >nul
if %errorlevel% == 0 (
    echo Stopping frontend server on port 9001...
    for /f "tokens=5" %%a in ('netstat -aon ^| find ":9001"') do taskkill /F /PID %%a >nul 2>&1
)

timeout /t 1 /nobreak >nul

echo.
echo Starting Backend (serves Frontend on same port)...
echo.

cd /d "%BACKEND_DIR%"
start "FinRAG Server" cmd /k "python -m uvicorn app.main:app --host 0.0.0.0 --port 9000 --reload"

timeout /t 3 /nobreak >nul

echo.
echo =========================================
echo    Server Started!
echo =========================================
echo.
echo Access URLs:
echo   - Frontend UI: http://localhost:9000
echo   - Backend API: http://localhost:9000/docs
echo   - Health Check: http://localhost:9000/health
echo.
echo Both frontend and backend on port 9000
echo.
pause
