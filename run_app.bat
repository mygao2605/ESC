@echo off
title Khoi chay Viettel BLDC / ESC Controller
cd /d "%~dp0"
echo ========================================================
echo   VIETTEL BLDC / ESC CONTROLLER - MODBUS PROPULSION SUITE
echo   Tap doan Cong nghiep - Vien thong Quan doi (Viettel)
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
