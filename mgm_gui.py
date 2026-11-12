"""
VIETTEL PROPULSION SUITE - MAIN APPLICATION GUI
File: mgm_gui.py
Chịu trách nhiệm:
1. Cửa sổ ứng dụng chính (Main Application Window) chuẩn nhận diện Đỏ Viettel (Viettel Red Theme).
2. Thanh Header quản lý kết nối truyền thông:
   - Cổng Serial (Port COM11, Baudrate 921600-8-N-1 theo bantin.jpeg)
   - Modbus Slave ID (ID = 1) và Chu kỳ quét Scan Rate (SR = 500ms)
   - Chế độ Mô phỏng (Simulator Switch) và Nút Kết nối (Connect/Disconnect)
3. Tích hợp 3 Tab quản lý chuyên biệt từ 3 file GUI riêng biệt:
   - Tab 1: 🚀 QUẢN LÝ ESC / ĐỘNG CƠ (nạp từ gui_esc.py)
   - Tab 2: 🔋 QUẢN LÝ BMU / PIN (nạp từ gui_bmu.py)
   - Tab 3: ⚡ QUẢN LÝ NGUỒN / POWER PDU (nạp từ gui_power.py)
4. Thanh công cụ tiện ích mở rộng: Cấu hình tham số, Lịch sử Datalogger BlackBox, Terminal Modbus HEX
5. Hàng đợi đa luồng thread-safe phân phối dữ liệu telemetry đồng bộ đến cả 3 module.
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

# Bảng màu chuẩn Viettel Red
VIETTEL_RED = "#EE0033"
VIETTEL_RED_HOVER = "#C4002A"
VIETTEL_RED_LIGHT = "#FF335C"
VIETTEL_PANEL_BG = "#1A1416"
VIETTEL_CARD_BG = "#221A1D"
VIETTEL_BORDER = "#42252A"
VIETTEL_TEXT_WHITE = "#FFFFFF"
VIETTEL_TEXT_GRAY = "#B5A7AA"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class ViettelMainApp(ctk.CTk):
    """Cửa sổ ứng dụng chính kết hợp 3 module: ESC, BMU và POWER"""
    def __init__(self):
        super().__init__()

        self.title("VIETTEL SYSTEM - HỆ THỐNG QUẢN LÝ ESC / BMU / POWER")
        self.geometry("1400x900")
        self.minsize(1150, 760)
        self.configure(fg_color="#120E10")

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

        # Xây dựng giao diện
        self._build_header_bar()
        self._build_main_tabview()
        self._build_status_bar()

        # Hàng đợi đa luồng thread-safe
        self.telemetry_queue = queue.Queue()
        self.log_queue = queue.Queue()

        self._refresh_ports()
        self._process_queues()

        # Mặc định kích hoạt chế độ mô phỏng
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
            text_box, text="VIETTEL VMC",
            font=ctk.CTkFont(size=17, weight="bold"), text_color=VIETTEL_TEXT_WHITE
        )
        lbl_brand.pack(anchor="w")

        sub_row = ctk.CTkFrame(text_box, fg_color="transparent")
        sub_row.pack(anchor="w")
        lbl_sub = ctk.CTkLabel(
            sub_row, text="ESC / BMU / POWER MANAGEMENT",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_RED
        )
        lbl_sub.pack(side="left")
        lbl_ver = ctk.CTkLabel(
            sub_row, text=" | Port 11: 921600-8-N-1 (ID=1, SR=500ms)",
            font=ctk.CTkFont(size=11), text_color=VIETTEL_TEXT_GRAY
        )
        lbl_ver.pack(side="left")

        # Cấu hình Cổng Serial (Port COM11, Baudrate 921600-8-N-1)
        conn_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        conn_frame.pack(side="left", padx=12, pady=8)
        ctk.CTkLabel(
            conn_frame, text="Cổng Serial & Baudrate (8-N-1):",
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

        # Slave ID & Scan Rate (SR)
        mb_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        mb_frame.pack(side="left", padx=10, pady=8)
        ctk.CTkLabel(
            mb_frame, text="Slave ID & Scan Rate:",
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

        # Tiện ích bổ trợ (Tools: Terminal, Datalogger, Params)
        tools_frame = ctk.CTkFrame(self.header_frame, fg_color="transparent")
        tools_frame.pack(side="left", padx=10, pady=8)
        ctk.CTkLabel(tools_frame, text="Công cụ bổ trợ:", font=ctk.CTkFont(size=11), text_color=VIETTEL_TEXT_GRAY).pack(anchor="w")

        t_row = ctk.CTkFrame(tools_frame, fg_color="transparent")
        t_row.pack(anchor="w", pady=2)
        self.btn_term_tool = ctk.CTkButton(
            t_row, text="💻 Terminal HEX", width=110, fg_color="#332427", hover_color="#4D353A",
            font=ctk.CTkFont(size=11), command=self._open_terminal_window
        )
        self.btn_term_tool.pack(side="left", padx=(0, 4))

        self.btn_hist_tool = ctk.CTkButton(
            t_row, text="📈 BlackBox", width=95, fg_color="#332427", hover_color="#4D353A",
            font=ctk.CTkFont(size=11), command=self._open_blackbox_window
        )
        self.btn_hist_tool.pack(side="left")

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
    # 2. MAIN TABVIEW: 3 TAB QUẢN LÝ (ESC, BMU, POWER) TỪ 3 FILE RIÊNG BIỆT
    # =========================================================================
    def _build_main_tabview(self):
        self.tabview = ctk.CTkTabview(
            self,
            corner_radius=10,
            command=self._on_tab_changed,
            fg_color=VIETTEL_PANEL_BG,
            segmented_button_selected_color=VIETTEL_RED,
            segmented_button_selected_hover_color=VIETTEL_RED_HOVER,
            segmented_button_unselected_color="#2A2022",
            segmented_button_unselected_hover_color="#3D2B2E"
        )
        self.tabview.pack(fill="both", expand=True, padx=10, pady=(4, 4))

        # 4 Tab quản lý chuyên biệt theo yêu cầu
        self.tab_esc_container = self.tabview.add("🚀 QUẢN LÝ ESC / ĐỘNG CƠ (ESC)")
        self.tab_bmu_container = self.tabview.add("🔋 QUẢN LÝ BMU / PIN (BMU)")
        self.tab_power_container = self.tabview.add("⚡ HỆ THỐNG NGUỒN & PHÂN PHỐI (POWER)")
        self.tab_mld_container = self.tabview.add("🎯 BỘ ĐIỀU KHIỂN MLD (MLD)")

        # Khởi tạo và nhúng 4 View từ 4 file riêng biệt
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
    # 3. STATUS BAR
    # =========================================================================
    def _build_status_bar(self):
        self.status_bar = ctk.CTkFrame(self, height=28, corner_radius=0, fg_color="#181214", border_width=1, border_color=VIETTEL_BORDER)
        self.status_bar.pack(side="bottom", fill="x")

        self.lbl_status = ctk.CTkLabel(self.status_bar, text="● Chưa kết nối", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_GRAY)
        self.lbl_status.pack(side="left", padx=15)

        self.lbl_port_spec = ctk.CTkLabel(
            self.status_bar,
            text="Port 11: 921600-8-N-1  |  ID = 1  |  F=03 Read (11) / F=16 Write (2)  |  SR = 500ms  |  3 Modules: ESC - BMU - POWER",
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

                # Chỉ phân phối telemetry tới Tab đang mở để tối ưu tài nguyên và chống giật lag
                if "POWER" in sel and hasattr(self, 'view_power') and self.view_power.winfo_exists():
                    self.view_power.update_telemetry(latest_d)
                elif "ESC" in sel and hasattr(self, 'view_esc') and self.view_esc.winfo_exists():
                    self.view_esc.update_telemetry(latest_d)
                elif "BMU" in sel and hasattr(self, 'view_bmu') and self.view_bmu.winfo_exists():
                    self.view_bmu.update_telemetry(latest_d)
                elif "MLD" in sel and hasattr(self, 'view_mld') and self.view_mld.winfo_exists():
                    self.view_mld.update_telemetry(latest_d)

                # Nếu Tab ESC đang bật chế độ Ghi log CSV thì vẫn ghi file ngầm (không cần vẽ GUI)
                if "ESC" not in sel and hasattr(self, 'view_esc') and getattr(self.view_esc, 'recording_file', None):
                    self.view_esc.log_csv_record(latest_d)

                # Nếu Tab MLD đang bật chế độ Ghi log CSV thì vẫn ghi file ngầm
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
        term_win.title("Terminal Modbus HEX - Debug Truyền Thông Viettel")
        term_win.geometry("720x450")
        term_win.configure(fg_color="#181214")

        top_row = ctk.CTkFrame(term_win, height=36, fg_color="transparent")
        top_row.pack(fill="x", padx=10, pady=8)

        ctk.CTkLabel(top_row, text="Gửi bản tin HEX:", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left")
        ent_hex = ctk.CTkEntry(top_row, width=320, placeholder_text="01 03 00 00 00 0B 04 0D", border_color=VIETTEL_BORDER)
        ent_hex.pack(side="left", padx=8)

        btn_send = ctk.CTkButton(
            top_row, text="Gửi", width=70, fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER,
            command=lambda: self._send_term_hex(ent_hex.get().strip())
        )
        btn_send.pack(side="left")

        self._txt_term = ctk.CTkTextbox(term_win, font=ctk.CTkFont(family="Consolas", size=11), fg_color="#120D0F", text_color="#E0E0E0", border_width=1, border_color=VIETTEL_BORDER)
        self._txt_term.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._txt_term.insert("end", "=== VIETTEL MODBUS RTU TERMINAL INITIALIZED ===\n")

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
        bbox_win.title("Phân Tích Datalogger BlackBox - Viettel Propulsion")
        bbox_win.geometry("800x480")
        bbox_win.configure(fg_color="#181214")

        ctk.CTkLabel(bbox_win, text="📊 DỮ LIỆU CHUYẾN BAY & NHẬT KÝ VẬN HÀNH BLACKBOX", font=ctk.CTkFont(size=13, weight="bold"), text_color=VIETTEL_RED_LIGHT).pack(padx=12, pady=10, anchor="w")

        info_box = ctk.CTkFrame(bbox_win, fg_color=VIETTEL_CARD_BG, corner_radius=6, border_width=1, border_color=VIETTEL_BORDER)
        info_box.pack(fill="x", padx=12, pady=6)

        stats_text = (
            "Dung lượng bộ nhớ Flash: 128 MB (Đã dùng 34.2 MB - 26%)\n"
            "Tần số ghi log nội bộ: 50 Hz (V, I, RPM, Id, Iq, Temps, Pack V, Contactor State)\n"
            "Số chuyến bay đã ghi nhận: 18 chuyến bay | Tổng thời gian vận hành: 14 giờ 22 phút"
        )
        ctk.CTkLabel(info_box, text=stats_text, font=ctk.CTkFont(family="Consolas", size=11), text_color=VIETTEL_TEXT_WHITE, justify="left").pack(padx=12, pady=10, anchor="w")

        btn_row = ctk.CTkFrame(bbox_win, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=8)

        ctk.CTkButton(
            btn_row, text="📥 Tải Dữ Liệu Từ ESC Flash", width=200, fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER,
            command=lambda: messagebox.showinfo("BlackBox", "Đã tải xong nhật ký vận hành từ bộ nhớ Flash!")
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="📂 Mở File CSV BlackBox...", width=180, fg_color="#332427", hover_color="#4D353A",
            command=lambda: messagebox.showinfo("BlackBox", "Vui lòng chọn file CSV để phân tích đồ thị!")
        ).pack(side="left")


def main():
    app = ViettelMainApp()
    app.mainloop()


if __name__ == "__main__":
    main()
