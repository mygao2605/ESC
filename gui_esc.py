"""
VIETTEL BLDC / ESC CONTROLLER - MODULE GIAO DIỆN QUẢN LÝ ESC
File: gui_esc.py
Chịu trách nhiệm:
1. Tái hiện chuẩn xác 2 cửa sổ Modbus Poll từ bantin.jpeg:
   - ModbusRead.mbp (F=03, 11 thanh ghi: StateAct, SpeedRpm, DcBusVolt, D_Curr, Q_Curr, Fault_H/L, MotorTemp, TempA/B/C)
   - ModbusWrite.mbp (F=16, 2 thanh ghi: ON/OFF, SpeedRpm)
2. Bảng điều khiển động cơ BLDC trực quan (Nút BẬT/TẮT, thanh trượt SpeedRpm, các mức đặt nhanh, gửi F=16 chu kỳ)
3. 8 khối đồng hồ số điện tử giám sát tức thời (Digital Gauges)
4. Đồ thị sóng Matplotlib đa kênh thời gian thực (SpeedRpm, DcBusVolt, D_Curr, Q_Curr, Temps) kèm chức năng ghi log CSV
"""

import time
import math
import csv
from typing import Dict, Any, List

import customtkinter as ctk
from tkinter import filedialog, messagebox

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from mgm_comm import MODBUS_READ_REGISTERS, MODBUS_WRITE_REGISTERS

# Bảng màu chuẩn Viettel Red
VIETTEL_RED = "#EE0033"
VIETTEL_RED_HOVER = "#C4002A"
VIETTEL_RED_LIGHT = "#FF335C"
VIETTEL_PANEL_BG = "#1A1416"
VIETTEL_CARD_BG = "#221A1D"
VIETTEL_BORDER = "#42252A"
VIETTEL_TEXT_WHITE = "#FFFFFF"
VIETTEL_TEXT_GRAY = "#B5A7AA"
MODBUS_BLUE_SEL = "#0078D7"


class ESCTabFrame(ctk.CTkScrollableFrame):
    """Giao diện quản lý toàn diện bộ điều tốc ESC / Động cơ BLDC (Hỗ trợ ScrollView cuộn mượt mà)"""
    def __init__(self, master, conn, **kwargs):
        super().__init__(
            master,
            fg_color="transparent",
            scrollbar_button_color="#3D2024",
            scrollbar_button_hover_color=VIETTEL_RED,
            **kwargs
        )
        self.conn = conn

        # Dữ liệu vẽ đồ thị thời gian thực (Ring buffers)
        self.max_points = 150
        self.t_data = []
        self.rpm_data = []
        self.v_data = []
        self.id_data = []
        self.iq_data = []
        self.mtemp_data = []
        self.tempa_data = []

        self.is_monitoring = True
        self.recording_file = None
        self.csv_writer = None

        self._build_ui()

    def _build_ui(self):
        # Chia thành 2 khu vực chính:
        # - Nửa trên: 2 cửa sổ Modbus chuẩn bantin.jpeg + Bảng điều khiển động cơ BLDC
        # - Nửa dưới: 8 Đồng hồ số điện tử + Đồ thị sóng thời gian thực

        # =====================================================================
        # KHU VỰC 1: BẢN TIN MODBUS READ (F=03) & WRITE (F=16) & ĐIỀU KHIỂN
        # =====================================================================
        top_container = ctk.CTkFrame(self, fg_color="transparent")
        top_container.pack(fill="x", padx=4, pady=(2, 6))
        top_container.grid_columnconfigure(0, weight=11)
        top_container.grid_columnconfigure(1, weight=10)

        # ---------------------------------------------------------------------
        # CỬA SỔ TRÁI: ModbusRead.mbp (F=03: 11 thanh ghi)
        # ---------------------------------------------------------------------
        read_win = ctk.CTkFrame(top_container, fg_color="#181214", corner_radius=8, border_width=1, border_color=VIETTEL_BORDER)
        read_win.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=2)

        read_title_bar = ctk.CTkFrame(read_win, height=30, fg_color="#2E1C20", corner_radius=6)
        read_title_bar.pack(fill="x", padx=4, pady=(4, 2))
        ctk.CTkLabel(
            read_title_bar, text="📄 ModbusRead.mbp  —  Function 03 (Read Holding Registers)",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=VIETTEL_TEXT_WHITE
        ).pack(side="left", padx=8, pady=3)

        read_stat_bar = ctk.CTkFrame(read_win, height=28, fg_color="#22181A", corner_radius=4)
        read_stat_bar.pack(fill="x", padx=6, pady=2)
        self.lbl_read_stat = ctk.CTkLabel(
            read_stat_bar,
            text="Tx = 0: Err = 0: ID = 1: F = 03: SR = 500ms",
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            text_color="#00E676"
        )
        self.lbl_read_stat.pack(side="left", padx=8, pady=2)

        read_table_box = ctk.CTkFrame(read_win, fg_color="#140F11", corner_radius=6, border_width=1, border_color=VIETTEL_BORDER)
        read_table_box.pack(fill="both", expand=True, padx=6, pady=4)

        r_hdr = ctk.CTkFrame(read_table_box, height=26, fg_color="#2D1E22", corner_radius=4)
        r_hdr.pack(fill="x", padx=3, pady=(3, 2))
        ctk.CTkLabel(r_hdr, text="Addr", width=42, font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_RED_LIGHT).pack(side="left", padx=2)
        ctk.CTkLabel(r_hdr, text="Name", width=115, anchor="w", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=4)
        ctk.CTkLabel(r_hdr, text="00000 (Value)", width=95, anchor="e", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=4)
        ctk.CTkLabel(r_hdr, text="HEX", width=68, anchor="center", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_GRAY).pack(side="left", padx=3)
        ctk.CTkLabel(r_hdr, text="Mô tả / Đơn vị", anchor="w", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_GRAY).pack(side="left", fill="x", expand=True, padx=4)

        self.read_row_labels: Dict[int, Dict[str, ctk.CTkLabel]] = {}
        init_read_vals = [0, 0, 0, 9, -1, 0, 0, 30, 24, 26, 26]

        for reg in MODBUS_READ_REGISTERS:
            idx = reg["index"]
            is_last = (idx == 10)
            row_bg = "#1E1618" if idx % 2 == 0 else "#251B1E"
            name_bg = MODBUS_BLUE_SEL if is_last else "transparent"

            row = ctk.CTkFrame(read_table_box, height=27, fg_color=row_bg, corner_radius=4)
            row.pack(fill="x", padx=3, pady=1)

            lbl_idx = ctk.CTkLabel(row, text=f"{idx}", width=42, font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color=VIETTEL_TEXT_GRAY)
            lbl_idx.pack(side="left", padx=2)

            lbl_name = ctk.CTkLabel(
                row, text=f"  {reg['name']}", width=115, anchor="w",
                fg_color=name_bg, corner_radius=3,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=VIETTEL_TEXT_WHITE
            )
            lbl_name.pack(side="left", padx=4, pady=1)

            v0 = init_read_vals[idx]
            lbl_val = ctk.CTkLabel(
                row, text=f"{v0}", width=95, anchor="e",
                font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
                text_color="#00E676" if idx in (1, 2) else VIETTEL_TEXT_WHITE
            )
            lbl_val.pack(side="left", padx=4)

            lbl_hex = ctk.CTkLabel(row, text=f"0x{(v0 & 0xFFFF):04X}", width=68, anchor="center", font=ctk.CTkFont(family="Consolas", size=10), text_color=VIETTEL_TEXT_GRAY)
            lbl_hex.pack(side="left", padx=3)

            lbl_desc = ctk.CTkLabel(
                row, text=f"{reg['desc']} ({reg['unit']})" if reg['unit'] else reg['desc'],
                anchor="w", font=ctk.CTkFont(size=10), text_color=VIETTEL_TEXT_GRAY
            )
            lbl_desc.pack(side="left", fill="x", expand=True, padx=4)

            self.read_row_labels[idx] = {
                "addr": lbl_idx,
                "name": lbl_name,
                "val": lbl_val,
                "hex": lbl_hex,
                "desc": lbl_desc,
            }

        read_hex_box = ctk.CTkFrame(read_win, fg_color="#120D0F", corner_radius=6, border_width=1, border_color=VIETTEL_BORDER)
        read_hex_box.pack(fill="x", padx=6, pady=(2, 5))
        self.lbl_read_tx_hex = ctk.CTkLabel(read_hex_box, text="[TX F=03] >> 01 03 00 00 00 0B 04 0D", font=ctk.CTkFont(family="Consolas", size=10), text_color="#FFD54F", anchor="w")
        self.lbl_read_tx_hex.pack(fill="x", padx=8, pady=(3, 1))
        self.lbl_read_rx_hex = ctk.CTkLabel(read_hex_box, text="[RX F=03] << Đang chờ dữ liệu...", font=ctk.CTkFont(family="Consolas", size=10), text_color="#80CBC4", anchor="w")
        self.lbl_read_rx_hex.pack(fill="x", padx=8, pady=(1, 3))

        # ---------------------------------------------------------------------
        # CỬA SỔ PHẢI: ModbusWrite.mbp (F=16: 2 thanh ghi) & BẢNG ĐIỀU KHIỂN BLDC
        # ---------------------------------------------------------------------
        write_win = ctk.CTkFrame(top_container, fg_color="#181214", corner_radius=8, border_width=1, border_color=VIETTEL_BORDER)
        write_win.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=2)

        write_title_bar = ctk.CTkFrame(write_win, height=30, fg_color="#3B151C", corner_radius=6)
        write_title_bar.pack(fill="x", padx=4, pady=(4, 2))
        ctk.CTkLabel(
            write_title_bar, text="📝 ModbusWrite.mbp  —  Function 16 (Write Multiple Registers)",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=VIETTEL_TEXT_WHITE
        ).pack(side="left", padx=8, pady=3)

        write_stat_bar = ctk.CTkFrame(write_win, height=28, fg_color="#22181A", corner_radius=4)
        write_stat_bar.pack(fill="x", padx=6, pady=2)
        self.lbl_write_stat = ctk.CTkLabel(
            write_stat_bar,
            text="Tx = 0: Err = 0: ID = 1: F = 16: SR = 500ms",
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            text_color="#FFD54F"
        )
        self.lbl_write_stat.pack(side="left", padx=8, pady=2)

        write_table_box = ctk.CTkFrame(write_win, fg_color="#140F11", corner_radius=6, border_width=1, border_color=VIETTEL_BORDER)
        write_table_box.pack(fill="x", padx=6, pady=3)

        w_hdr = ctk.CTkFrame(write_table_box, height=26, fg_color="#2D1E22", corner_radius=4)
        w_hdr.pack(fill="x", padx=3, pady=(3, 1))
        ctk.CTkLabel(w_hdr, text="Addr", width=42, font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_RED_LIGHT).pack(side="left", padx=2)
        ctk.CTkLabel(w_hdr, text="Name", width=120, anchor="w", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=4)
        ctk.CTkLabel(w_hdr, text="00000 (Hiện tại)", width=120, anchor="e", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=4)
        ctk.CTkLabel(w_hdr, text="Nhập mới & Enter", anchor="w", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_GRAY).pack(side="left", fill="x", expand=True, padx=6)

        w_row0 = ctk.CTkFrame(write_table_box, height=32, fg_color="#1E1618", corner_radius=4)
        w_row0.pack(fill="x", padx=3, pady=1.5)
        self.lbl_w_addr0 = ctk.CTkLabel(w_row0, text="0", width=42, font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color=VIETTEL_TEXT_GRAY)
        self.lbl_w_addr0.pack(side="left", padx=2)
        ctk.CTkLabel(w_row0, text="  ON/OFF", width=120, anchor="w", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=4)
        self.lbl_w_val0 = ctk.CTkLabel(w_row0, text="0", width=120, anchor="e", font=ctk.CTkFont(family="Consolas", size=13, weight="bold"), text_color=VIETTEL_TEXT_WHITE)
        self.lbl_w_val0.pack(side="left", padx=4)
        self.ent_w_onoff = ctk.CTkEntry(w_row0, width=95, border_color=VIETTEL_BORDER, placeholder_text="0 hoặc 1")
        self.ent_w_onoff.insert(0, "0")
        self.ent_w_onoff.pack(side="left", padx=6, pady=2)
        self.ent_w_onoff.bind("<Return>", lambda e: self._send_write_from_entries())

        w_row1 = ctk.CTkFrame(write_table_box, height=32, fg_color="#251B1E", corner_radius=4)
        w_row1.pack(fill="x", padx=3, pady=(1.5, 4))
        self.lbl_w_addr1 = ctk.CTkLabel(w_row1, text="1", width=42, font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color=VIETTEL_TEXT_GRAY)
        self.lbl_w_addr1.pack(side="left", padx=2)
        ctk.CTkLabel(w_row1, text="  SpeedRpm", width=120, anchor="w", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=4)
        self.lbl_w_val1 = ctk.CTkLabel(
            w_row1, text="0  ", width=120, anchor="e",
            fg_color=MODBUS_BLUE_SEL, corner_radius=3,
            font=ctk.CTkFont(family="Consolas", size=13, weight="bold"), text_color=VIETTEL_TEXT_WHITE
        )
        self.lbl_w_val1.pack(side="left", padx=4, pady=2)
        self.ent_w_rpm = ctk.CTkEntry(w_row1, width=95, border_color=VIETTEL_BORDER, placeholder_text="RPM")
        self.ent_w_rpm.insert(0, "0")
        self.ent_w_rpm.pack(side="left", padx=6, pady=2)
        self.ent_w_rpm.bind("<Return>", lambda e: self._send_write_from_entries())

        # Bảng điều khiển động cơ BLDC
        ctrl_panel = ctk.CTkFrame(write_win, fg_color=VIETTEL_CARD_BG, corner_radius=8, border_width=1, border_color=VIETTEL_BORDER)
        ctrl_panel.pack(fill="both", expand=True, padx=6, pady=3)

        ctk.CTkLabel(
            ctrl_panel, text="🎛️ BẢNG ĐIỀU KHIỂN ĐỘNG CƠ BLDC (MODBUS F=16 WRITE)",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=VIETTEL_RED_LIGHT
        ).pack(anchor="w", padx=10, pady=(6, 4))

        btn_row = ctk.CTkFrame(ctrl_panel, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=2)

        self.btn_motor_on = ctk.CTkButton(
            btn_row, text="🟢 BẬT ĐỘNG CƠ (ON/OFF = 1)", height=34,
            fg_color="#1E8E3E", hover_color="#16692D",
            font=ctk.CTkFont(size=11, weight="bold"),
            command=lambda: self._quick_set_on_off(1)
        )
        self.btn_motor_on.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self.btn_motor_off = ctk.CTkButton(
            btn_row, text="🔴 DỪNG ĐỘNG CƠ (ON/OFF = 0)", height=34,
            fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=lambda: self._quick_set_on_off(0)
        )
        self.btn_motor_off.pack(side="left", fill="x", expand=True, padx=(4, 0))

        rpm_slider_box = ctk.CTkFrame(ctrl_panel, fg_color="#181214", corner_radius=6, border_width=1, border_color=VIETTEL_BORDER)
        rpm_slider_box.pack(fill="x", padx=10, pady=5)

        rpm_top = ctk.CTkFrame(rpm_slider_box, fg_color="transparent")
        rpm_top.pack(fill="x", padx=8, pady=(4, 2))
        ctk.CTkLabel(
            rpm_top, text="Đặt tốc độ mục tiêu (Thanh ghi 1 - SpeedRpm):",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_WHITE
        ).pack(side="left")
        self.lbl_target_rpm_big = ctk.CTkLabel(
            rpm_top, text="0 RPM",
            font=ctk.CTkFont(family="Consolas", size=14, weight="bold"), text_color="#00E676"
        )
        self.lbl_target_rpm_big.pack(side="right")

        self.slider_modbus_rpm = ctk.CTkSlider(
            rpm_slider_box, from_=0, to=6000, number_of_steps=120,
            progress_color=VIETTEL_RED, button_color=VIETTEL_RED, button_hover_color=VIETTEL_RED_HOVER,
            command=self._on_modbus_rpm_slider
        )
        self.slider_modbus_rpm.set(0)
        self.slider_modbus_rpm.pack(fill="x", padx=8, pady=(2, 4))

        preset_row = ctk.CTkFrame(rpm_slider_box, fg_color="transparent")
        preset_row.pack(fill="x", padx=8, pady=(0, 6))
        ctk.CTkLabel(preset_row, text="Chọn nhanh:", font=ctk.CTkFont(size=10), text_color=VIETTEL_TEXT_GRAY).pack(side="left", padx=(0, 4))
        for spd in [0, 500, 1000, 1500, 2000, 3000, 5000]:
            b = ctk.CTkButton(
                preset_row, text=f"{spd}", width=46, height=24,
                fg_color="#2B2023", hover_color=VIETTEL_RED,
                font=ctk.CTkFont(size=10, weight="bold"),
                command=lambda s=spd: self._set_preset_rpm(s)
            )
            b.pack(side="left", padx=2)

        action_row = ctk.CTkFrame(ctrl_panel, fg_color="transparent")
        action_row.pack(fill="x", padx=10, pady=(2, 6))

        self.sw_cyclic_write = ctk.CTkSwitch(
            action_row, text="Tự động gửi F=16 (500ms)",
            progress_color=VIETTEL_RED, font=ctk.CTkFont(size=11),
            command=self._on_cyclic_write_toggled
        )
        self.sw_cyclic_write.select()
        self.sw_cyclic_write.pack(side="left")

        self.btn_send_fc16 = ctk.CTkButton(
            action_row, text="⚡ Gửi F=16 ngay", width=140, height=30,
            fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER,
            font=ctk.CTkFont(size=11, weight="bold"),
            command=self._send_write_from_entries
        )
        self.btn_send_fc16.pack(side="right")

        # =====================================================================
        # KHU VỰC 2: ĐỒNG HỒ ĐIỆN TỬ & ĐỒ THỊ SÓNG THỜI GIAN THỰC
        # =====================================================================
        bottom_container = ctk.CTkFrame(self, fg_color=VIETTEL_PANEL_BG, corner_radius=8, border_width=1, border_color=VIETTEL_BORDER)
        bottom_container.pack(fill="x", padx=4, pady=(2, 10))
        bottom_container.grid_columnconfigure(0, weight=1)
        bottom_container.grid_rowconfigure(0, weight=0)
        bottom_container.grid_rowconfigure(1, weight=1)

        # 8 khối đồng hồ điện tử
        cards_frame = ctk.CTkFrame(bottom_container, fg_color="transparent")
        cards_frame.grid(row=0, column=0, sticky="ew", padx=6, pady=4)

        self.card_labels = {}
        metrics = [
            ("StateAct",   "TRẠNG THÁI (StateAct)",     "0 (IDLE)", "",    "#00E676"),
            ("SpeedRpm",   "TỐC ĐỘ (SpeedRpm)",         "0",        "RPM", "#00E676"),
            ("DcBusVolt",  "ĐIỆN ÁP DC BUS (DcBusVolt)","0",        "V",   VIETTEL_RED_LIGHT),
            ("D_Curr",     "DÒNG TRỤC D (D_Curr)",      "9",        "A",   "#4FC3F7"),
            ("Q_Curr",     "DÒNG TRỤC Q (Q_Curr)",      "-1",       "A",   "#FF7043"),
            ("Fault_HL",   "MÃ LỖI (Fault_H / L)",      "0 / 0",    "HEX", "#FFD54F"),
            ("MotorTemp",  "NHIỆT ĐỘ MOTOR",            "30",       "°C",  "#FF8A80"),
            ("PhaseTemps", "NHIỆT ĐỘ PHA (A/B/C)",      "24/26/26", "°C",  VIETTEL_RED),
        ]

        for idx, (key, title, init_val, unit, color) in enumerate(metrics):
            r = idx // 4
            c = idx % 4
            card = ctk.CTkFrame(cards_frame, fg_color=VIETTEL_CARD_BG, corner_radius=6, border_width=1, border_color=VIETTEL_BORDER)
            card.grid(row=r, column=c, padx=4, pady=3, sticky="nsew")
            cards_frame.grid_columnconfigure(c, weight=1)

            ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=9, weight="bold"), text_color=VIETTEL_TEXT_GRAY).pack(anchor="w", padx=8, pady=(4, 1))

            val_box = ctk.CTkFrame(card, fg_color="transparent")
            val_box.pack(anchor="w", padx=8, pady=(0, 4))

            lbl_val = ctk.CTkLabel(val_box, text=init_val, font=ctk.CTkFont(family="Consolas", size=17, weight="bold"), text_color=color)
            lbl_val.pack(side="left")

            if unit:
                lbl_unit = ctk.CTkLabel(val_box, text=f" {unit}", font=ctk.CTkFont(size=10), text_color=VIETTEL_TEXT_GRAY)
                lbl_unit.pack(side="left", padx=(2, 0), pady=(3, 0))

            self.card_labels[key] = lbl_val

        # Khung đồ thị Matplotlib
        chart_box = ctk.CTkFrame(bottom_container, fg_color="transparent")
        chart_box.grid(row=1, column=0, sticky="nsew", padx=6, pady=2)
        chart_box.grid_columnconfigure(0, weight=1)
        chart_box.grid_rowconfigure(0, weight=0)
        chart_box.grid_rowconfigure(1, weight=1)

        chart_ctrl = ctk.CTkFrame(chart_box, height=28, fg_color="transparent")
        chart_ctrl.grid(row=0, column=0, sticky="ew", padx=4, pady=1)

        self.chk_rpm = ctk.CTkCheckBox(chart_ctrl, text="SpeedRpm / 10", text_color="#00E676", fg_color="#00E676", font=ctk.CTkFont(size=10, weight="bold"))
        self.chk_rpm.select()
        self.chk_rpm.pack(side="left", padx=6)

        self.chk_v = ctk.CTkCheckBox(chart_ctrl, text="DcBusVolt (V)", text_color=VIETTEL_RED_LIGHT, fg_color=VIETTEL_RED, font=ctk.CTkFont(size=10, weight="bold"))
        self.chk_v.select()
        self.chk_v.pack(side="left", padx=6)

        self.chk_id = ctk.CTkCheckBox(chart_ctrl, text="D_Curr (A)", text_color="#4FC3F7", fg_color="#4FC3F7", font=ctk.CTkFont(size=10, weight="bold"))
        self.chk_id.select()
        self.chk_id.pack(side="left", padx=6)

        self.chk_iq = ctk.CTkCheckBox(chart_ctrl, text="Q_Curr (A)", text_color="#FF7043", fg_color="#FF7043", font=ctk.CTkFont(size=10, weight="bold"))
        self.chk_iq.select()
        self.chk_iq.pack(side="left", padx=6)

        self.chk_t = ctk.CTkCheckBox(chart_ctrl, text="MotorTemp (°C)", text_color="#FFD54F", fg_color="#FFD54F", font=ctk.CTkFont(size=10, weight="bold"))
        self.chk_t.select()
        self.chk_t.pack(side="left", padx=6)

        self.btn_pause_chart = ctk.CTkButton(chart_ctrl, text="Tạm dừng", width=70, height=24, fg_color="#332427", hover_color="#4D353A", command=self._toggle_pause_chart)
        self.btn_pause_chart.pack(side="right", padx=3)

        self.btn_clear_chart = ctk.CTkButton(chart_ctrl, text="Xóa đồ thị", width=70, height=24, fg_color="#332427", hover_color="#4D353A", command=self._clear_chart)
        self.btn_clear_chart.pack(side="right", padx=3)

        self.btn_record = ctk.CTkButton(chart_ctrl, text="🔴 Ghi log CSV", width=110, height=24, fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER, font=ctk.CTkFont(size=10, weight="bold"), command=self._toggle_recording)
        self.btn_record.pack(side="right", padx=3)

        self.fig = Figure(figsize=(8, 2.8), dpi=100, facecolor="#140F11")
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor("#0F0B0D")
        self.ax.tick_params(colors="#CCCCCC", labelsize=8)
        self.ax.grid(True, linestyle="--", alpha=0.25, color="#5E2028")
        self.ax.set_title("ĐỒ THỊ THỜI GIAN THỰC ĐỘNG CƠ BLDC (SpeedRpm, DcBusVolt, D/Q_Curr, Temps)", color=VIETTEL_TEXT_WHITE, fontsize=9, pad=4, weight="bold")

        for spine in self.ax.spines.values():
            spine.set_color("#4A1B22")

        self.line_rpm, = self.ax.plot([], [], label="SpeedRpm / 10", color="#00E676", linewidth=1.6)
        self.line_v, = self.ax.plot([], [], label="DcBusVolt (V)", color=VIETTEL_RED, linewidth=1.8)
        self.line_id, = self.ax.plot([], [], label="D_Curr (A)", color="#4FC3F7", linewidth=1.4)
        self.line_iq, = self.ax.plot([], [], label="Q_Curr (A)", color="#FF7043", linewidth=1.6)
        self.line_mtemp, = self.ax.plot([], [], label="MotorTemp (°C)", color="#FFD54F", linewidth=1.4)
        self.ax.legend(loc="upper left", ncol=5, facecolor="#1E1618", edgecolor=VIETTEL_BORDER, labelcolor=VIETTEL_TEXT_WHITE, fontsize=7)

        self.canvas = FigureCanvasTkAgg(self.fig, master=chart_box)
        self.canvas.draw()
        self.canvas.get_tk_widget().grid(row=1, column=0, sticky="nsew", padx=2, pady=2)

    # -------------------------------------------------------------------------
    # ĐIỀU KHIỂN & GỬI LỆNH MODBUS
    # -------------------------------------------------------------------------
    def _quick_set_on_off(self, on_val: int):
        try:
            rpm_val = int(self.ent_w_rpm.get().strip())
        except Exception:
            rpm_val = self.conn.current_write_regs[1]
        if on_val == 1 and rpm_val == 0:
            rpm_val = int(self.slider_modbus_rpm.get())
        self.ent_w_onoff.delete(0, "end")
        self.ent_w_onoff.insert(0, str(on_val))
        self.ent_w_rpm.delete(0, "end")
        self.ent_w_rpm.insert(0, str(rpm_val))
        self.conn.write_control_command(on_val, rpm_val, immediate=True)

    def _set_preset_rpm(self, rpm_val: int):
        self.slider_modbus_rpm.set(rpm_val)
        self.lbl_target_rpm_big.configure(text=f"{rpm_val} RPM")
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
            self.lbl_target_rpm_big.configure(text=f"{rpm_val} RPM")
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
        self.line_rpm.set_data([], [])
        self.line_v.set_data([], [])
        self.line_id.set_data([], [])
        self.line_iq.set_data([], [])
        self.line_mtemp.set_data([], [])
        self.canvas.draw_idle()

    def _toggle_recording(self):
        if self.recording_file:
            try:
                self.recording_file.close()
            except Exception:
                pass
            self.recording_file = None
            self.csv_writer = None
            self.btn_record.configure(text="🔴 Ghi log CSV", fg_color=VIETTEL_RED)
            messagebox.showinfo("Ghi log", "Đã lưu và đóng tệp log CSV Modbus thành công!")
        else:
            path = filedialog.asksaveasfilename(
                title="Lưu tệp log Modbus RTU (11 thanh ghi)",
                defaultextension=".csv",
                filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
                initialfile=f"viettel_esc_log_{time.strftime('%Y%m%d_%H%M%S')}.csv"
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
    # CẬP NHẬT TELEMETRY (GỌI TỪ LUỒNG CHÍNH MỖI CHU KỲ QUÉT)
    # -------------------------------------------------------------------------
    def update_telemetry(self, d: Dict[str, Any]):
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
            self.card_labels["PhaseTemps"].configure(text=f"{ta}/{tb}/{tc}")

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

        now = time.time()
        self.t_data.append(now)
        self.rpm_data.append(speed_rpm / 10.0)
        self.v_data.append(dc_volt)
        self.id_data.append(d_curr)
        self.iq_data.append(q_curr)
        self.mtemp_data.append(m_temp)

        if len(self.t_data) > self.max_points:
            self.t_data.pop(0)
            self.rpm_data.pop(0)
            self.v_data.pop(0)
            self.id_data.pop(0)
            self.iq_data.pop(0)
            self.mtemp_data.pop(0)

        t_rel = [t - self.t_data[0] for t in self.t_data]
        self.line_rpm.set_data(t_rel, self.rpm_data if self.chk_rpm.get() else [])
        self.line_v.set_data(t_rel, self.v_data if self.chk_v.get() else [])
        self.line_id.set_data(t_rel, self.id_data if self.chk_id.get() else [])
        self.line_iq.set_data(t_rel, self.iq_data if self.chk_iq.get() else [])
        self.line_mtemp.set_data(t_rel, self.mtemp_data if self.chk_t.get() else [])

        self.ax.relim()
        self.ax.autoscale_view(True, True, True)
        self.canvas.draw_idle()

