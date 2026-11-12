# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller Spec file for Viettel BLDC / ESC Controller
Đóng gói toàn bộ mã nguồn, thư viện (customtkinter, matplotlib, pyserial, PIL)
và tài nguyên (logo, icons, themes) thành 1 file .exe duy nhất chạy độc lập.
"""

import sys
import os
from PyInstaller.utils.hooks import collect_all, collect_data_files

block_cipher = None

# Tự động thu thập toàn bộ tài nguyên của customtkinter và matplotlib
ctk_datas, ctk_binaries, ctk_hiddenimports = collect_all('customtkinter')
mpl_datas, mpl_binaries, mpl_hiddenimports = collect_all('matplotlib')

datas = [
    ('viettel_logo.png', '.'),
    ('viettel_logo.ico', '.'),
] + ctk_datas + mpl_datas

binaries = ctk_binaries + mpl_binaries
hiddenimports = [
    'gui_esc',
    'gui_bmu',
    'gui_power',
    'gui_mld',
    'viettel_theme',
    'mgm_comm',
    'mgm_data',
    'serial',
    'serial.tools',
    'serial.tools.list_ports',
    'PIL',
    'PIL._tkinter_finder',
    'tkinter',
    'tkinter.ttk',
    'tkinter.filedialog',
    'tkinter.messagebox',
] + ctk_hiddenimports + mpl_hiddenimports

a = Analysis(
    ['main.py'],
    pathex=[os.path.abspath('.')],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Viettel_BLDC_Controller',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Ẩn cửa sổ dòng lệnh đen khi chạy
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='viettel_logo.ico'
)

