@echo off
title VIETTEL VMC
cd /d "%~dp0"
echo ========================================================
echo   VIETTEL VMC (Viettel)
echo ========================================================
echo.
echo Dang kiem tra va khoi dong ung dung...
python main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ========================================================
    echo [THONG BAO] Neu gap loi thieu thu vien, hay chay lenh:
    echo        pip install -r requirements.txt
    echo ========================================================
    echo.
    pause
)
