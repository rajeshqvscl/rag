@echo off
echo =========================================
echo Resetting Database and Testing
echo =========================================
echo.

cd /d "c:\Users\Admin\OneDrive\Documents\fin_rag\backend"

REM Delete old empty database
echo Deleting old database...
if exist "finrag.db" (
    del "finrag.db"
    echo Old database deleted
) else (
    echo No existing database found
)

REM Run diagnostic to create new database
echo.
echo Creating new database with tables...
python check_db.py

echo.
echo =========================================
echo If you see "Tables found" with users, drafts, library
echo then the database is working!
echo =========================================
pause
