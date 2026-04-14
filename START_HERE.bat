@echo off
echo =========================================
echo    FinRAG - Complete System Startup
echo =========================================
echo.
echo This will start both servers:
echo   - Backend API: http://localhost:9000
echo   - Frontend UI: http://localhost:9001
echo.
echo Press any key to start...
pause >nul

cd /d "c:\Users\Admin\OneDrive\Documents\fin_rag"
python start_all.py
