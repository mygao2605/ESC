@echo off
title Dong goi phan mem Viettel BLDC Controller thanh file .exe
cd /d "%~dp0"

echo =======================================================================
echo   VIETTEL BLDC / ESC CONTROLLER - TIEN TRINH TAO FILE EXE DONG GOI
echo   Tap doan Cong nghiep - Vien thong Quan doi (Viettel)
echo =======================================================================
echo.

echo [Buoc 1/3] Kiem tra va cai dat PyInstaller cung cac thu vien can thiet...
python -m pip install --upgrade pip
python -m pip install pyinstaller customtkinter pyserial pillow matplotlib

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [LOI] Khong the cai dat thu vien. Vui long kiem tra ket noi Internet hoac Python!
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [Buoc 2/3] Bat dau dong goi thanh file .exe duy nhat (Single Executable)...
echo Tien trinh nay co the mat khoang 1 - 2 phut...
python -m PyInstaller --clean Viettel_BLDC_Controller.spec

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [LOI] Qua trinh dong goi bi loi!
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo =======================================================================
echo   [THANH CONG!] FILE .EXE DA DUOC TAO TAI:
echo   dist\Viettel_BLDC_Controller.exe
echo =======================================================================
echo.
echo File nay da duoc dong goi kem tat ca thu vien (khong can cai Python nua).
echo Ban co the copy file 'dist\Viettel_BLDC_Controller.exe' sang may bat ky de chay!
echo.
pause

