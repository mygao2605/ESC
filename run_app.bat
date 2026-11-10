@echo off
title Khoi chay Viettel ESC Controller
cd /d "%~dp0"
echo ========================================================
echo   VIETTEL ESC CONTROLLER - HE THONG DIEU KHIEN DONG CO
echo   Tap doan Cong nghiep - Vien thong Quan doi (Viettel)
echo ========================================================
echo Dang khoi dong ung dung...
python main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [LOI] Co van de khi chay Python. Nhan phim bat ky de thoat...
    pause
)
