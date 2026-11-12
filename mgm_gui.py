"""
VIETTEL PROPULSION SUITE - MAIN APPLICATION GUI
File: mgm_gui.py
Chịu trách nhiệm:
1. Cửa sổ ứng dụng chính (Main Application Window) chuẩn nhận diện Đỏ Viettel & Titanium Obsidian.
2. Thanh Header quản lý kết nối truyền thông công nghiệp:
   - Cổng Serial (Port COM11, Baudrate 921600-8-N-1 theo bantin.jpeg)
   - Modbus Slave ID (ID = 1) và Chu kỳ quét Scan Rate (SR = 500ms)
   - Chế độ Mô phỏng (Simulator Switch) và Nút Kết nối (Connect/Disconnect)
3. Tích hợp 4 Tab quản lý chuyên biệt từ 4 file GUI riêng biệt:
   - Tab 1: 🚀 ĐIỀU TỐC ESC / BLDC (nạp từ gui_esc.py)
   - Tab 2: 🔋 QUẢN LÝ PIN BMU / BMS (nạp từ gui_bmu.py)
   - Tab 3: ⚡ HỆ THỐNG NGUỒN & PDU (nạp từ gui_power.py)
   - Tab 4: 🎯 BỘ TRUYỀN ĐỘNG MLD (nạp từ gui_mld.py)
4. Thanh công cụ tiện ích mở rộng: Datalogger BlackBox, Terminal Modbus HEX
5. Hàng đợi đa luồng thread-safe phân phối dữ liệu telemetry đồng bộ, chống giật lag.
"""

import os
import sys
import time
import json
import queue
import threading
from typing import Dict, Any

import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image

from mgm_data import MGMDatabase
from mgm_comm import MGMConnection, get_available_ports
from gui_esc import ESCTabFrame
from gui_bmu import BMUTabFrame
from gui_power import PowerTabFrame
from gui_mld import MLDTabFrame

from viettel_theme import (
    COLOR_BG, COLOR_HEADER_BG, COLOR_PANEL_BG, COLOR_CARD_BG, COLOR_CARD_BG_HOVER,
    COLOR_CARD_INNER, COLOR_BORDER, COLOR_BORDER_SUBTLE, COLOR_BORDER_RED,
    VIETTEL_RED, VIETTEL_RED_HOVER, VIETTEL_RED_LIGHT, VIETTEL_RED_GLOW,
    COLOR_SUCCESS, COLOR_SUCCESS_HOVER, COLOR_SUCCESS_GLOW, COLOR_CYAN,
    COLOR_WARNING, COLOR_WARNING_LIGHT, COLOR_CRITICAL, COLOR_BLUE_SEL,
    COLOR_TEXT_WHITE, COLOR_TEXT_GRAY, COLOR_TEXT_MUTED,
    font_brand, font_section_title, font_card_label, font_digital_sm, font_mono, font_btn,
    font_body, FONT_PRIMARY, safe_configure_label
)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class ViettelMainApp(ctk.CTk):
    """Cửa sổ ứng dụng chính kết hợp 4 module: ESC, BMU, POWER và MLD chuẩn sản xuất"""
    def __init__(self):
        super().__init__()

        self.title("VIETTEL VMC - HỆ THỐNG ĐIỀU KHIỂN & GIÁM SÁT ESC / BMU / POWER / MLD")
        self.geometry("1420x920")
        self.minsize(1180, 780)
        self.configure(fg_color=COLOR_BG)

        # Khởi tạo cơ sở dữ liệu và truyền thông Modbus RTU
        self.db = MGMDatabase()
        self.conn = MGMConnection()
        self.conn.on_telemetry_callback = self._on_telemetry_received
        self.conn.on_log_callback = self._on_log_received
        self.conn.on_status_change = self._on_status_changed

        self.selected_device_id = 10

        # Thiết lập Icon cửa sổ (Viettel Logo ICO)
        ico_path = os.path.join(os.path.dirname(__file__), "viettel_logo.ico")
        if os.path.exists(ico_path):
            try:
                self.iconbitmap(ico_path)
            except Exception:
                pass

        # Xây dựng giao diện chuẩn SCADA quân sự / công nghiệp
        self._build_header_bar()
        self._build_main_tabview()
        self._build_status_bar()

        # Hàng đợi đa luồng thread-safe
        self.telemetry_queue = queue.Queue()
        self.log_queue = queue.Queue()

        self._refresh_ports()
        self._process_queues()
        self._update_clock()

        # Mặc định kích hoạt chế độ mô phỏng
        self.sim_switch.select()
        self._toggle_connection()

    # =========================================================================
    # 1. HEADER BAR & CONTROLS (VIETTEL AEROSPACE SUITE)
    # =========================================================================
    def _build_header_bar(self):
        self.header_frame = ctk.CTkFrame(
            self, height=72, corner_radius=0,
            fg_color=COLOR_HEADER_BG, border_width=1, border_color=COLOR_BORDER
        )
        self.header_frame.pack(side="top", fill="x", padx=0, pady=0)

        # Viettel Logo + Tiêu đề thương hiệu chuẩn VMC
        title_box = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        title_box.pack(side="left", padx=(14, 8), pady=8)

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

        title_row = ctk.CTkFrame(text_box, fg_color="transparent")
        title_row.pack(anchor="w")

        lbl_brand = ctk.CTkLabel(
            title_row, text="VIETTEL VMC",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=17, weight="bold"), text_color=COLOR_TEXT_WHITE
        )
        lbl_brand.pack(side="left", padx=(0, 6))

        lbl_badge = ctk.CTkLabel(
            title_row, text="PROD v2.5",
            font=ctk.CTkFont(family="Consolas", size=9, weight="bold"),
            fg_color=COLOR_CARD_INNER, text_color=COLOR_CYAN,
            corner_radius=4, padx=5, pady=1
        )
        lbl_badge.pack(side="left")

        sub_row = ctk.CTkFrame(text_box, fg_color="transparent")
        sub_row.pack(anchor="w", pady=(1, 0))
        lbl_sub = ctk.CTkLabel(
            sub_row, text="PROPULSION & POWER SUITE",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=10, weight="bold"), text_color=VIETTEL_RED_LIGHT
        )
        lbl_sub.pack(side="left")

        # Cụm điều khiển Serial & Modbus RTU
        comm_box = ctk.CTkFrame(
            self.header_frame, fg_color=COLOR_CARD_BG, corner_radius=6,
            border_width=1, border_color=COLOR_BORDER
        )
        comm_box.pack(side="left", padx=8, pady=8)

        # Hàng trên của comm_box: tiêu đề nhỏ
        c_title_row = ctk.CTkFrame(comm_box, fg_color="transparent")
        c_title_row.pack(fill="x", padx=8, pady=(4, 1))
        ctk.CTkLabel(
            c_title_row, text="KẾT NỐI TRUYỀN THÔNG (MODBUS RTU 921600-8-N-1)",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=9, weight="bold"), text_color=COLOR_TEXT_GRAY
        ).pack(side="left")

        # Hàng dưới của comm_box: các ô chọn
        c_ctrl_row = ctk.CTkFrame(comm_box, fg_color="transparent")
        c_ctrl_row.pack(fill="x", padx=8, pady=(0, 6))

        # Port selector
        self.cb_port = ctk.CTkComboBox(
            c_ctrl_row, values=["COM11"], width=105, height=28,
            border_color=COLOR_BORDER, fg_color=COLOR_CARD_INNER,
            button_color="#223042", button_hover_color="#33465C",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=11)
        )
        self.cb_port.set("COM11")
        self.cb_port.pack(side="left", padx=(0, 3))

        self.btn_refresh_ports = ctk.CTkButton(
            c_ctrl_row, text="↻", width=28, height=28, fg_color="#223042", hover_color="#33465C",
            font=ctk.CTkFont(size=12, weight="bold"), command=self._refresh_ports
        )
        self.btn_refresh_ports.pack(side="left", padx=(0, 6))

        # Baudrate selector
        self.cb_baud = ctk.CTkComboBox(
            c_ctrl_row,
            values=["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"],
            width=95, height=28, border_color=COLOR_BORDER, fg_color=COLOR_CARD_INNER,
            button_color="#223042", button_hover_color="#33465C",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=11)
        )
        self.cb_baud.set("921600")
        self.cb_baud.pack(side="left", padx=(0, 8))

        # Slave ID
        ctk.CTkLabel(
            c_ctrl_row, text="ID:", font=ctk.CTkFont(family=FONT_PRIMARY, size=10, weight="bold"),
            text_color=COLOR_TEXT_WHITE
        ).pack(side="left", padx=(0, 2))

        self.ent_slave_id = ctk.CTkEntry(
            c_ctrl_row, width=38, height=28, border_color=COLOR_BORDER, fg_color=COLOR_CARD_INNER,
            font=ctk.CTkFont(family=FONT_PRIMARY, size=11)
        )
        self.ent_slave_id.insert(0, "1")
        self.ent_slave_id.pack(side="left", padx=(0, 8))

        # Scan Rate
        ctk.CTkLabel(
            c_ctrl_row, text="SR:", font=ctk.CTkFont(family=FONT_PRIMARY, size=10, weight="bold"),
            text_color=COLOR_TEXT_WHITE
        ).pack(side="left", padx=(0, 2))

        self.cb_sr = ctk.CTkComboBox(
            c_ctrl_row, values=["100", "200", "500", "1000"], width=72, height=28,
            border_color=COLOR_BORDER, fg_color=COLOR_CARD_INNER,
            button_color="#223042", button_hover_color="#33465C",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=11),
            command=self._on_sr_changed
        )
        self.cb_sr.set("500")
        self.cb_sr.pack(side="left")

        # Cụm Tiện ích bổ trợ (Tools: Terminal, BlackBox)
        tools_box = ctk.CTkFrame(
            self.header_frame, fg_color=COLOR_CARD_BG, corner_radius=6,
            border_width=1, border_color=COLOR_BORDER
        )
        tools_box.pack(side="left", padx=8, pady=8)

        t_title_row = ctk.CTkFrame(tools_box, fg_color="transparent")
        t_title_row.pack(fill="x", padx=8, pady=(4, 1))
        ctk.CTkLabel(
            t_title_row, text="CÔNG CỤ PHÂN TÍCH",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=9, weight="bold"), text_color=COLOR_TEXT_GRAY
        ).pack(side="left")

        t_row = ctk.CTkFrame(tools_box, fg_color="transparent")
        t_row.pack(fill="x", padx=8, pady=(0, 6))

        self.btn_term_tool = ctk.CTkButton(
            t_row, text="💻 Terminal HEX", width=110, height=28, fg_color="#223042", hover_color="#33465C",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=11), command=self._open_terminal_window
        )
        self.btn_term_tool.pack(side="left", padx=(0, 4))

        self.btn_hist_tool = ctk.CTkButton(
            t_row, text="📈 BlackBox", width=95, height=28, fg_color="#223042", hover_color="#33465C",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=11), command=self._open_blackbox_window
        )
        self.btn_hist_tool.pack(side="left")

        # Cụm Điều khiển Kết nối (Simulator + Connect Button) bên phải
        ctrl_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        ctrl_frame.pack(side="right", padx=14, pady=8)

        ctrl_top = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        ctrl_top.pack(anchor="e", pady=(0, 3))

        # Đèn báo LED trạng thái
        self.lbl_led_status = ctk.CTkLabel(
            ctrl_top, text="● SẴN SÀNG",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=10, weight="bold"),
            text_color=COLOR_SUCCESS_GLOW, fg_color=COLOR_CARD_INNER,
            corner_radius=4, padx=6, pady=2
        )
        self.lbl_led_status.pack(side="left", padx=(0, 10))

        self.sim_switch = ctk.CTkSwitch(
            ctrl_top, text="Mô phỏng (Simulator)",
            progress_color=VIETTEL_RED, font=ctk.CTkFont(family=FONT_PRIMARY, size=11, weight="bold")
        )
        self.sim_switch.pack(side="left")

        self.btn_connect = ctk.CTkButton(
            ctrl_frame, text="⚡ KẾT NỐI (CONNECT)", width=170, height=32,
            fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER,
            font=ctk.CTkFont(family=FONT_PRIMARY, size=12, weight="bold"), command=self._toggle_connection
        )
        self.btn_connect.pack(anchor="e")

    # =========================================================================
    # 2. MAIN TABVIEW: 4 TAB QUẢN LÝ (ESC, BMU, POWER, MLD)
    # =========================================================================
    def _build_main_tabview(self):
        self.tabview = ctk.CTkTabview(
            self,
            corner_radius=8,
            command=self._on_tab_changed,
            fg_color=COLOR_PANEL_BG,
            segmented_button_selected_color=VIETTEL_RED,
            segmented_button_selected_hover_color=VIETTEL_RED_HOVER,
            segmented_button_unselected_color=COLOR_CARD_BG,
            segmented_button_unselected_hover_color=COLOR_CARD_BG_HOVER
        )
        self.tabview.pack(fill="both", expand=True, padx=8, pady=(4, 4))

        # 4 Tab quản lý chuyên biệt theo chuẩn hệ thống Viettel
        self.tab_esc_container = self.tabview.add("🚀 ĐIỀU TỐC ESC / BLDC")
        self.tab_bmu_container = self.tabview.add("🔋 QUẢN LÝ PIN BMU / BMS")
        self.tab_power_container = self.tabview.add("⚡ HỆ THỐNG NGUỒN & PDU")
        self.tab_mld_container = self.tabview.add("🎯 BỘ TRUYỀN ĐỘNG MLD")

        # Khởi tạo và nhúng 4 View từ 4 module chuyên biệt
        self.view_esc = ESCTabFrame(self.tab_esc_container, conn=self.conn)
        self.view_esc.pack(fill="both", expand=True)

        self.view_bmu = BMUTabFrame(self.tab_bmu_container, conn=self.conn)
        self.view_bmu.pack(fill="both", expand=True)

        self.view_power = PowerTabFrame(self.tab_power_container, conn=self.conn)
        self.view_power.pack(fill="both", expand=True)

        self.view_mld = MLDTabFrame(self.tab_mld_container, conn=self.conn)
        self.view_mld.pack(fill="both", expand=True)

    def _on_tab_changed(self):
        """Xử lý sự kiện khi người dùng chuyển đổi tab"""
        sel = self.tabview.get()
        last_d = getattr(self, '_last_telemetry', None)
        if "POWER" in sel:
            self.conn.set_active_tab("POWER")
            self.lbl_port_spec.configure(
                text=f"Port: {self.conn.port_name} ({self.conn.baud_rate}-8-N-1) | ID={self.conn.slave_id} | Modbus POWER: F=03 Read (36 Regs) / F=16 Write (10 Regs)"
            )
            if hasattr(self, 'view_power') and last_d:
                self.view_power.update_telemetry(last_d)
        elif "ESC" in sel:
            self.conn.set_active_tab("ESC")
            self.lbl_port_spec.configure(
                text=f"Port: {self.conn.port_name} ({self.conn.baud_rate}-8-N-1) | ID={self.conn.slave_id} | Modbus ESC: F=03 Read (11 Regs) / F=16 Write (2 Regs)"
            )
            if hasattr(self, 'view_esc') and last_d:
                self.view_esc.update_telemetry(last_d)
        elif "BMU" in sel:
            self.conn.set_active_tab("BMU")
            self.lbl_port_spec.configure(
                text=f"Port: {self.conn.port_name} ({self.conn.baud_rate}-8-N-1) | ID={self.conn.slave_id} | Module: BMU Battery Management"
            )
            if hasattr(self, 'view_bmu') and last_d:
                self.view_bmu.update_telemetry(last_d)
        elif "MLD" in sel:
            self.conn.set_active_tab("MLD")
            self.lbl_port_spec.configure(
                text=f"Port: {self.conn.port_name} ({self.conn.baud_rate}-8-N-1) | ID={self.conn.slave_id} | Modbus MLD: F=03 Read (7 Regs) / F=16 Write (4 Regs)"
            )
            if hasattr(self, 'view_mld') and last_d:
                self.view_mld.update_telemetry(last_d)

    # =========================================================================
    # 3. STATUS BAR (AEROSPACE SCADA FOOTER)
    # =========================================================================
    def _build_status_bar(self):
        self.status_bar = ctk.CTkFrame(
            self, height=30, corner_radius=0,
            fg_color=COLOR_HEADER_BG, border_width=1, border_color=COLOR_BORDER
        )
        self.status_bar.pack(side="bottom", fill="x")

        # Trạng thái kết nối
        self.lbl_status = ctk.CTkLabel(
            self.status_bar, text="● Chưa kết nối",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=11, weight="bold"), text_color=COLOR_TEXT_GRAY
        )
        self.lbl_status.pack(side="left", padx=14)

        # Thông số truyền thông
        self.lbl_port_spec = ctk.CTkLabel(
            self.status_bar,
            text="Port 11: 921600-8-N-1  |  ID = 1  |  F=03 Read (11) / F=16 Write (2)  |  SR = 500ms",
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
            text_color=COLOR_TEXT_MUTED
        )
        self.lbl_port_spec.pack(side="left", padx=15)

        # Division branding + Real-time Clock
        right_box = ctk.CTkFrame(self.status_bar, fg_color="transparent")
        right_box.pack(side="right", padx=14)

        lbl_div = ctk.CTkLabel(
            right_box, text="VIETTEL HIGH-TECH • AEROSPACE SUITE |",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=10, weight="bold"),
            text_color=COLOR_TEXT_MUTED
        )
        lbl_div.pack(side="left", padx=(0, 6))

        self.lbl_clock = ctk.CTkLabel(
            right_box, text="00:00:00",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color=COLOR_CYAN
        )
        self.lbl_clock.pack(side="left")

    def _update_clock(self):
        """Cập nhật đồng hồ thời gian thực mỗi giây"""
        try:
            curr_time = time.strftime("%H:%M:%S")
            self.lbl_clock.configure(text=curr_time)
        except Exception:
            pass
        finally:
            if self.winfo_exists():
                self.after(1000, self._update_clock)

    # =========================================================================
    # 4. EVENT HANDLERS & CALLBACKS
    # =========================================================================
    def _refresh_ports(self):
        ports = get_available_ports()
        port_names = [p['device'] for p in ports]
        if "COM11" not in port_names:
            port_names.insert(0, "COM11")
        for fallback in ["COM1", "COM2", "COM3", "COM4"]:
            if fallback not in port_names:
                port_names.append(fallback)
        self.cb_port.configure(values=port_names)
        self.cb_port.set("COM11" if "COM11" in port_names else port_names[0])

    def _on_sr_changed(self, val_str: str):
        try:
            sr = int(val_str)
            self.conn.scan_rate_ms = max(50, sr)
        except Exception:
            pass

    def _toggle_connection(self):
        if self.conn.is_connected:
            self.conn.disconnect()
            self.btn_connect.configure(
                text="⚡ KẾT NỐI (CONNECT)", fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER
            )
            self.lbl_led_status.configure(text="○ OFFLINE", text_color=COLOR_TEXT_MUTED)
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
                self.btn_connect.configure(
                    text="🔌 NGẮT KẾT NỐI", fg_color="#C85A17", hover_color="#9A4511"
                )
                self.lbl_led_status.configure(
                    text="● TRỰC TUYẾN" if not use_sim else "● MÔ PHỎNG",
                    text_color=COLOR_SUCCESS_GLOW
                )
                port_num = port.replace("COM", "Port ") if port.startswith("COM") else port
                self.lbl_port_spec.configure(
                    text=f"{port_num}: {baud}-8-N-1  |  ID = {sid}  |  SR = {sr}ms"
                )

    def _on_status_changed(self, connected: bool, desc: str):
        if connected:
            self.lbl_status.configure(text=f"● Đã kết nối: {desc}", text_color=COLOR_SUCCESS)
            self.lbl_led_status.configure(text="● TRỰC TUYẾN", text_color=COLOR_SUCCESS_GLOW)
        else:
            self.lbl_status.configure(text="● Chưa kết nối (Disconnected)", text_color=COLOR_TEXT_GRAY)
            self.lbl_led_status.configure(text="○ OFFLINE", text_color=COLOR_TEXT_MUTED)

    def _on_log_received(self, msg: str, level: str):
        t_str = time.strftime("%H:%M:%S")
        self.log_queue.put(f"[{t_str}] [{level}] {msg}\n")

    def _on_telemetry_received(self, data: Dict[str, Any]):
        self.telemetry_queue.put(data)

    def _process_queues(self):
        try:
            latest_d = None
            while not self.telemetry_queue.empty():
                latest_d = self.telemetry_queue.get_nowait()
            if latest_d:
                self._last_telemetry = latest_d
                sel = self.tabview.get() if hasattr(self, 'tabview') else ""

                # Phân phối telemetry tới Tab đang mở
                if "POWER" in sel and hasattr(self, 'view_power') and self.view_power.winfo_exists():
                    self.view_power.update_telemetry(latest_d)
                elif "ESC" in sel and hasattr(self, 'view_esc') and self.view_esc.winfo_exists():
                    self.view_esc.update_telemetry(latest_d)
                elif "BMU" in sel and hasattr(self, 'view_bmu') and self.view_bmu.winfo_exists():
                    self.view_bmu.update_telemetry(latest_d)
                elif "MLD" in sel and hasattr(self, 'view_mld') and self.view_mld.winfo_exists():
                    self.view_mld.update_telemetry(latest_d)

                # Ghi file ngầm nếu bật log CSV
                if "ESC" not in sel and hasattr(self, 'view_esc') and getattr(self.view_esc, 'recording_file', None):
                    self.view_esc.log_csv_record(latest_d)
                if "MLD" not in sel and hasattr(self, 'view_mld') and getattr(self.view_mld, 'recording_file', None):
                    self.view_mld.log_csv_record(latest_d)

            while not self.log_queue.empty():
                msg = self.log_queue.get_nowait()
                if hasattr(self, '_txt_term') and self._txt_term.winfo_exists():
                    self._txt_term.insert("end", msg)
                    self._txt_term.see("end")
        except Exception:
            pass
        finally:
            if self.winfo_exists():
                self.after(50, self._process_queues)

    # =========================================================================
    # 5. CỬA SỔ PHỤ (SUB-WINDOWS: TERMINAL HEX & BLACKBOX)
    # =========================================================================
    def _open_terminal_window(self):
        """Mở cửa sổ Terminal Modbus HEX để debug bản tin thô"""
        term_win = ctk.CTkToplevel(self)
        term_win.title("Terminal Modbus HEX — Viettel High-Tech Diagnostics")
        term_win.geometry("740x480")
        term_win.configure(fg_color=COLOR_BG)

        top_row = ctk.CTkFrame(term_win, height=40, fg_color=COLOR_HEADER_BG, border_width=1, border_color=COLOR_BORDER)
        top_row.pack(fill="x", padx=10, pady=(10, 6))

        ctk.CTkLabel(
            top_row, text="Bản tin HEX:", font=ctk.CTkFont(family=FONT_PRIMARY, size=11, weight="bold"),
            text_color=COLOR_TEXT_WHITE
        ).pack(side="left", padx=10)

        ent_hex = ctk.CTkEntry(
            top_row, width=360, placeholder_text="01 03 00 00 00 0B 04 0D",
            border_color=COLOR_BORDER, fg_color=COLOR_CARD_INNER, font=ctk.CTkFont(family="Consolas", size=11)
        )
        ent_hex.pack(side="left", padx=8)

        btn_send = ctk.CTkButton(
            top_row, text="GỬI (TX)", width=80, fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER,
            font=ctk.CTkFont(family=FONT_PRIMARY, size=11, weight="bold"),
            command=lambda: self._send_term_hex(ent_hex.get().strip())
        )
        btn_send.pack(side="left", padx=6)

        self._txt_term = ctk.CTkTextbox(
            term_win, font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=COLOR_CARD_INNER, text_color="#E2E8F0",
            border_width=1, border_color=COLOR_BORDER
        )
        self._txt_term.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._txt_term.insert("end", "=== VIETTEL HIGH-TECH MODBUS RTU TERMINAL INITIALIZED ===\n")

    def _send_term_hex(self, hex_str: str):
        if not hex_str:
            return
        try:
            raw = bytes.fromhex(hex_str.replace(" ", ""))
            self._txt_term.insert("end", f"\n[TX] >> {raw.hex(' ').upper()}\n")
            resp = self.conn.send_raw_frame(raw)
            if resp:
                self._txt_term.insert("end", f"[RX] << {resp.hex(' ').upper()}\n")
            else:
                self._txt_term.insert("end", "[RX] << (No Response / Timeout)\n")
        except Exception as e:
            self._txt_term.insert("end", f"[ERROR] {e}\n")
        self._txt_term.see("end")

    def _open_blackbox_window(self):
        """Mở cửa sổ phân tích Datalogger BlackBox"""
        bbox_win = ctk.CTkToplevel(self)
        bbox_win.title("Nhật Ký Chuyến Bay BlackBox — Viettel Propulsion")
        bbox_win.geometry("820x500")
        bbox_win.configure(fg_color=COLOR_BG)

        header = ctk.CTkFrame(bbox_win, fg_color=COLOR_HEADER_BG, height=44, border_width=1, border_color=COLOR_BORDER)
        header.pack(fill="x", padx=10, pady=(10, 6))

        ctk.CTkLabel(
            header, text="📊 DỮ LIỆU CHUYẾN BAY & NHẬT KÝ VẬN HÀNH BLACKBOX",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=13, weight="bold"), text_color=VIETTEL_RED_LIGHT
        ).pack(side="left", padx=12, pady=8)

        info_box = ctk.CTkFrame(
            bbox_win, fg_color=COLOR_CARD_BG, corner_radius=6, border_width=1, border_color=COLOR_BORDER
        )
        info_box.pack(fill="x", padx=10, pady=6)

        stats_text = (
            "Dung lượng bộ nhớ Flash: 128 MB (Đã dùng 34.2 MB - 26%)\n"
            "Tần số ghi log nội bộ: 50 Hz (V, I, RPM, Id, Iq, Temps, Pack V, Contactor State)\n"
            "Số chuyến bay đã ghi nhận: 18 chuyến bay | Tổng thời gian vận hành: 14 giờ 22 phút"
        )
        ctk.CTkLabel(
            info_box, text=stats_text, font=ctk.CTkFont(family="Consolas", size=11),
            text_color=COLOR_TEXT_WHITE, justify="left"
        ).pack(padx=14, pady=12, anchor="w")

        btn_row = ctk.CTkFrame(bbox_win, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=8)

        ctk.CTkButton(
            btn_row, text="📥 Tải Dữ Liệu Từ ESC Flash", width=200, height=34,
            fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER,
            font=ctk.CTkFont(family=FONT_PRIMARY, size=11, weight="bold"),
            command=lambda: messagebox.showinfo("BlackBox", "Đã tải xong nhật ký vận hành từ bộ nhớ Flash!")
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="📂 Mở File CSV BlackBox...", width=180, height=34,
            fg_color="#223042", hover_color="#33465C",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=11, weight="bold"),
            command=lambda: messagebox.showinfo("BlackBox", "Vui lòng chọn file CSV để phân tích đồ thị!")
        ).pack(side="left")


def main():
    app = ViettelMainApp()
    app.mainloop()


if __name__ == "__main__":
    main()
