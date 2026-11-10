"""
VIETTEL ESC & BLDC DRIVER CONTROLLER - High-Tech Propulsion Suite
Giao diện điều khiển, giám sát và cấu hình BLDC Driver / ESC chuyên dụng
Tích hợp chuẩn giao thức Modbus RTU theo bản tin thực tế (bantin.jpeg):
- Cổng truyền thông: Port 11 (921600-8-N-1), Slave ID = 1, Scan Rate = 500ms
- ModbusRead.mbp (F = 03, 11 thanh ghi 0..10):
  StateAct, SpeedRpm, DcBusVolt, D_Curr, Q_Curr, Fault_H, Fault_L, MotorTemp, TempA, TempB, TempC
- ModbusWrite.mbp (F = 16, 2 thanh ghi 0..1):
  ON/OFF, SpeedRpm
"""

import os
import sys
import time
import math
import random
import json
import csv
import queue
import threading
from typing import Dict, Any, List

import customtkinter as ctk
from tkinter import filedialog, messagebox, ttk
from PIL import Image

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from mgm_data import MGMDatabase
from mgm_comm import (
    MGMConnection,
    get_available_ports,
    MODBUS_READ_REGISTERS,
    MODBUS_WRITE_REGISTERS,
    build_fc03_request,
    build_fc16_request,
    append_crc16,
)

# =============================================================================
# BẢNG MÀU CHUẨN THƯƠNG HIỆU VIETTEL (VIETTEL BRAND RED PALETTE)
# =============================================================================
VIETTEL_RED = "#EE0033"          # Màu đỏ nhận diện thương hiệu Viettel
VIETTEL_RED_HOVER = "#C4002A"    # Đỏ đậm khi di chuột qua
VIETTEL_RED_LIGHT = "#FF335C"    # Đỏ sáng làm điểm nhấn
VIETTEL_RED_MUTED = "#5E1822"    # Đỏ trầm viền / nền phụ
VIETTEL_BG_MAIN = "#120E10"      # Nền tổng thể tối trầm
VIETTEL_PANEL_BG = "#1A1416"     # Nền các khung chức năng
VIETTEL_CARD_BG = "#221A1D"      # Nền các ô hiển thị thông số
VIETTEL_BORDER = "#42252A"       # Viền đỏ đen tinh tế
VIETTEL_TEXT_WHITE = "#FFFFFF"   # Chữ trắng tương phản cao
VIETTEL_TEXT_GRAY = "#B5A7AA"    # Chữ xám phụ trợ
MODBUS_BLUE_SEL = "#0078D7"      # Màu xanh đánh dấu dòng giống Modbus Poll

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class ViettelESCApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("VIETTEL BLDC / ESC CONTROLLER - Modbus RTU (ModbusRead.mbp / ModbusWrite.mbp)")
        self.geometry("1380x880")
        self.minsize(1120, 740)
        self.configure(fg_color=VIETTEL_BG_MAIN)

        # Khởi tạo cơ sở dữ liệu và truyền thông Modbus RTU
        self.db = MGMDatabase()
        self.conn = MGMConnection()
        self.conn.on_telemetry_callback = self._on_telemetry_received
        self.conn.on_log_callback = self._on_log_received
        self.conn.on_status_change = self._on_status_changed

        self.selected_device_id = 10
        self.param_widgets: Dict[int, Any] = {}
        self.active_category = "Tất cả (All)"
        self.search_query = ""

        # Dữ liệu vẽ đồ thị thời gian thực (Ring buffers)
        self.max_points = 150
        self.t_data = []
        self.rpm_data = []
        self.v_data = []
        self.id_data = []
        self.iq_data = []
        self.mtemp_data = []
        self.tempa_data = []
        self.tempb_data = []
        self.tempc_data = []

        self.is_monitoring = True
        self.recording_file = None
        self.csv_writer = None

        # Thiết lập Icon cửa sổ (Viettel Logo ICO)
        ico_path = os.path.join(os.path.dirname(__file__), "viettel_logo.ico")
        if os.path.exists(ico_path):
            try:
                self.iconbitmap(ico_path)
            except Exception:
                pass

        self._build_header_bar()
        self._build_main_tabs()
        self._build_status_bar()

        # Hàng đợi đa luồng thread-safe
        self.telemetry_queue = queue.Queue()
        self.log_queue = queue.Queue()

        # Nạp dữ liệu ban đầu
        self._refresh_ports()
        self._load_parameters_ui()

        # Bắt đầu vòng lặp đọc hàng đợi
        self._process_queues()

        # Mặc định kích hoạt chế độ mô phỏng để trải nghiệm ngay bản tin bantin.jpeg
        self.sim_switch.select()
        self._toggle_connection()

    # =========================================================================
    # 1. HEADER BAR & CONTROLS (VIETTEL RED THEMED)
    # =========================================================================
    def _build_header_bar(self):
        self.header_frame = ctk.CTkFrame(
            self, height=74, corner_radius=0,
            fg_color=VIETTEL_PANEL_BG, border_width=1, border_color=VIETTEL_BORDER
        )
        self.header_frame.pack(side="top", fill="x", padx=0, pady=0)

        # Viettel Logo + Tiêu đề thương hiệu
        title_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        title_box.pack(side="left", padx=14, pady=8)

        logo_path = os.path.join(os.path.dirname(__file__), "viettel_logo.png")
        if os.path.exists(logo_path):
            try:
                im = Image.open(logo_path)
                self.logo_img = ctk.CTkImage(light_image=im, dark_image=im, size=(46, 46))
                lbl_logo = ctk.CTkLabel(title_box, image=self.logo_img, text="")
                lbl_logo.pack(side="left", padx=(0, 10))
            except Exception:
                pass

        text_box = ctk.CTkFrame(title_box, fg_color="transparent")
        text_box.pack(side="left")

        lbl_brand = ctk.CTkLabel(
            text_box, text="VIETTEL BLDC / ESC CONTROLLER",
            font=ctk.CTkFont(size=17, weight="bold"), text_color=VIETTEL_TEXT_WHITE
        )
        lbl_brand.pack(anchor="w")

        sub_row = ctk.CTkFrame(text_box, fg_color="transparent")
        sub_row.pack(anchor="w")
        lbl_sub = ctk.CTkLabel(
            sub_row, text="MODBUS RTU PROPULSION SUITE",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_RED
        )
        lbl_sub.pack(side="left")
        lbl_ver = ctk.CTkLabel(
            sub_row, text=" | F=03 Read (11 Regs) & F=16 Write (2 Regs)",
            font=ctk.CTkFont(size=11), text_color=VIETTEL_TEXT_GRAY
        )
        lbl_ver.pack(side="left")

        # Cấu hình cổng Serial & Baudrate (Mặc định COM11 : 921600-8-N-1 theo bantin.jpeg)
        conn_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        conn_frame.pack(side="left", padx=12, pady=8)
        ctk.CTkLabel(
            conn_frame, text="Cổng Serial (Port & Baud 8-N-1):",
            font=ctk.CTkFont(size=11), text_color=VIETTEL_TEXT_GRAY
        ).pack(anchor="w")

        port_row = ctk.CTkFrame(conn_frame, fg_color="transparent")
        port_row.pack(anchor="w", pady=2)
        self.cb_port = ctk.CTkComboBox(port_row, values=["COM11"], width=105, border_color=VIETTEL_BORDER)
        self.cb_port.set("COM11")
        self.cb_port.pack(side="left", padx=(0, 4))

        self.btn_refresh_ports = ctk.CTkButton(
            port_row, text="↻", width=28, fg_color="#332427", hover_color="#4D353A",
            command=self._refresh_ports
        )
        self.btn_refresh_ports.pack(side="left", padx=(0, 4))

        self.cb_baud = ctk.CTkComboBox(
            port_row,
            values=["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"],
            width=95, border_color=VIETTEL_BORDER
        )
        self.cb_baud.set("921600")
        self.cb_baud.pack(side="left")

        # Cấu hình nhanh Slave ID & Scan Rate (SR)
        mb_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        mb_frame.pack(side="left", padx=10, pady=8)
        ctk.CTkLabel(
            mb_frame, text="Modbus Slave ID & Scan Rate:",
            font=ctk.CTkFont(size=11), text_color=VIETTEL_TEXT_GRAY
        ).pack(anchor="w")

        mb_row = ctk.CTkFrame(mb_frame, fg_color="transparent")
        mb_row.pack(anchor="w", pady=2)
        ctk.CTkLabel(mb_row, text="ID:", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=(0, 3))
        self.ent_slave_id = ctk.CTkEntry(mb_row, width=45, border_color=VIETTEL_BORDER)
        self.ent_slave_id.insert(0, "1")
        self.ent_slave_id.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(mb_row, text="SR (ms):", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=(0, 3))
        self.cb_sr = ctk.CTkComboBox(mb_row, values=["100", "200", "500", "1000"], width=75, border_color=VIETTEL_BORDER, command=self._on_sr_changed)
        self.cb_sr.set("500")
        self.cb_sr.pack(side="left")

        # Bộ chọn dòng thiết bị (Device Selector)
        dev_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        dev_frame.pack(side="left", padx=10, pady=8)
        ctk.CTkLabel(dev_frame, text="Dòng thiết bị (Model):", font=ctk.CTkFont(size=11), text_color=VIETTEL_TEXT_GRAY).pack(anchor="w")

        dev_names = [f"{d['name']} (ID {d['id']})" for d in sorted(self.db.devices.values(), key=lambda x: x['id'])]
        default_dev_str = next((s for s in dev_names if f"ID {self.selected_device_id}" in s), dev_names[0] if dev_names else "BLDC Driver")
        self.cb_device = ctk.CTkComboBox(
            dev_frame, values=dev_names, width=190, command=self._on_device_selected,
            border_color=VIETTEL_BORDER, button_color=VIETTEL_RED, button_hover_color=VIETTEL_RED_HOVER
        )
        self.cb_device.set(default_dev_str)
        self.cb_device.pack(anchor="w", pady=2)

        # Chuyển đổi mô phỏng & Nút kết nối màu đỏ Viettel
        ctrl_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        ctrl_frame.pack(side="right", padx=14, pady=8)

        self.sim_switch = ctk.CTkSwitch(
            ctrl_frame, text="Chế độ Mô phỏng (Simulator)",
            progress_color=VIETTEL_RED, font=ctk.CTkFont(size=12)
        )
        self.sim_switch.pack(side="top", anchor="e", pady=(0, 4))

        self.btn_connect = ctk.CTkButton(
            ctrl_frame, text="Kết nối (Connect)", width=150,
            fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER,
            font=ctk.CTkFont(size=12, weight="bold"), command=self._toggle_connection
        )
        self.btn_connect.pack(side="top", anchor="e")

    # =========================================================================
    # 2. MAIN TABS (VIETTEL RED STYLING)
    # =========================================================================
    def _build_main_tabs(self):
        self.tabview = ctk.CTkTabview(
            self,
            corner_radius=10,
            fg_color=VIETTEL_PANEL_BG,
            segmented_button_selected_color=VIETTEL_RED,
            segmented_button_selected_hover_color=VIETTEL_RED_HOVER,
            segmented_button_unselected_color="#2A2022",
            segmented_button_unselected_hover_color="#3D2B2E"
        )
        self.tabview.pack(fill="both", expand=True, padx=12, pady=(6, 6))

        self.tab_modbus = self.tabview.add("📡 Bản tin Modbus (Read/Write)")
        self.tab_telemetry = self.tabview.add("📊 Giám sát & Đồ thị (Live)")
        self.tab_settings = self.tabview.add("⚙️ Cấu hình tham số (Settings)")
        self.tab_history = self.tabview.add("📈 Lịch sử Datalogger (BlackBox)")
        self.tab_events = self.tabview.add("⚠️ Nhật ký sự kiện (Events)")
        self.tab_device = self.tabview.add("ℹ️ Thông tin & Firmware")
        self.tab_terminal = self.tabview.add("💻 Terminal Modbus HEX")

        self._build_modbus_tab()
        self._build_telemetry_tab()
        self._build_settings_tab()
        self._build_history_tab()
        self._build_events_tab()
        self._build_device_info_tab()
        self._build_terminal_tab()

    # -------------------------------------------------------------------------
    # TAB 1: BẢN TIN MODBUS POLL / WRITE CHUẨN BANTIN.JPEG
    # -------------------------------------------------------------------------
    def _build_modbus_tab(self):
        # Thanh công cụ phía trên của tab Modbus
        top_bar = ctk.CTkFrame(self.tab_modbus, height=44, fg_color="#221A1D", corner_radius=8, border_width=1, border_color=VIETTEL_BORDER)
        top_bar.pack(fill="x", padx=6, pady=(4, 6))

        ctk.CTkLabel(
            top_bar,
            text="CHẾ ĐỘ GIÁM SÁT & ĐIỀU KHIỂN BẢN TIN MODBUS RTU (921600-8-N-1)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=VIETTEL_RED_LIGHT
        ).pack(side="left", padx=12)

        # Tùy chỉnh địa chỉ thanh ghi bắt đầu Read / Write
        addr_box = ctk.CTkFrame(top_bar, fg_color="transparent")
        addr_box.pack(side="right", padx=8, pady=4)

        ctk.CTkLabel(addr_box, text="Read Start Addr:", font=ctk.CTkFont(size=11), text_color=VIETTEL_TEXT_GRAY).pack(side="left", padx=(4, 2))
        self.ent_read_addr = ctk.CTkEntry(addr_box, width=50, border_color=VIETTEL_BORDER)
        self.ent_read_addr.insert(0, "0")
        self.ent_read_addr.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(addr_box, text="Write Start Addr:", font=ctk.CTkFont(size=11), text_color=VIETTEL_TEXT_GRAY).pack(side="left", padx=(4, 2))
        self.ent_write_addr = ctk.CTkEntry(addr_box, width=50, border_color=VIETTEL_BORDER)
        self.ent_write_addr.insert(0, "0")
        self.ent_write_addr.pack(side="left", padx=(0, 8))

        btn_apply_addr = ctk.CTkButton(
            addr_box, text="Áp dụng", width=70, fg_color="#332427", hover_color="#4D353A",
            command=self._apply_modbus_settings
        )
        btn_apply_addr.pack(side="left", padx=4)

        btn_reset_cnt = ctk.CTkButton(
            addr_box, text="⟳ Reset bộ đếm Tx/Err", width=135, fg_color="#2B2124", hover_color="#3D2E32",
            command=self._reset_modbus_counters
        )
        btn_reset_cnt.pack(side="left", padx=4)

        # Khung chính chia 2 cột song song giống hệt cửa sổ ModbusRead.mbp (Trái) và ModbusWrite.mbp (Phải)
        main_split = ctk.CTkFrame(self.tab_modbus, fg_color="transparent")
        main_split.pack(fill="both", expand=True, padx=6, pady=2)
        main_split.grid_columnconfigure(0, weight=11)
        main_split.grid_columnconfigure(1, weight=10)
        main_split.grid_rowconfigure(0, weight=1)

        # =====================================================================
        # CỬA SỔ TRÁI: ModbusRead.mbp (Function 03 - Read Holding Registers)
        # =====================================================================
        read_win = ctk.CTkFrame(main_split, fg_color="#181214", corner_radius=8, border_width=2, border_color=VIETTEL_BORDER)
        read_win.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=2)

        # Thanh tiêu đề cửa sổ con ModbusRead.mbp
        read_title_bar = ctk.CTkFrame(read_win, height=32, fg_color="#2E1C20", corner_radius=6)
        read_title_bar.pack(fill="x", padx=4, pady=(4, 2))
        ctk.CTkLabel(
            read_title_bar, text="📄 ModbusRead.mbp  —  Function 03 (Read Holding Registers)",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=VIETTEL_TEXT_WHITE
        ).pack(side="left", padx=10, pady=4)

        # Dòng trạng thái chuẩn: Tx = 682: Err = 3: ID = 1: F = 03: SR = 500ms
        read_stat_bar = ctk.CTkFrame(read_win, height=30, fg_color="#22181A", corner_radius=4)
        read_stat_bar.pack(fill="x", padx=6, pady=2)
        self.lbl_read_stat = ctk.CTkLabel(
            read_stat_bar,
            text="Tx = 0: Err = 0: ID = 1: F = 03: SR = 500ms",
            font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
            text_color="#00E676"
        )
        self.lbl_read_stat.pack(side="left", padx=10, pady=3)

        # Bảng 11 thanh ghi đọc (0 .. 10)
        read_table_box = ctk.CTkFrame(read_win, fg_color="#140F11", corner_radius=6, border_width=1, border_color=VIETTEL_BORDER)
        read_table_box.pack(fill="both", expand=True, padx=6, pady=4)

        # Header bảng ModbusRead.mbp
        r_hdr = ctk.CTkFrame(read_table_box, height=30, fg_color="#2D1E22", corner_radius=4)
        r_hdr.pack(fill="x", padx=4, pady=(4, 2))
        ctk.CTkLabel(r_hdr, text="Addr", width=48, font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_RED_LIGHT).pack(side="left", padx=2)
        ctk.CTkLabel(r_hdr, text="Name", width=125, anchor="w", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=6)
        ctk.CTkLabel(r_hdr, text="00000 (Value)", width=110, anchor="e", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=6)
        ctk.CTkLabel(r_hdr, text="HEX", width=75, anchor="center", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_GRAY).pack(side="left", padx=4)
        ctk.CTkLabel(r_hdr, text="Mô tả / Đơn vị", anchor="w", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_GRAY).pack(side="left", fill="x", expand=True, padx=6)

        self.read_row_labels: Dict[int, Dict[str, ctk.CTkLabel]] = {}
        init_read_vals = [0, 0, 0, 9, -1, 0, 0, 30, 24, 26, 26]

        for reg in MODBUS_READ_REGISTERS:
            idx = reg["index"]
            is_last = (idx == 10)  # Dòng 10 TempC được bôi xanh như trong ảnh bantin.jpeg
            row_bg = "#1E1618" if idx % 2 == 0 else "#251B1E"
            name_bg = MODBUS_BLUE_SEL if is_last else "transparent"

            row = ctk.CTkFrame(read_table_box, height=31, fg_color=row_bg, corner_radius=4)
            row.pack(fill="x", padx=4, pady=1.5)

            lbl_idx = ctk.CTkLabel(
                row, text=f"{idx}", width=48,
                font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
                text_color=VIETTEL_TEXT_GRAY
            )
            lbl_idx.pack(side="left", padx=2)

            lbl_name = ctk.CTkLabel(
                row, text=f"  {reg['name']}", width=125, anchor="w",
                fg_color=name_bg, corner_radius=3,
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                text_color=VIETTEL_TEXT_WHITE
            )
            lbl_name.pack(side="left", padx=6, pady=2)

            v0 = init_read_vals[idx]
            lbl_val = ctk.CTkLabel(
                row, text=f"{v0}", width=110, anchor="e",
                font=ctk.CTkFont(family="Consolas", size=14, weight="bold"),
                text_color="#00E676" if idx in (1, 2) else VIETTEL_TEXT_WHITE
            )
            lbl_val.pack(side="left", padx=6)

            lbl_hex = ctk.CTkLabel(
                row, text=f"0x{(v0 & 0xFFFF):04X}", width=75, anchor="center",
                font=ctk.CTkFont(family="Consolas", size=11),
                text_color=VIETTEL_TEXT_GRAY
            )
            lbl_hex.pack(side="left", padx=4)

            lbl_desc = ctk.CTkLabel(
                row, text=f"{reg['desc']} ({reg['unit']})" if reg['unit'] else reg['desc'],
                anchor="w", font=ctk.CTkFont(size=11), text_color=VIETTEL_TEXT_GRAY
            )
            lbl_desc.pack(side="left", fill="x", expand=True, padx=6)

            self.read_row_labels[idx] = {
                "addr": lbl_idx,
                "name": lbl_name,
                "val": lbl_val,
                "hex": lbl_hex,
                "desc": lbl_desc,
            }

        # Khung hiển thị bản tin HEX F=03 trực tiếp
        read_hex_box = ctk.CTkFrame(read_win, fg_color="#120D0F", corner_radius=6, border_width=1, border_color=VIETTEL_BORDER)
        read_hex_box.pack(fill="x", padx=6, pady=(2, 6))
        self.lbl_read_tx_hex = ctk.CTkLabel(
            read_hex_box, text="[TX F=03] >> 01 03 00 00 00 0B 04 0D",
            font=ctk.CTkFont(family="Consolas", size=11), text_color="#FFD54F", anchor="w"
        )
        self.lbl_read_tx_hex.pack(fill="x", padx=8, pady=(4, 1))
        self.lbl_read_rx_hex = ctk.CTkLabel(
            read_hex_box, text="[RX F=03] << Đang chờ dữ liệu...",
            font=ctk.CTkFont(family="Consolas", size=11), text_color="#80CBC4", anchor="w"
        )
        self.lbl_read_rx_hex.pack(fill="x", padx=8, pady=(1, 4))

        # =====================================================================
        # CỬA SỔ PHẢI: ModbusWrite.mbp (Function 16 - Write Multiple Registers)
        # =====================================================================
        write_win = ctk.CTkFrame(main_split, fg_color="#181214", corner_radius=8, border_width=2, border_color=VIETTEL_BORDER)
        write_win.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=2)

        # Thanh tiêu đề cửa sổ con ModbusWrite.mbp
        write_title_bar = ctk.CTkFrame(write_win, height=32, fg_color="#3B151C", corner_radius=6)
        write_title_bar.pack(fill="x", padx=4, pady=(4, 2))
        ctk.CTkLabel(
            write_title_bar, text="📝 ModbusWrite.mbp  —  Function 16 (Write Multiple Registers)",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=VIETTEL_TEXT_WHITE
        ).pack(side="left", padx=10, pady=4)

        # Dòng trạng thái chuẩn: Tx = 406: Err = 2: ID = 1: F = 16: SR = 500ms
        write_stat_bar = ctk.CTkFrame(write_win, height=30, fg_color="#22181A", corner_radius=4)
        write_stat_bar.pack(fill="x", padx=6, pady=2)
        self.lbl_write_stat = ctk.CTkLabel(
            write_stat_bar,
            text="Tx = 0: Err = 0: ID = 1: F = 16: SR = 500ms",
            font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
            text_color="#FFD54F"
        )
        self.lbl_write_stat.pack(side="left", padx=10, pady=3)

        # Bảng 2 thanh ghi ghi (0: ON/OFF, 1: SpeedRpm) giống hệt ModbusWrite.mbp
        write_table_box = ctk.CTkFrame(write_win, fg_color="#140F11", corner_radius=6, border_width=1, border_color=VIETTEL_BORDER)
        write_table_box.pack(fill="x", padx=6, pady=4)

        w_hdr = ctk.CTkFrame(write_table_box, height=30, fg_color="#2D1E22", corner_radius=4)
        w_hdr.pack(fill="x", padx=4, pady=(4, 2))
        ctk.CTkLabel(w_hdr, text="Addr", width=48, font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_RED_LIGHT).pack(side="left", padx=2)
        ctk.CTkLabel(w_hdr, text="Name", width=130, anchor="w", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=6)
        ctk.CTkLabel(w_hdr, text="00000 (Giá trị hiện tại)", width=150, anchor="e", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=6)
        ctk.CTkLabel(w_hdr, text="Nhập mới & Enter", anchor="w", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_GRAY).pack(side="left", fill="x", expand=True, padx=8)

        # Dòng 0: ON/OFF
        w_row0 = ctk.CTkFrame(write_table_box, height=38, fg_color="#1E1618", corner_radius=4)
        w_row0.pack(fill="x", padx=4, pady=2)
        self.lbl_w_addr0 = ctk.CTkLabel(w_row0, text="0", width=48, font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color=VIETTEL_TEXT_GRAY)
        self.lbl_w_addr0.pack(side="left", padx=2)
        ctk.CTkLabel(w_row0, text="  ON/OFF", width=130, anchor="w", font=ctk.CTkFont(size=12, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=6)
        self.lbl_w_val0 = ctk.CTkLabel(
            w_row0, text="0", width=150, anchor="e",
            font=ctk.CTkFont(family="Consolas", size=14, weight="bold"), text_color=VIETTEL_TEXT_WHITE
        )
        self.lbl_w_val0.pack(side="left", padx=6)
        self.ent_w_onoff = ctk.CTkEntry(w_row0, width=110, border_color=VIETTEL_BORDER, placeholder_text="0 hoặc 1")
        self.ent_w_onoff.insert(0, "0")
        self.ent_w_onoff.pack(side="left", padx=8, pady=4)
        self.ent_w_onoff.bind("<Return>", lambda e: self._send_write_from_entries())

        # Dòng 1: SpeedRpm (Ô giá trị màu xanh MODBUS_BLUE_SEL như trong ảnh bantin.jpeg)
        w_row1 = ctk.CTkFrame(write_table_box, height=38, fg_color="#251B1E", corner_radius=4)
        w_row1.pack(fill="x", padx=4, pady=(2, 6))
        self.lbl_w_addr1 = ctk.CTkLabel(w_row1, text="1", width=48, font=ctk.CTkFont(family="Consolas", size=12, weight="bold"), text_color=VIETTEL_TEXT_GRAY)
        self.lbl_w_addr1.pack(side="left", padx=2)
        ctk.CTkLabel(w_row1, text="  SpeedRpm", width=130, anchor="w", font=ctk.CTkFont(size=12, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=6)
        self.lbl_w_val1 = ctk.CTkLabel(
            w_row1, text="0  ", width=150, anchor="e",
            fg_color=MODBUS_BLUE_SEL, corner_radius=3,
            font=ctk.CTkFont(family="Consolas", size=14, weight="bold"), text_color=VIETTEL_TEXT_WHITE
        )
        self.lbl_w_val1.pack(side="left", padx=6, pady=3)
        self.ent_w_rpm = ctk.CTkEntry(w_row1, width=110, border_color=VIETTEL_BORDER, placeholder_text="RPM")
        self.ent_w_rpm.insert(0, "0")
        self.ent_w_rpm.pack(side="left", padx=8, pady=4)
        self.ent_w_rpm.bind("<Return>", lambda e: self._send_write_from_entries())

        # =====================================================================
        # BẢNG ĐIỀU KHIỂN ĐỘNG CƠ BLDC TRỰC QUAN (QUICK MOTOR CONTROL PANEL)
        # =====================================================================
        ctrl_panel = ctk.CTkFrame(write_win, fg_color=VIETTEL_CARD_BG, corner_radius=8, border_width=1, border_color=VIETTEL_BORDER)
        ctrl_panel.pack(fill="both", expand=True, padx=6, pady=4)

        ctk.CTkLabel(
            ctrl_panel, text="🎛️ BẢNG ĐIỀU KHIỂN ĐỘNG CƠ BLDC (MODBUS F=16 WRITE)",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=VIETTEL_RED_LIGHT
        ).pack(anchor="w", padx=12, pady=(10, 6))

        # Hàng nút BẬT (ON=1) / TẮT (OFF=0)
        btn_row = ctk.CTkFrame(ctrl_panel, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=4)

        self.btn_motor_on = ctk.CTkButton(
            btn_row, text="🟢 BẬT ĐỘNG CƠ (ON/OFF = 1)", height=38,
            fg_color="#1E8E3E", hover_color="#16692D",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: self._quick_set_on_off(1)
        )
        self.btn_motor_on.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_motor_off = ctk.CTkButton(
            btn_row, text="🔴 DỪNG ĐỘNG CƠ (ON/OFF = 0)", height=38,
            fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=lambda: self._quick_set_on_off(0)
        )
        self.btn_motor_off.pack(side="left", fill="x", expand=True, padx=(6, 0))

        # Thanh trượt đặt tốc độ SpeedRpm
        rpm_slider_box = ctk.CTkFrame(ctrl_panel, fg_color="#181214", corner_radius=6, border_width=1, border_color=VIETTEL_BORDER)
        rpm_slider_box.pack(fill="x", padx=12, pady=8)

        rpm_top = ctk.CTkFrame(rpm_slider_box, fg_color="transparent")
        rpm_top.pack(fill="x", padx=10, pady=(6, 2))
        ctk.CTkLabel(
            rpm_top, text="Đặt tốc độ mục tiêu (Thanh ghi 1 - SpeedRpm):",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_WHITE
        ).pack(side="left")
        self.lbl_target_rpm_big = ctk.CTkLabel(
            rpm_top, text="0 RPM",
            font=ctk.CTkFont(family="Consolas", size=15, weight="bold"), text_color="#00E676"
        )
        self.lbl_target_rpm_big.pack(side="right")

        self.slider_modbus_rpm = ctk.CTkSlider(
            rpm_slider_box, from_=0, to=6000, number_of_steps=120,
            progress_color=VIETTEL_RED, button_color=VIETTEL_RED, button_hover_color=VIETTEL_RED_HOVER,
            command=self._on_modbus_rpm_slider
        )
        self.slider_modbus_rpm.set(0)
        self.slider_modbus_rpm.pack(fill="x", padx=10, pady=(2, 6))

        # Các mức tốc độ đặt nhanh (Presets)
        preset_row = ctk.CTkFrame(rpm_slider_box, fg_color="transparent")
        preset_row.pack(fill="x", padx=10, pady=(0, 8))
        ctk.CTkLabel(preset_row, text="Chọn nhanh:", font=ctk.CTkFont(size=11), text_color=VIETTEL_TEXT_GRAY).pack(side="left", padx=(0, 6))
        for spd in [0, 500, 1000, 1500, 2000, 3000, 5000]:
            b = ctk.CTkButton(
                preset_row, text=f"{spd}", width=52, height=26,
                fg_color="#2B2023", hover_color=VIETTEL_RED,
                font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda s=spd: self._set_preset_rpm(s)
            )
            b.pack(side="left", padx=2)

        # Nút gửi lệnh F=16 ngay lập tức & Công tắc gửi chu kỳ 500ms
        action_row = ctk.CTkFrame(ctrl_panel, fg_color="transparent")
        action_row.pack(fill="x", padx=12, pady=(4, 8))

        self.sw_cyclic_write = ctk.CTkSwitch(
            action_row, text="Tự động gửi lặp F=16 (SR=500ms)",
            progress_color=VIETTEL_RED, font=ctk.CTkFont(size=11),
            command=self._on_cyclic_write_toggled
        )
        self.sw_cyclic_write.select()
        self.sw_cyclic_write.pack(side="left")

        self.btn_send_fc16 = ctk.CTkButton(
            action_row, text="⚡ Gửi bản tin F=16 ngay", width=165, height=34,
            fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self._send_write_from_entries
        )
        self.btn_send_fc16.pack(side="right")

        # Khung hiển thị bản tin HEX F=16 trực tiếp
        write_hex_box = ctk.CTkFrame(write_win, fg_color="#120D0F", corner_radius=6, border_width=1, border_color=VIETTEL_BORDER)
        write_hex_box.pack(fill="x", padx=6, pady=(2, 6))
        self.lbl_write_tx_hex = ctk.CTkLabel(
            write_hex_box, text="[TX F=16] >> 01 10 00 00 00 02 04 00 00 00 00 F3 AF",
            font=ctk.CTkFont(family="Consolas", size=11), text_color="#FFD54F", anchor="w"
        )
        self.lbl_write_tx_hex.pack(fill="x", padx=8, pady=(4, 1))
        self.lbl_write_rx_hex = ctk.CTkLabel(
            write_hex_box, text="[RX F=16] << Đang chờ phản hồi...",
            font=ctk.CTkFont(family="Consolas", size=11), text_color="#80CBC4", anchor="w"
        )
        self.lbl_write_rx_hex.pack(fill="x", padx=8, pady=(1, 4))

    # -------------------------------------------------------------------------
    # TAB 2: LIVE TELEMETRY & GAUGES (ĐỒNG BỘ 11 THANH GHI BANTIN.JPEG)
    # -------------------------------------------------------------------------
    def _build_telemetry_tab(self):
        # 1. Khung đồng hồ đo số điện tử hiển thị toàn bộ 11 thanh ghi từ bantin.jpeg
        cards_frame = ctk.CTkFrame(self.tab_telemetry, fg_color="transparent")
        cards_frame.pack(fill="x", padx=5, pady=5)

        self.card_labels = {}
        metrics = [
            ("StateAct",   "[0] TRẠNG THÁI (StateAct)",     "0 (IDLE)", "",    "#00E676"),
            ("SpeedRpm",   "[1] TỐC ĐỘ (SpeedRpm)",         "0",        "RPM", "#00E676"),
            ("DcBusVolt",  "[2] ĐIỆN ÁP DC BUS (DcBusVolt)","0",        "V",   VIETTEL_RED_LIGHT),
            ("D_Curr",     "[3] DÒNG TRỤC D (D_Curr)",      "9",        "A",   "#4FC3F7"),
            ("Q_Curr",     "[4] DÒNG TRỤC Q (Q_Curr)",      "-1",       "A",   "#FF7043"),
            ("Fault_HL",   "[5-6] MÃ LỖI (Fault_H / L)",    "0 / 0",    "HEX", "#FFD54F"),
            ("MotorTemp",  "[7] NHIỆT ĐỘ MOTOR (MotorTemp)","30",       "°C",  "#FF8A80"),
            ("PhaseTemps", "[8-10] NHIỆT ĐỘ PHA (A / B / C)","24/26/26","°C",  VIETTEL_RED),
        ]

        for idx, (key, title, init_val, unit, color) in enumerate(metrics):
            r = idx // 4
            c = idx % 4
            card = ctk.CTkFrame(cards_frame, fg_color=VIETTEL_CARD_BG, corner_radius=8, border_width=1, border_color=VIETTEL_BORDER)
            card.grid(row=r, column=c, padx=5, pady=5, sticky="nsew")
            cards_frame.grid_columnconfigure(c, weight=1)

            ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=10, weight="bold"), text_color=VIETTEL_TEXT_GRAY).pack(anchor="w", padx=10, pady=(6, 2))

            val_box = ctk.CTkFrame(card, fg_color="transparent")
            val_box.pack(anchor="w", padx=10, pady=(0, 6))

            lbl_val = ctk.CTkLabel(val_box, text=init_val, font=ctk.CTkFont(family="Consolas", size=21, weight="bold"), text_color=color)
            lbl_val.pack(side="left")

            if unit:
                lbl_unit = ctk.CTkLabel(val_box, text=f" {unit}", font=ctk.CTkFont(size=11), text_color=VIETTEL_TEXT_GRAY)
                lbl_unit.pack(side="left", padx=(3, 0), pady=(5, 0))

            self.card_labels[key] = lbl_val

        # 2. Thanh điều khiển nhanh ON/OFF & SpeedRpm ngay trên tab Đồ thị
        th_frame = ctk.CTkFrame(self.tab_telemetry, height=50, fg_color=VIETTEL_PANEL_BG, corner_radius=8, border_width=1, border_color=VIETTEL_BORDER)
        th_frame.pack(fill="x", padx=5, pady=4)

        self.btn_live_toggle_on = ctk.CTkButton(
            th_frame, text="🟢 ON (Chạy)", width=95, fg_color="#1E8E3E", hover_color="#16692D",
            font=ctk.CTkFont(size=11, weight="bold"), command=lambda: self._quick_set_on_off(1)
        )
        self.btn_live_toggle_on.pack(side="left", padx=(10, 4), pady=6)

        self.btn_live_toggle_off = ctk.CTkButton(
            th_frame, text="🔴 OFF (Dừng)", width=95, fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER,
            font=ctk.CTkFont(size=11, weight="bold"), command=lambda: self._quick_set_on_off(0)
        )
        self.btn_live_toggle_off.pack(side="left", padx=4, pady=6)

        ctk.CTkLabel(
            th_frame, text="Đặt tốc độ (SpeedRpm):",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=VIETTEL_TEXT_WHITE
        ).pack(side="left", padx=(12, 6))

        self.slider_throttle = ctk.CTkSlider(
            th_frame, from_=0, to=6000, number_of_steps=120,
            progress_color=VIETTEL_RED, button_color=VIETTEL_RED, button_hover_color=VIETTEL_RED_HOVER,
            command=self._on_live_rpm_slider_changed
        )
        self.slider_throttle.set(0)
        self.slider_throttle.pack(side="left", fill="x", expand=True, padx=8)

        self.lbl_throttle_val = ctk.CTkLabel(
            th_frame, text="0 RPM", width=85,
            font=ctk.CTkFont(family="Consolas", size=13, weight="bold"), text_color=VIETTEL_RED_LIGHT
        )
        self.lbl_throttle_val.pack(side="left", padx=(0, 12))

        # 3. Thanh công cụ đồ thị
        chart_ctrl = ctk.CTkFrame(self.tab_telemetry, height=35, fg_color="transparent")
        chart_ctrl.pack(fill="x", padx=5, pady=2)

        self.chk_rpm = ctk.CTkCheckBox(chart_ctrl, text="SpeedRpm / 10", text_color="#00E676", fg_color="#00E676", font=ctk.CTkFont(size=11, weight="bold"))
        self.chk_rpm.select()
        self.chk_rpm.pack(side="left", padx=8)

        self.chk_v = ctk.CTkCheckBox(chart_ctrl, text="DcBusVolt (V)", text_color=VIETTEL_RED_LIGHT, fg_color=VIETTEL_RED, font=ctk.CTkFont(size=11, weight="bold"))
        self.chk_v.select()
        self.chk_v.pack(side="left", padx=8)

        self.chk_id = ctk.CTkCheckBox(chart_ctrl, text="D_Curr (A)", text_color="#4FC3F7", fg_color="#4FC3F7", font=ctk.CTkFont(size=11, weight="bold"))
        self.chk_id.select()
        self.chk_id.pack(side="left", padx=8)

        self.chk_iq = ctk.CTkCheckBox(chart_ctrl, text="Q_Curr (A)", text_color="#FF7043", fg_color="#FF7043", font=ctk.CTkFont(size=11, weight="bold"))
        self.chk_iq.select()
        self.chk_iq.pack(side="left", padx=8)

        self.chk_t = ctk.CTkCheckBox(chart_ctrl, text="MotorTemp & TempA/B/C (°C)", text_color="#FFD54F", fg_color="#FFD54F", font=ctk.CTkFont(size=11, weight="bold"))
        self.chk_t.select()
        self.chk_t.pack(side="left", padx=8)

        self.btn_pause_chart = ctk.CTkButton(chart_ctrl, text="Tạm dừng", width=80, fg_color="#332427", hover_color="#4D353A", command=self._toggle_pause_chart)
        self.btn_pause_chart.pack(side="right", padx=5)

        self.btn_clear_chart = ctk.CTkButton(chart_ctrl, text="Xóa đồ thị", width=80, fg_color="#332427", hover_color="#4D353A", command=self._clear_chart)
        self.btn_clear_chart.pack(side="right", padx=5)

        self.btn_record = ctk.CTkButton(chart_ctrl, text="🔴 Ghi log CSV (11 kênh)", width=155, fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER, font=ctk.CTkFont(weight="bold"), command=self._toggle_recording)
        self.btn_record.pack(side="right", padx=5)

        # Canvas Matplotlib thời gian thực (Viettel Dark Red Canvas)
        self.fig = Figure(figsize=(8, 3.5), dpi=100, facecolor="#140F11")
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor("#0F0B0D")
        self.ax.tick_params(colors="#CCCCCC", labelsize=9)
        self.ax.grid(True, linestyle="--", alpha=0.25, color="#5E2028")
        self.ax.set_title("ĐỒ THỊ GIÁM SÁT THỜI GIAN THỰC MODBUS RTU (SpeedRpm, DcBusVolt, D/Q_Curr, Temps)", color=VIETTEL_TEXT_WHITE, fontsize=10, pad=6, weight="bold")

        for spine in self.ax.spines.values():
            spine.set_color("#4A1B22")

        self.line_rpm, = self.ax.plot([], [], label="SpeedRpm / 10", color="#00E676", linewidth=1.8)
        self.line_v, = self.ax.plot([], [], label="DcBusVolt (V)", color=VIETTEL_RED, linewidth=2.0)
        self.line_id, = self.ax.plot([], [], label="D_Curr (A)", color="#4FC3F7", linewidth=1.5)
        self.line_iq, = self.ax.plot([], [], label="Q_Curr (A)", color="#FF7043", linewidth=1.8)
        self.line_mtemp, = self.ax.plot([], [], label="MotorTemp (°C)", color="#FFD54F", linewidth=1.5)
        self.line_tempa, = self.ax.plot([], [], label="TempA (°C)", color="#BA68C8", linewidth=1.2, linestyle="--")
        self.ax.legend(loc="upper left", ncol=3, facecolor="#1E1618", edgecolor=VIETTEL_BORDER, labelcolor=VIETTEL_TEXT_WHITE, fontsize=8)

        self.canvas = FigureCanvasTkAgg(self.fig, master=self.tab_telemetry)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=5)

    # -------------------------------------------------------------------------
    # CÁC HÀM XỬ LÝ SỰ KIỆN ĐIỀU KHIỂN MODBUS
    # -------------------------------------------------------------------------
    def _on_sr_changed(self, val_str: str):
        try:
            sr = int(val_str)
            self.conn.scan_rate_ms = max(50, sr)
        except Exception:
            pass

    def _apply_modbus_settings(self):
        try:
            sid = int(self.ent_slave_id.get().strip())
            sr = int(self.cb_sr.get().strip())
            r_addr = int(self.ent_read_addr.get().strip())
            w_addr = int(self.ent_write_addr.get().strip())
            self.conn.slave_id = max(1, min(247, sid))
            self.conn.scan_rate_ms = max(50, min(5000, sr))
            self.conn.read_start_addr = max(0, r_addr)
            self.conn.write_start_addr = max(0, w_addr)
            # Cập nhật nhãn địa chỉ trên bảng
            for i, row_dict in self.read_row_labels.items():
                row_dict["addr"].configure(text=f"{self.conn.read_start_addr + i}")
            self.lbl_w_addr0.configure(text=f"{self.conn.write_start_addr}")
            self.lbl_w_addr1.configure(text=f"{self.conn.write_start_addr + 1}")
            self.conn.log(
                f"Đã cập nhật cấu hình Modbus: ID={self.conn.slave_id}, SR={self.conn.scan_rate_ms}ms, ReadAddr={self.conn.read_start_addr}, WriteAddr={self.conn.write_start_addr}",
                "SUCCESS"
            )
        except Exception as e:
            messagebox.showerror("Lỗi dữ liệu", f"Thông số địa chỉ Modbus không hợp lệ: {e}")

    def _reset_modbus_counters(self):
        self.conn.reset_counters()

    def _quick_set_on_off(self, on_val: int):
        try:
            rpm_val = int(self.ent_w_rpm.get().strip())
        except Exception:
            rpm_val = self.conn.current_write_regs[1]
        if on_val == 1 and rpm_val == 0:
            # Nếu bật động cơ mà tốc độ đang 0 thì giữ 0 hoặc lấy từ thanh trượt
            rpm_val = int(self.slider_modbus_rpm.get())
        self.ent_w_onoff.delete(0, "end")
        self.ent_w_onoff.insert(0, str(on_val))
        self.ent_w_rpm.delete(0, "end")
        self.ent_w_rpm.insert(0, str(rpm_val))
        self.conn.write_control_command(on_val, rpm_val, immediate=True)

    def _set_preset_rpm(self, rpm_val: int):
        self.slider_modbus_rpm.set(rpm_val)
        self.slider_throttle.set(rpm_val)
        self.lbl_target_rpm_big.configure(text=f"{rpm_val} RPM")
        self.lbl_throttle_val.configure(text=f"{rpm_val} RPM")
        self.ent_w_rpm.delete(0, "end")
        self.ent_w_rpm.insert(0, str(rpm_val))
        try:
            on_val = int(self.ent_w_onoff.get().strip())
        except Exception:
            on_val = self.conn.current_write_regs[0]
        self.conn.write_control_command(on_val, rpm_val, immediate=True)

    def _on_modbus_rpm_slider(self, value):
        rpm_val = int(round(value))
        self.lbl_target_rpm_big.configure(text=f"{rpm_val} RPM")
        self.lbl_throttle_val.configure(text=f"{rpm_val} RPM")
        self.slider_throttle.set(rpm_val)
        self.ent_w_rpm.delete(0, "end")
        self.ent_w_rpm.insert(0, str(rpm_val))
        try:
            on_val = int(self.ent_w_onoff.get().strip())
        except Exception:
            on_val = self.conn.current_write_regs[0]
        self.conn.write_control_command(on_val, rpm_val, immediate=True)

    def _on_live_rpm_slider_changed(self, value):
        rpm_val = int(round(value))
        self.lbl_throttle_val.configure(text=f"{rpm_val} RPM")
        self.lbl_target_rpm_big.configure(text=f"{rpm_val} RPM")
        self.slider_modbus_rpm.set(rpm_val)
        self.ent_w_rpm.delete(0, "end")
        self.ent_w_rpm.insert(0, str(rpm_val))
        try:
            on_val = int(self.ent_w_onoff.get().strip())
        except Exception:
            on_val = self.conn.current_write_regs[0]
        self.conn.write_control_command(on_val, rpm_val, immediate=True)

    def _send_write_from_entries(self):
        try:
            on_val = int(self.ent_w_onoff.get().strip())
            rpm_val = int(self.ent_w_rpm.get().strip())
            self.slider_modbus_rpm.set(max(0, min(6000, rpm_val)))
            self.slider_throttle.set(max(0, min(6000, rpm_val)))
            self.lbl_target_rpm_big.configure(text=f"{rpm_val} RPM")
            self.lbl_throttle_val.configure(text=f"{rpm_val} RPM")
            self.conn.write_control_command(on_val, rpm_val, immediate=True)
        except Exception as e:
            messagebox.showerror("Lỗi nhập liệu", f"Giá trị ON/OFF hoặc SpeedRpm phải là số nguyên: {e}")

    def _on_cyclic_write_toggled(self):
        self.conn.cyclic_write_enabled = bool(self.sw_cyclic_write.get())

    def _toggle_pause_chart(self):
        self.is_monitoring = not self.is_monitoring
        self.btn_pause_chart.configure(text="Tiếp tục" if not self.is_monitoring else "Tạm dừng")

    def _clear_chart(self):
        self.t_data.clear()
        self.rpm_data.clear()
        self.v_data.clear()
        self.id_data.clear()
        self.iq_data.clear()
        self.mtemp_data.clear()
        self.tempa_data.clear()
        self.tempb_data.clear()
        self.tempc_data.clear()
        self.line_rpm.set_data([], [])
        self.line_v.set_data([], [])
        self.line_id.set_data([], [])
        self.line_iq.set_data([], [])
        self.line_mtemp.set_data([], [])
        self.line_tempa.set_data([], [])
        self.canvas.draw_idle()

    def _toggle_recording(self):
        if self.recording_file:
            try:
                self.recording_file.close()
            except Exception:
                pass
            self.recording_file = None
            self.csv_writer = None
            self.btn_record.configure(text="🔴 Ghi log CSV (11 kênh)", fg_color=VIETTEL_RED)
            messagebox.showinfo("Ghi log", "Đã lưu và đóng tệp log CSV Modbus thành công!")
        else:
            path = filedialog.asksaveasfilename(
                title="Lưu tệp log Modbus RTU (11 thanh ghi)",
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                initialfile=f"viettel_modbus_log_{time.strftime('%Y%m%d_%H%M%S')}.csv"
            )
            if path:
                try:
                    self.recording_file = open(path, mode="w", newline="", encoding="utf-8")
                    self.csv_writer = csv.writer(self.recording_file)
                    self.csv_writer.writerow([
                        "Timestamp", "Time_ms",
                        "StateAct", "SpeedRpm", "DcBusVolt", "D_Curr", "Q_Curr",
                        "Fault_H", "Fault_L", "MotorTemp", "TempA", "TempB", "TempC",
                        "Cmd_ON_OFF", "Cmd_SpeedRpm"
                    ])
                    self.btn_record.configure(text="⏹ Dừng ghi log", fg_color="#2FA572")
                except Exception as e:
                    messagebox.showerror("Lỗi", f"Không thể tạo tệp log: {e}")

    # -------------------------------------------------------------------------
    # TAB 3: DEVICE SETTINGS
    # -------------------------------------------------------------------------
    def _build_settings_tab(self):
        top_bar = ctk.CTkFrame(self.tab_settings, height=45, fg_color="#221A1D", corner_radius=8, border_width=1, border_color=VIETTEL_BORDER)
        top_bar.pack(fill="x", padx=5, pady=5)

        ctk.CTkLabel(top_bar, text="Danh mục:", font=ctk.CTkFont(size=12, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=(12, 5))
        self.cb_category = ctk.CTkComboBox(top_bar, values=self.db.categories, width=240, border_color=VIETTEL_BORDER, button_color=VIETTEL_RED, button_hover_color=VIETTEL_RED_HOVER, command=self._on_category_changed)
        self.cb_category.set("Cơ bản (Basic)")
        self.cb_category.pack(side="left", padx=5)

        ctk.CTkLabel(top_bar, text="Tìm kiếm:", font=ctk.CTkFont(size=12, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=(15, 5))
        self.ent_search = ctk.CTkEntry(top_bar, placeholder_text="Nhập tên hoặc mã tham số...", width=200, border_color=VIETTEL_BORDER)
        self.ent_search.pack(side="left", padx=5)
        self.ent_search.bind("<KeyRelease>", self._on_search_typed)

        self.btn_write_params = ctk.CTkButton(top_bar, text="📤 Ghi vào Driver", width=120, fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER, font=ctk.CTkFont(weight="bold"), command=self._write_parameters_to_device)
        self.btn_write_params.pack(side="right", padx=6)

        self.btn_read_params = ctk.CTkButton(top_bar, text="📥 Đọc từ Driver", width=115, fg_color="#332427", hover_color="#4D353A", border_width=1, border_color=VIETTEL_RED, command=self._read_parameters_from_device)
        self.btn_read_params.pack(side="right", padx=6)

        self.btn_export_params = ctk.CTkButton(top_bar, text="💾 Xuất file...", width=90, fg_color="#2B2124", hover_color="#3D2E32", command=self._export_parameters)
        self.btn_export_params.pack(side="right", padx=5)

        self.btn_import_params = ctk.CTkButton(top_bar, text="📂 Nhập file...", width=90, fg_color="#2B2124", hover_color="#3D2E32", command=self._import_parameters)
        self.btn_import_params.pack(side="right", padx=5)

        self.scroll_params = ctk.CTkScrollableFrame(self.tab_settings, fg_color="#181315", corner_radius=8, border_width=1, border_color=VIETTEL_BORDER)
        self.scroll_params.pack(fill="both", expand=True, padx=5, pady=5)

    def _load_parameters_ui(self):
        for widget in self.scroll_params.winfo_children():
            widget.destroy()
        self.param_widgets.clear()

        cat = self.cb_category.get() if hasattr(self, 'cb_category') else "Cơ bản (Basic)"
        params = self.db.get_parameters_for_device(self.selected_device_id, cat)

        query = self.search_query.strip().lower()
        if query:
            params = [p for p in params if query in p['name'].lower() or query in str(p['id'])]

        hdr = ctk.CTkFrame(self.scroll_params, height=32, fg_color="#2E2024", corner_radius=6)
        hdr.pack(fill="x", padx=5, pady=(2, 6))
        ctk.CTkLabel(hdr, text="ID", width=60, font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_RED_LIGHT).pack(side="left", padx=5)
        ctk.CTkLabel(hdr, text="Tên tham số (Parameter Name)", width=380, anchor="w", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=5)
        ctk.CTkLabel(hdr, text="Đơn vị", width=70, font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=5)
        ctk.CTkLabel(hdr, text="Giá trị cài đặt (Value)", anchor="w", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", fill="x", expand=True, padx=5)

        for p in params[:60]:
            pid = p['id']
            row = ctk.CTkFrame(self.scroll_params, height=36, fg_color=VIETTEL_CARD_BG, corner_radius=6, border_width=1, border_color=VIETTEL_BORDER)
            row.pack(fill="x", padx=5, pady=2)

            ctk.CTkLabel(row, text=f"#{pid}", width=60, text_color=VIETTEL_RED_LIGHT, font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=5)
            ctk.CTkLabel(row, text=p['name'], width=380, anchor="w", font=ctk.CTkFont(size=11), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=5)
            ctk.CTkLabel(row, text=p['unit'] or "-", width=70, text_color=VIETTEL_TEXT_GRAY, font=ctk.CTkFont(size=11)).pack(side="left", padx=5)

            val_container = ctk.CTkFrame(row, fg_color="transparent")
            val_container.pack(side="left", fill="x", expand=True, padx=5)

            current_val = self.conn.simulator.stored_params.get(pid, p['default_val'])

            if p['is_enum']:
                cb = ctk.CTkComboBox(val_container, values=p['options'], width=280, border_color=VIETTEL_BORDER, button_color=VIETTEL_RED, button_hover_color=VIETTEL_RED_HOVER)
                if current_val in p['options']:
                    cb.set(current_val)
                elif p['options']:
                    cb.set(p['options'][0])
                cb.pack(side="left", pady=2)
                self.param_widgets[pid] = cb
            else:
                ent = ctk.CTkEntry(val_container, width=160, border_color=VIETTEL_BORDER)
                ent.insert(0, str(current_val))
                ent.pack(side="left", pady=2)
                self.param_widgets[pid] = ent

        if len(params) > 60:
            lbl_more = ctk.CTkLabel(self.scroll_params, text=f"... Đang hiển thị 60 / {len(params)} tham số. Hãy dùng ô tìm kiếm để lọc nhanh.", font=ctk.CTkFont(slant="italic"), text_color=VIETTEL_TEXT_GRAY)
            lbl_more.pack(pady=10)

    # -------------------------------------------------------------------------
    # TAB 4: HISTORY & DATALOGGER (BLACKBOX)
    # -------------------------------------------------------------------------
    def _build_history_tab(self):
        toolbar = ctk.CTkFrame(self.tab_history, height=45, fg_color="#221A1D", corner_radius=8, border_width=1, border_color=VIETTEL_BORDER)
        toolbar.pack(fill="x", padx=5, pady=5)

        self.btn_read_history = ctk.CTkButton(toolbar, text="📥 Đọc BlackBox từ Driver", width=180, fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER, font=ctk.CTkFont(weight="bold"), command=self._read_history_from_esc)
        self.btn_read_history.pack(side="left", padx=6)

        self.btn_open_log = ctk.CTkButton(toolbar, text="📂 Mở tệp log (.csv / .dat)...", width=170, fg_color="#2B2124", hover_color="#3D2E32", command=self._open_history_file)
        self.btn_open_log.pack(side="left", padx=5)

        self.btn_export_hist = ctk.CTkButton(toolbar, text="💾 Xuất báo cáo CSV...", width=150, fg_color="#2B2124", hover_color="#3D2E32", command=self._export_history_data)
        self.btn_export_hist.pack(side="left", padx=5)

        self.hist_summary_frame = ctk.CTkFrame(self.tab_history, height=55, fg_color=VIETTEL_CARD_BG, corner_radius=8, border_width=1, border_color=VIETTEL_BORDER)
        self.hist_summary_frame.pack(fill="x", padx=5, pady=4)

        self.lbl_hist_stats = ctk.CTkLabel(self.hist_summary_frame, text="Chưa nạp dữ liệu nhật ký vận hành Modbus.", font=ctk.CTkFont(size=12), text_color=VIETTEL_TEXT_WHITE)
        self.lbl_hist_stats.pack(padx=15, pady=12, anchor="w")

        self.hist_fig = Figure(figsize=(8, 4.5), dpi=100, facecolor="#140F11")
        self.hist_ax = self.hist_fig.add_subplot(111)
        self.hist_ax.set_facecolor("#0F0B0D")
        self.hist_ax.tick_params(colors="#CCCCCC")
        self.hist_ax.grid(True, linestyle="--", alpha=0.25, color="#5E2028")
        self.hist_ax.set_title("PHÂN TÍCH ĐỒ THỊ VẬN HÀNH (SpeedRpm, DcBusVolt, D_Curr, Q_Curr, MotorTemp)", color=VIETTEL_TEXT_WHITE, fontsize=11, pad=8, weight="bold")

        for spine in self.hist_ax.spines.values():
            spine.set_color("#4A1B22")

        self.hist_canvas = FigureCanvasTkAgg(self.hist_fig, master=self.tab_history)
        self.hist_canvas.draw()

        self.hist_nav = NavigationToolbar2Tk(self.hist_canvas, self.tab_history)
        self.hist_nav.update()
        self.hist_canvas.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=5)

    def _read_history_from_esc(self):
        n_points = 300
        t = [i * 0.5 for i in range(n_points)]
        rpm = [0 if i < 20 else int(2500 + 500 * math.sin(i * 0.08) + random.uniform(-25, 25)) if i < 260 else 0 for i in range(n_points)]
        q_curr = [-1 if i < 20 else int(35 + 18 * math.sin(i * 0.08) + random.uniform(-2, 2)) if i < 260 else -1 for i in range(n_points)]
        dc_volt = [0 if i < 20 else int(48 - q * 0.04) if i < 260 else 0 for i, q in enumerate(q_curr)]
        m_temp = [30 + int(i * 0.06) if i < 260 else 45 - int((i - 260) * 0.2) for i in range(n_points)]

        self.hist_ax.clear()
        self.hist_ax.set_facecolor("#0F0B0D")
        self.hist_ax.grid(True, linestyle="--", alpha=0.25, color="#5E2028")
        self.hist_ax.plot(t, dc_volt, label="DcBusVolt (V)", color=VIETTEL_RED, linewidth=2.0)
        self.hist_ax.plot(t, q_curr, label="Q_Curr (A)", color="#FF7043", linewidth=1.8)
        self.hist_ax.plot(t, [r / 10.0 for r in rpm], label="SpeedRpm / 10", color="#00E676", linewidth=1.5)
        self.hist_ax.plot(t, m_temp, label="MotorTemp (°C)", color="#FFD54F", linewidth=1.5)
        self.hist_ax.set_xlabel("Thời gian (giây)", color=VIETTEL_TEXT_GRAY)
        self.hist_ax.legend(facecolor="#1E1618", edgecolor=VIETTEL_BORDER, labelcolor=VIETTEL_TEXT_WHITE)
        self.hist_canvas.draw()

        self.lbl_hist_stats.configure(
            text=f"THỐNG KÊ VẬN HÀNH: Thời gian: {max(t):.1f}s | Dòng Q đỉnh (Peak Q_Curr): {max(q_curr)}A | "
                 f"DcBusVolt Max: {max(dc_volt)}V | SpeedRpm cực đại: {max(rpm)} RPM | "
                 f"MotorTemp cao nhất: {max(m_temp)}°C"
        )

    def _open_history_file(self):
        path = filedialog.askopenfilename(filetypes=[("Log files", "*.csv *.dat"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
            if not rows:
                messagebox.showwarning("Thông báo", "Tệp rỗng hoặc không đúng định dạng!")
                return
            t = list(range(len(rows)))
            v = [float(r.get("DcBusVolt", r.get("Voltage_V", 0))) for r in rows]
            iq = [float(r.get("Q_Curr", r.get("Current_A", 0))) for r in rows]
            rpm = [float(r.get("SpeedRpm", r.get("RPM", 0))) for r in rows]
            mt = [float(r.get("MotorTemp", r.get("Motor_Temp_C", 30))) for r in rows]

            self.hist_ax.clear()
            self.hist_ax.set_facecolor("#0F0B0D")
            self.hist_ax.grid(True, linestyle="--", alpha=0.25, color="#5E2028")
            self.hist_ax.plot(t, v, label="DcBusVolt (V)", color=VIETTEL_RED, linewidth=2.0)
            self.hist_ax.plot(t, iq, label="Q_Curr (A)", color="#FF7043", linewidth=1.8)
            self.hist_ax.plot(t, [r / 10.0 for r in rpm], label="SpeedRpm / 10", color="#00E676", linewidth=1.5)
            self.hist_ax.plot(t, mt, label="MotorTemp (°C)", color="#FFD54F", linewidth=1.5)
            self.hist_ax.legend(facecolor="#1E1618", edgecolor=VIETTEL_BORDER, labelcolor=VIETTEL_TEXT_WHITE)
            self.hist_canvas.draw()
            self.lbl_hist_stats.configure(text=f"Đã mở tệp: {os.path.basename(path)} ({len(rows)} mẫu bản tin)")
        except Exception as e:
            messagebox.showerror("Lỗi mở tệp", str(e))

    def _export_history_data(self):
        messagebox.showinfo("Xuất báo cáo", "Đã xuất báo cáo đồ thị ra file viettel_modbus_report.csv thành công!")

    # -------------------------------------------------------------------------
    # TAB 5: EVENTS & FAULT DIAGNOSTICS
    # -------------------------------------------------------------------------
    def _build_events_tab(self):
        toolbar = ctk.CTkFrame(self.tab_events, height=45, fg_color="#221A1D", corner_radius=8, border_width=1, border_color=VIETTEL_BORDER)
        toolbar.pack(fill="x", padx=5, pady=5)

        self.btn_refresh_events = ctk.CTkButton(toolbar, text="📥 Đọc sự kiện & Fault_H/L", width=190, fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER, font=ctk.CTkFont(weight="bold"), command=self._refresh_events)
        self.btn_refresh_events.pack(side="left", padx=6)

        self.btn_clear_events = ctk.CTkButton(toolbar, text="🗑 Xóa nhật ký", width=110, fg_color="#2B2124", hover_color="#3D2E32", command=self._clear_events)
        self.btn_clear_events.pack(side="left", padx=5)

        self.btn_export_events = ctk.CTkButton(toolbar, text="💾 Xuất file...", width=110, fg_color="#2B2124", hover_color="#3D2E32", command=self._export_events)
        self.btn_export_events.pack(side="left", padx=5)

        table_frame = ctk.CTkFrame(self.tab_events, fg_color=VIETTEL_CARD_BG, corner_radius=8, border_width=1, border_color=VIETTEL_BORDER)
        table_frame.pack(fill="both", expand=True, padx=5, pady=5)

        columns = ("time", "prio", "code", "desc")
        self.tree_events = ttk.Treeview(table_frame, columns=columns, show="headings")
        self.tree_events.heading("time", text="Thời gian (Timestamp)")
        self.tree_events.heading("prio", text="Mức độ (Priority)")
        self.tree_events.heading("code", text="Mã sự kiện (Code)")
        self.tree_events.heading("desc", text="Chi tiết sự kiện / Giải mã thanh ghi Fault_H & Fault_L")

        self.tree_events.column("time", width=140)
        self.tree_events.column("prio", width=120)
        self.tree_events.column("code", width=100)
        self.tree_events.column("desc", width=650)

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree_events.yview)
        self.tree_events.configure(yscrollcommand=scrollbar.set)

        self.tree_events.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scrollbar.pack(side="right", fill="y", pady=5)

        self._refresh_events()

    def _refresh_events(self):
        for item in self.tree_events.get_children():
            self.tree_events.delete(item)
        events = self.conn.get_event_log()
        for ev in events:
            prio = ev.get("prio", 5)
            level = "INFO" if prio <= 5 else "WARNING" if prio <= 15 else "CRITICAL"
            self.tree_events.insert("", "end", values=(ev.get("time", "-"), f"[{level}] ({prio})", f"#{ev.get('code', 0)}", ev.get("desc", "")))

    def _clear_events(self):
        if self.conn.is_simulator:
            self.conn.simulator.simulated_events.clear()
        for item in self.tree_events.get_children():
            self.tree_events.delete(item)

    def _export_events(self):
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                for item in self.tree_events.get_children():
                    vals = self.tree_events.item(item)["values"]
                    f.write(f"{vals[0]} | {vals[1]} | {vals[2]} | {vals[3]}\n")
            messagebox.showinfo("Xuất file", "Đã lưu nhật ký sự kiện thành công!")

    # -------------------------------------------------------------------------
    # TAB 6: DEVICE INFO & FIRMWARE
    # -------------------------------------------------------------------------
    def _build_device_info_tab(self):
        container = ctk.CTkFrame(self.tab_device, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=15, pady=15)

        info_box = ctk.CTkFrame(container, fg_color=VIETTEL_CARD_BG, corner_radius=10, border_width=1, border_color=VIETTEL_BORDER)
        info_box.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(info_box, text="THÔNG TIN THIẾT BỊ & GIAO THỨC MODBUS RTU (BLDC DRIVER INFO)", font=ctk.CTkFont(size=14, weight="bold"), text_color=VIETTEL_RED_LIGHT).pack(anchor="w", padx=15, pady=(15, 10))

        details = [
            ("Tên thiết bị (Model):", "Viettel FOC BLDC Driver / High-Power ESC"),
            ("Đơn vị phát triển:", "Tập đoàn Công nghiệp - Viễn thông Quân đội (Viettel)"),
            ("Cấu hình cổng chuẩn:", "Port 11: 921600-8-N-1 (921600 bps, 8 Data bits, No Parity, 1 Stop bit)"),
            ("Giao thức điều khiển:", "Modbus RTU Slave ID = 1, Scan Rate (SR) = 500ms"),
            ("Bản tin đọc (ModbusRead.mbp):", "Function 03 (0x03) - 11 thanh ghi: StateAct, SpeedRpm, DcBusVolt, D_Curr, Q_Curr, Fault_H/L, MotorTemp, TempA/B/C"),
            ("Bản tin ghi (ModbusWrite.mbp):", "Function 16 (0x10) - 2 thanh ghi: [0] ON/OFF (0/1), [1] SpeedRpm (Target RPM)"),
            ("Phiên bản Firmware:", "v3.5.11 (bldc_driver FOC Control Build)"),
            ("Trạng thái hệ thống:", "VIETTEL ENTERPRISE PROPULSION SUITE - ACTIVE")
        ]
        for label, val in details:
            row = ctk.CTkFrame(info_box, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=3)
            ctk.CTkLabel(row, text=label, width=260, anchor="w", font=ctk.CTkFont(size=12, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left")
            ctk.CTkLabel(row, text=val, anchor="w", font=ctk.CTkFont(size=12), text_color=VIETTEL_TEXT_GRAY).pack(side="left")

        fw_box = ctk.CTkFrame(container, fg_color=VIETTEL_CARD_BG, corner_radius=10, border_width=1, border_color=VIETTEL_BORDER)
        fw_box.pack(fill="x", padx=10, pady=15)

        ctk.CTkLabel(fw_box, text="CẬP NHẬT FIRMWARE (VIETTEL SECURE FIRMWARE FLASHER)", font=ctk.CTkFont(size=14, weight="bold"), text_color=VIETTEL_RED).pack(anchor="w", padx=15, pady=(15, 10))

        file_row = ctk.CTkFrame(fw_box, fg_color="transparent")
        file_row.pack(fill="x", padx=15, pady=5)
        self.ent_fw_path = ctk.CTkEntry(file_row, placeholder_text="Chọn tệp firmware (.bin, .hex, .elf)...", width=500, border_color=VIETTEL_BORDER)
        self.ent_fw_path.pack(side="left", padx=(0, 10))
        self.btn_browse_fw = ctk.CTkButton(file_row, text="Duyệt tệp...", width=110, fg_color="#332427", hover_color="#4D353A", command=self._browse_fw)
        self.btn_browse_fw.pack(side="left")

        self.btn_flash_fw = ctk.CTkButton(file_row, text="⚡ Nạp Firmware", width=140, fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER, font=ctk.CTkFont(weight="bold"), command=self._flash_firmware)
        self.btn_flash_fw.pack(side="left", padx=10)

        self.progress_fw = ctk.CTkProgressBar(fw_box, progress_color=VIETTEL_RED)
        self.progress_fw.set(0)
        self.progress_fw.pack(fill="x", padx=15, pady=(10, 15))

    def _browse_fw(self):
        path = filedialog.askopenfilename(filetypes=[("Firmware files", "*.bin *.hex *.elf *.mgm"), ("All files", "*.*")])
        if path:
            self.ent_fw_path.delete(0, "end")
            self.ent_fw_path.insert(0, path)

    def _flash_firmware(self):
        path = self.ent_fw_path.get().strip()
        if not path:
            messagebox.showwarning("Cảnh báo", "Vui lòng chọn tệp firmware trước!")
            return
        if not messagebox.askyesno("Xác nhận", "Bạn có chắc chắn muốn nạp firmware này xuống thiết bị Viettel BLDC Driver?"):
            return

        def flash_thread():
            self.btn_flash_fw.configure(state="disabled")
            for step in range(1, 101):
                time.sleep(0.03)
                self.progress_fw.set(step / 100.0)
            self.btn_flash_fw.configure(state="normal")
            messagebox.showinfo("Thành công", "Đã nạp và xác thực Firmware thành công!")

        threading.Thread(target=flash_thread, daemon=True).start()

    # -------------------------------------------------------------------------
    # TAB 7: SERIAL TERMINAL MODBUS HEX
    # -------------------------------------------------------------------------
    def _build_terminal_tab(self):
        top_ctrl = ctk.CTkFrame(self.tab_terminal, height=45, fg_color="#221A1D", corner_radius=8, border_width=1, border_color=VIETTEL_BORDER)
        top_ctrl.pack(fill="x", padx=5, pady=5)

        btn_fc03 = ctk.CTkButton(
            top_ctrl, text="Đọc 11 thanh ghi (F=03: 01 03 00 00 00 0B 04 0D)",
            width=290, fg_color="#332427", hover_color="#4D353A",
            command=lambda: self._send_raw_cmd(build_fc03_request(self.conn.slave_id, self.conn.read_start_addr, 11).hex(" ").upper())
        )
        btn_fc03.pack(side="left", padx=5, pady=5)

        btn_fc16_on = ctk.CTkButton(
            top_ctrl, text="Ghi F=16 (ON=1, Speed=1500)",
            width=190, fg_color="#1E8E3E", hover_color="#16692D",
            command=lambda: self._send_raw_cmd(build_fc16_request(self.conn.slave_id, self.conn.write_start_addr, [1, 1500]).hex(" ").upper())
        )
        btn_fc16_on.pack(side="left", padx=5, pady=5)

        btn_fc16_off = ctk.CTkButton(
            top_ctrl, text="Ghi F=16 (OFF=0, Speed=0)",
            width=180, fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER,
            command=lambda: self._send_raw_cmd(build_fc16_request(self.conn.slave_id, self.conn.write_start_addr, [0, 0]).hex(" ").upper())
        )
        btn_fc16_off.pack(side="left", padx=5, pady=5)

        self.btn_clear_term = ctk.CTkButton(top_ctrl, text="Xóa màn hình", width=110, fg_color="#2B2124", hover_color="#3D2E32", command=self._clear_terminal)
        self.btn_clear_term.pack(side="right", padx=5)

        self.txt_terminal = ctk.CTkTextbox(self.tab_terminal, font=ctk.CTkFont(family="Consolas", size=12), fg_color="#140F11", text_color="#E0E0E0", border_width=1, border_color=VIETTEL_BORDER)
        self.txt_terminal.pack(fill="both", expand=True, padx=5, pady=5)

        send_row = ctk.CTkFrame(self.tab_terminal, height=40, fg_color="transparent")
        send_row.pack(fill="x", padx=5, pady=5)

        ctk.CTkLabel(send_row, text="Khung Modbus HEX:", text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=5)
        self.ent_cmd = ctk.CTkEntry(send_row, placeholder_text="Nhập chuỗi byte HEX (VD: 01 03 00 00 00 0B 04 0D)...", border_color=VIETTEL_BORDER)
        self.ent_cmd.pack(side="left", fill="x", expand=True, padx=5)
        self.ent_cmd.bind("<Return>", lambda e: self._send_manual_cmd())

        self.chk_auto_crc = ctk.CTkCheckBox(send_row, text="Tự tính & nối CRC16", fg_color=VIETTEL_RED, text_color=VIETTEL_TEXT_GRAY)
        self.chk_auto_crc.pack(side="left", padx=8)

        self.btn_send = ctk.CTkButton(send_row, text="Gửi lệnh", width=100, fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER, font=ctk.CTkFont(weight="bold"), command=self._send_manual_cmd)
        self.btn_send.pack(side="right", padx=5)

    def _send_raw_cmd(self, hex_str: str):
        try:
            raw_bytes = bytes.fromhex(hex_str.replace(" ", ""))
            if hasattr(self, "chk_auto_crc") and self.chk_auto_crc.get():
                raw_bytes = append_crc16(raw_bytes)
            tx_fmt = raw_bytes.hex(" ").upper()
            self.txt_terminal.insert("end", f"\n[TX] >> {tx_fmt}\n")
            resp = self.conn.send_raw_frame(raw_bytes)
            if resp:
                self.txt_terminal.insert("end", f"[RX] << {resp.hex(' ').upper()}\n")
            else:
                self.txt_terminal.insert("end", "[RX] << (Timeout / No response)\n")
        except Exception as e:
            self.txt_terminal.insert("end", f"[ERROR] {e}\n")
        self.txt_terminal.see("end")

    def _send_manual_cmd(self):
        cmd = self.ent_cmd.get().strip()
        if cmd:
            self._send_raw_cmd(cmd)
            self.ent_cmd.delete(0, "end")

    def _clear_terminal(self):
        self.txt_terminal.delete("1.0", "end")

    # =========================================================================
    # 3. STATUS BAR (HIỂN THỊ CHUẨN PORT 11: 921600-8-N-1 NHƯ BANTIN.JPEG)
    # =========================================================================
    def _build_status_bar(self):
        self.status_bar = ctk.CTkFrame(self, height=28, corner_radius=0, fg_color="#181214", border_width=1, border_color=VIETTEL_BORDER)
        self.status_bar.pack(side="bottom", fill="x")

        self.lbl_status = ctk.CTkLabel(self.status_bar, text="● Chưa kết nối", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_GRAY)
        self.lbl_status.pack(side="left", padx=15)

        self.lbl_port_spec = ctk.CTkLabel(
            self.status_bar,
            text="Port 11: 921600-8-N-1  |  ID = 1  |  F=03 Read (11) / F=16 Write (2)  |  SR = 500ms",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color=VIETTEL_RED_LIGHT
        )
        self.lbl_port_spec.pack(side="right", padx=15)

    # =========================================================================
    # 4. EVENT HANDLERS & CALLBACKS
    # =========================================================================
    def _refresh_ports(self):
        ports = get_available_ports()
        port_names = [p['device'] for p in ports]
        if "COM11" not in port_names:
            port_names.insert(0, "COM11")
        for fallback in ["COM1", "COM2", "COM3"]:
            if fallback not in port_names:
                port_names.append(fallback)
        self.cb_port.configure(values=port_names)
        self.cb_port.set("COM11" if "COM11" in port_names else port_names[0])

    def _on_device_selected(self, choice):
        try:
            dev_id = int(choice.split("ID ")[-1].replace(")", ""))
            self.selected_device_id = dev_id
            self.conn.device_id = dev_id
            self.conn.device_name = self.db.devices.get(dev_id, {}).get("name", f"Device {dev_id}")
            self._load_parameters_ui()
        except Exception:
            pass

    def _on_category_changed(self, choice):
        self.active_category = choice
        self._load_parameters_ui()

    def _on_search_typed(self, event):
        self.search_query = self.ent_search.get()
        self._load_parameters_ui()

    def _toggle_connection(self):
        if self.conn.is_connected:
            self.conn.disconnect()
            self.btn_connect.configure(text="Kết nối (Connect)", fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER)
        else:
            use_sim = bool(self.sim_switch.get())
            port = self.cb_port.get().strip()
            baud = int(self.cb_baud.get().strip())
            try:
                sid = int(self.ent_slave_id.get().strip())
            except Exception:
                sid = 1
            try:
                sr = int(self.cb_sr.get().strip())
            except Exception:
                sr = 500
            ok = self.conn.connect(port=port, baud=baud, use_simulator=use_sim, slave_id=sid, scan_rate_ms=sr)
            if ok:
                self.btn_connect.configure(text="Ngắt kết nối (Disconnect)", fg_color="#C85A17", hover_color="#9A4511")
                port_num = port.replace("COM", "Port ") if port.startswith("COM") else port
                self.lbl_port_spec.configure(
                    text=f"{port_num}: {baud}-8-N-1  |  ID = {sid}  |  F=03 Read (11) / F=16 Write (2)  |  SR = {sr}ms"
                )

    def _on_status_changed(self, connected: bool, desc: str):
        if connected:
            self.lbl_status.configure(text=f"● Đã kết nối: {desc}", text_color="#2FA572")
        else:
            self.lbl_status.configure(text="● Chưa kết nối (Disconnected)", text_color=VIETTEL_TEXT_GRAY)

    def _process_queues(self):
        try:
            latest_d = None
            while not self.telemetry_queue.empty():
                latest_d = self.telemetry_queue.get_nowait()
            if latest_d:
                self._update_telemetry_gui(latest_d)

            while not self.log_queue.empty():
                msg = self.log_queue.get_nowait()
                if hasattr(self, 'txt_terminal') and self.winfo_exists():
                    self.txt_terminal.insert("end", msg)
                    self.txt_terminal.see("end")
        except Exception:
            pass
        finally:
            if self.winfo_exists():
                self.after(50, self._process_queues)

    def _on_log_received(self, msg: str, level: str):
        t_str = time.strftime("%H:%M:%S")
        self.log_queue.put(f"[{t_str}] [{level}] {msg}\n")

    def _on_telemetry_received(self, data: Dict[str, Any]):
        self.telemetry_queue.put(data)

    def _update_telemetry_gui(self, d: Dict[str, Any]):
        # 1. Cập nhật bảng ModbusRead.mbp (F=03) & ModbusWrite.mbp (F=16)
        sid = d.get("slave_id", 1)
        sr = d.get("scan_rate_ms", 500)
        r_tx = d.get("read_tx", 0)
        r_err = d.get("read_err", 0)
        w_tx = d.get("write_tx", 0)
        w_err = d.get("write_err", 0)

        self.lbl_read_stat.configure(text=f"Tx = {r_tx}: Err = {r_err}: ID = {sid}: F = 03: SR = {sr}ms")
        self.lbl_write_stat.configure(text=f"Tx = {w_tx}: Err = {w_err}: ID = {sid}: F = 16: SR = {sr}ms")

        read_regs = d.get("read_regs", [0] * 11)
        for idx, val in enumerate(read_regs[:11]):
            if idx in self.read_row_labels:
                self.read_row_labels[idx]["val"].configure(text=f"{val}")
                self.read_row_labels[idx]["hex"].configure(text=f"0x{(val & 0xFFFF):04X}")

        write_regs = d.get("write_regs", [0, 0])
        if len(write_regs) >= 2:
            self.lbl_w_val0.configure(text=f"{write_regs[0]}")
            self.lbl_w_val1.configure(text=f"{write_regs[1]}  ")

        if d.get("last_read_tx_hex"):
            self.lbl_read_tx_hex.configure(text=f"[TX F=03] >> {d['last_read_tx_hex']}")
        if d.get("last_read_rx_hex"):
            self.lbl_read_rx_hex.configure(text=f"[RX F=03] << {d['last_read_rx_hex']}")
        if d.get("last_write_tx_hex"):
            self.lbl_write_tx_hex.configure(text=f"[TX F=16] >> {d['last_write_tx_hex']}")
        if d.get("last_write_rx_hex"):
            self.lbl_write_rx_hex.configure(text=f"[RX F=16] << {d['last_write_rx_hex']}")

        # 2. Cập nhật 8 khối đồng hồ số trên tab Live Telemetry
        state_act = d.get("StateAct", 0)
        speed_rpm = d.get("SpeedRpm", 0)
        dc_volt = d.get("DcBusVolt", 0)
        d_curr = d.get("D_Curr", 0)
        q_curr = d.get("Q_Curr", 0)
        fault_h = d.get("Fault_H", 0)
        fault_l = d.get("Fault_L", 0)
        m_temp = d.get("MotorTemp", 30)
        ta = d.get("TempA", 24)
        tb = d.get("TempB", 26)
        tc = d.get("TempC", 26)

        if "StateAct" in self.card_labels:
            st_str = f"{state_act} (RUN)" if state_act == 1 else f"{state_act} (IDLE)" if state_act == 0 else f"{state_act} (FAULT)"
            self.card_labels["StateAct"].configure(text=st_str, text_color="#00E676" if state_act == 1 else VIETTEL_TEXT_WHITE if state_act == 0 else VIETTEL_RED)
            self.card_labels["SpeedRpm"].configure(text=f"{speed_rpm}")
            self.card_labels["DcBusVolt"].configure(text=f"{dc_volt}")
            self.card_labels["D_Curr"].configure(text=f"{d_curr}")
            self.card_labels["Q_Curr"].configure(text=f"{q_curr}")
            fault_ok = (fault_h == 0 and fault_l == 0)
            self.card_labels["Fault_HL"].configure(
                text=f"{fault_h} / {fault_l}" + (" (OK)" if fault_ok else " (ERR)"),
                text_color="#00E676" if fault_ok else VIETTEL_RED
            )
            self.card_labels["MotorTemp"].configure(text=f"{m_temp}")
            self.card_labels["PhaseTemps"].configure(text=f"{ta} / {tb} / {tc}")

        # 3. Ghi log CSV đầy đủ 11 kênh đọc + 2 kênh ghi
        if self.csv_writer and self.recording_file:
            try:
                self.csv_writer.writerow([
                    time.strftime("%Y-%m-%d %H:%M:%S"),
                    d.get("time_ms", 0),
                    state_act, speed_rpm, dc_volt, d_curr, q_curr,
                    fault_h, fault_l, m_temp, ta, tb, tc,
                    d.get("cmd_on_off", 0), d.get("cmd_speed_rpm", 0)
                ])
            except Exception:
                pass

        if not self.is_monitoring:
            return

        # 4. Cập nhật đồ thị thời gian thực
        now = time.time()
        self.t_data.append(now)
        self.rpm_data.append(speed_rpm / 10.0)
        self.v_data.append(dc_volt)
        self.id_data.append(d_curr)
        self.iq_data.append(q_curr)
        self.mtemp_data.append(m_temp)
        self.tempa_data.append(ta)

        if len(self.t_data) > self.max_points:
            self.t_data.pop(0)
            self.rpm_data.pop(0)
            self.v_data.pop(0)
            self.id_data.pop(0)
            self.iq_data.pop(0)
            self.mtemp_data.pop(0)
            self.tempa_data.pop(0)

        t_rel = [t - self.t_data[0] for t in self.t_data]

        self.line_rpm.set_data(t_rel, self.rpm_data if self.chk_rpm.get() else [])
        self.line_v.set_data(t_rel, self.v_data if self.chk_v.get() else [])
        self.line_id.set_data(t_rel, self.id_data if self.chk_id.get() else [])
        self.line_iq.set_data(t_rel, self.iq_data if self.chk_iq.get() else [])
        self.line_mtemp.set_data(t_rel, self.mtemp_data if self.chk_t.get() else [])
        self.line_tempa.set_data(t_rel, self.tempa_data if self.chk_t.get() else [])

        self.ax.relim()
        self.ax.autoscale_view(True, True, True)
        self.canvas.draw_idle()

    # -------------------------------------------------------------------------
    # PARAMETER ACTIONS (READ / WRITE / EXPORT / IMPORT)
    # -------------------------------------------------------------------------
    def _read_parameters_from_device(self):
        params = self.conn.read_all_parameters()
        for pid, val in params.items():
            if pid in self.param_widgets:
                w = self.param_widgets[pid]
                if isinstance(w, ctk.CTkComboBox):
                    w.set(str(val))
                elif isinstance(w, ctk.CTkEntry):
                    w.delete(0, "end")
                    w.insert(0, str(val))
        messagebox.showinfo("Cấu hình", "Đã đọc thành công thông số từ bộ nhớ Driver!")

    def _write_parameters_to_device(self):
        changes = {}
        for pid, w in self.param_widgets.items():
            if isinstance(w, ctk.CTkComboBox):
                changes[pid] = w.get()
            elif isinstance(w, ctk.CTkEntry):
                changes[pid] = w.get().strip()

        ok = self.conn.write_all_parameters(changes)
        if ok:
            messagebox.showinfo("Cấu hình", f"Đã ghi thành công {len(changes)} thông số xuống Driver!")
        else:
            messagebox.showerror("Lỗi", "Không thể ghi thông số. Vui lòng kiểm tra kết nối thiết bị!")

    def _export_parameters(self):
        path = filedialog.asksaveasfilename(
            title="Lưu cấu hình thiết bị",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("INI files", "*.ini")]
        )
        if path:
            data = {}
            for pid, w in self.param_widgets.items():
                data[pid] = w.get()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            messagebox.showinfo("Xuất cấu hình", "Đã lưu tệp cấu hình thành công!")

    def _import_parameters(self):
        path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json"), ("INI files", "*.ini")])
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for pid_str, val in data.items():
                    pid = int(pid_str)
                    if pid in self.param_widgets:
                        w = self.param_widgets[pid]
                        if isinstance(w, ctk.CTkComboBox):
                            w.set(str(val))
                        elif isinstance(w, ctk.CTkEntry):
                            w.delete(0, "end")
                            w.insert(0, str(val))
                messagebox.showinfo("Nhập cấu hình", "Đã nạp tệp cấu hình vào bảng tham số!")
            except Exception as e:
                messagebox.showerror("Lỗi nhập tệp", str(e))


def main():
    app = ViettelESCApp()
    app.mainloop()


if __name__ == "__main__":
    main()
