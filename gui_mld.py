"""
VIETTEL PROPULSION SUITE - MLD CONTROLLER GUI
File: gui_mld.py
Chịu trách nhiệm:
1. Giao diện quản lý & điều khiển Bộ điều khiển MLD (MLD Controller).
2. Bản tin đọc (Read - Modbus Function 03): 7 thanh ghi:
   - [0] State (Trạng thái)
   - [1] Position (Vị trí hiện tại, đơn vị mm: -1700 .. 1700)
   - [2] Vdc_bus (Điện áp nguồn DC Bus, V)
   - [3] Error_code (Mã lỗi)
   - [4] Set_Position (Vị trí đặt phản hồi về, mm)
   - [5] Speed (Tốc độ động cơ, RPM)
   - [6] Hall_Value (Giá trị cảm biến Hall)
3. Bản tin ghi (Write - Modbus Function 16): 4 thanh ghi:
   - [0] Set_Position (Vị trí đặt: mm, giới hạn -1700 đến 1700)
   - [1] State (Lệnh trạng thái BẬT/TẮT: 1 hoặc 0)
   - [2] Sel_test (Chế độ tự kiểm tra: ON=1 / OFF=0)
   - [3] Period (ms) (Chu kỳ thời gian thực thi: 100 đến 2000 ms)
4. Tích hợp đồ thị bám vị trí thời gian thực (Position vs Set_Position Tracking) và ghi log CSV.
5. Tối ưu chống giật lag / nhấp nháy màn hình (Dirty Checking & Throttled Rendering).
"""

import os
import sys
import time
import csv
import math
from typing import Dict, Any, List, Optional

import customtkinter as ctk
from tkinter import filedialog, messagebox
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from viettel_theme import (
    COLOR_BG, COLOR_HEADER_BG, COLOR_PANEL_BG, COLOR_CARD_BG, COLOR_CARD_BG_HOVER,
    COLOR_CARD_INNER, COLOR_ROW_ALT1, COLOR_ROW_ALT2, COLOR_BORDER, COLOR_BORDER_SUBTLE,
    COLOR_BORDER_RED, VIETTEL_RED, VIETTEL_RED_HOVER, VIETTEL_RED_LIGHT, VIETTEL_RED_GLOW,
    COLOR_SUCCESS, COLOR_SUCCESS_HOVER, COLOR_SUCCESS_GLOW, COLOR_CYAN,
    COLOR_WARNING, COLOR_WARNING_LIGHT, COLOR_CRITICAL, COLOR_BLUE_SEL,
    COLOR_TEXT_WHITE, COLOR_TEXT_GRAY, COLOR_TEXT_MUTED,
    font_section_title, font_card_label, font_digital_lg, font_digital_md, font_digital_sm,
    font_mono, font_mono_sm, font_btn, FONT_PRIMARY, safe_configure_label
)

# BẢNG ĐẶC TẢ 7 THANH GHI BẢN TIN ĐỌC (FUNCTION 03)
MLD_READ_REGISTERS = [
    {"index": 0, "name": "State", "desc": "Trạng thái hoạt động", "unit": "0: IDLE, 1: RUN, 2: FAULT"},
    {"index": 1, "name": "Position", "desc": "Vị trí hiện tại", "unit": "mm"},
    {"index": 2, "name": "Vdc_bus", "desc": "Điện áp DC Bus", "unit": "V"},
    {"index": 3, "name": "Error_code", "desc": "Mã lỗi hệ thống", "unit": "0: OK"},
    {"index": 4, "name": "Set_Position", "desc": "Vị trí đặt", "unit": "mm"},
    {"index": 5, "name": "Speed", "desc": "Tốc độ động cơ", "unit": "RPM"},
    {"index": 6, "name": "Hall_Value", "desc": "Giá trị cảm biến Hall", "unit": "Mã nhị phân"},
]

# BẢNG ĐẶC TẢ 4 THANH GHI BẢN TIN GHI (FUNCTION 16)
MLD_WRITE_REGISTERS = [
    {"index": 0, "name": "Set_Position", "desc": "Vị trí đặt mong muốn", "unit": "mm (-1700..1700)", "default": 0},
    {"index": 1, "name": "State", "desc": "Lệnh trạng thái điều khiển", "unit": "0: TẮT, 1: BẬT", "default": 0},
    {"index": 2, "name": "Sel_test", "desc": "Tự kiểm tra (Self-Test)", "unit": "0: TẮT, 1: BẬT", "default": 0},
    {"index": 3, "name": "Period (ms)", "desc": "Chu kỳ thực thi", "unit": "100..2000 ms", "default": 500},
]


def _safe_configure_label(lbl, text: str, text_color: str = None):
    safe_configure_label(lbl, text, text_color)


class MLDTabFrame(ctk.CTkScrollableFrame):
    """Giao diện quản lý & điều khiển Bộ điều khiển MLD (MLD Controller) chuẩn sản xuất"""
    def __init__(self, master, conn, **kwargs):
        super().__init__(
            master,
            fg_color="transparent",
            scrollbar_button_color="#223042",
            scrollbar_button_hover_color=VIETTEL_RED,
            **kwargs
        )
        self.conn = conn

        # Bộ đệm dữ liệu vẽ đồ thị thời gian thực (Position tracking)
        self.max_points = 150
        self.t_data = []
        self.pos_data = []
        self.set_pos_data = []
        self.speed_data = []
        self.vdc_data = []
        self.is_monitoring = True
        self._last_chart_redraw = 0.0

        # Ghi log CSV
        self.csv_writer = None
        self.recording_file = None
        self.record_start_time = None

        # Lưu cache nhãn để cập nhật nhanh
        self.hero_labels: Dict[str, ctk.CTkLabel] = {}
        self.read_row_labels: Dict[int, Dict[str, ctk.CTkLabel]] = {}
        self.write_row_labels: Dict[int, Dict[str, ctk.CTkLabel]] = {}

        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)

        # 1. THANH TRẠNG THÁI MODBUS MLD
        self._build_modbus_status_bar()

        # 2. KHU VỰC HERO CARDS (7 CHỈ SỐ BẢN TIN ĐỌC)
        self._build_hero_cards()

        # 3. KHU VỰC ĐIỀU KHIỂN & BẢN TIN GHI (4 THANH GHI)
        self._build_control_write_section()

        # 4. BẢNG CHI TIẾT 7 THANH GHI ĐỌC & 4 THANH GHI GHI
        self._build_registers_tables()

        # 5. ĐỒ THỊ BÁM VỊ TRÍ THỜI GIAN THỰC (REAL-TIME TRACKING CHART)
        self._build_chart_section()

    # -------------------------------------------------------------------------
    # 1. THANH TRẠNG THÁI TRUYỀN THÔNG MODBUS MLD
    # -------------------------------------------------------------------------
    def _build_modbus_status_bar(self):
        status_card = ctk.CTkFrame(
            self, fg_color=COLOR_CARD_BG, corner_radius=8,
            border_width=1, border_color=COLOR_BORDER
        )
        status_card.pack(fill="x", padx=10, pady=(6, 4))

        row1 = ctk.CTkFrame(status_card, fg_color="transparent")
        row1.pack(fill="x", padx=12, pady=6)

        ctk.CTkLabel(
            row1,
            text="🎯 BỘ ĐIỀU KHIỂN TRUYỀN ĐỘNG MLD — MODBUS F=03 (READ 7) & F=16 (WRITE 4)",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=11, weight="bold"),
            text_color=COLOR_TEXT_WHITE
        ).pack(side="left")

        self.lbl_read_stat = ctk.CTkLabel(
            row1,
            text="Tx = 0: Err = 0: ID = 1: F = 03: SR = 500ms (Read 7 Regs)",
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
            text_color=COLOR_CYAN
        )
        self.lbl_read_stat.pack(side="right", padx=10)

        self.lbl_write_stat = ctk.CTkLabel(
            row1,
            text="Tx = 0: Err = 0: ID = 1: F = 16 (Write 4 Regs)",
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
            text_color=COLOR_SUCCESS_GLOW
        )
        self.lbl_write_stat.pack(side="right", padx=10)

        # Hàng hiển thị Frame HEX Modbus
        row2 = ctk.CTkFrame(
            status_card, fg_color=COLOR_CARD_INNER, corner_radius=6,
            border_width=1, border_color=COLOR_BORDER_SUBTLE
        )
        row2.pack(fill="x", padx=12, pady=(0, 6))

        self.lbl_read_tx_hex = ctk.CTkLabel(
            row2, text="[TX F=03] >> 01 03 00 00 00 07 04 08",
            font=ctk.CTkFont(family="Consolas", size=9), text_color=COLOR_SUCCESS_GLOW
        )
        self.lbl_read_tx_hex.pack(side="left", padx=8, pady=3)

        self.lbl_read_rx_hex = ctk.CTkLabel(
            row2, text="[RX F=03] << Chưa có phản hồi",
            font=ctk.CTkFont(family="Consolas", size=9), text_color=COLOR_WARNING_LIGHT
        )
        self.lbl_read_rx_hex.pack(side="left", padx=15, pady=3)

        self.lbl_write_tx_hex = ctk.CTkLabel(
            row2, text="[TX F=16] >> (Sẵn sàng)",
            font=ctk.CTkFont(family="Consolas", size=9), text_color=COLOR_CYAN
        )
        self.lbl_write_tx_hex.pack(side="right", padx=8, pady=3)

    # -------------------------------------------------------------------------
    # 2. KHU VỰC HERO CARDS (7 CHỈ SỐ BẢN TIN ĐỌC)
    # -------------------------------------------------------------------------
    def _build_hero_cards(self):
        hero_box = ctk.CTkFrame(self, fg_color="transparent")
        hero_box.pack(fill="x", padx=10, pady=4)

        for col in range(7):
            hero_box.grid_columnconfigure(col, weight=1)

        cards_spec = [
            ("state", "TRẠNG THÁI (STATE)", "IDLE (0)", COLOR_TEXT_WHITE, "Thanh ghi 0"),
            ("position", "VỊ TRÍ THỰC (POS)", "0", COLOR_SUCCESS_GLOW, "Thanh ghi 1 (mm)"),
            ("vdc_bus", "ĐIỆN ÁP DC (VDC)", "0.0", COLOR_WARNING_LIGHT, "Thanh ghi 2 (V)"),
            ("error_code", "MÃ LỖI (ERR)", "0 (OK)", COLOR_SUCCESS_GLOW, "Thanh ghi 3"),
            ("set_pos_read", "VỊ TRÍ ĐẶT (SET)", "0", COLOR_CYAN, "Thanh ghi 4 (mm)"),
            ("speed", "TỐC ĐỘ (SPEED)", "0", "#FB923C", "Thanh ghi 5 (RPM)"),
            ("hall_val", "CẢM BIẾN HALL", "0 (0x00)", "#C084FC", "Thanh ghi 6 (Bits)"),
        ]

        for idx, (key, title, default_val, text_color, note) in enumerate(cards_spec):
            card = ctk.CTkFrame(
                hero_box, fg_color=COLOR_CARD_BG, corner_radius=8,
                border_width=1, border_color=COLOR_BORDER
            )
            card.grid(row=0, column=idx, padx=3, pady=2, sticky="nsew")

            ctk.CTkLabel(
                card, text=title, font=ctk.CTkFont(family=FONT_PRIMARY, size=9, weight="bold"),
                text_color=COLOR_TEXT_GRAY
            ).pack(pady=(6, 1))

            lbl_val = ctk.CTkLabel(
                card, text=default_val,
                font=ctk.CTkFont(family="Consolas", size=15, weight="bold"), text_color=text_color
            )
            lbl_val.pack(pady=1)
            self.hero_labels[key] = lbl_val

            ctk.CTkLabel(
                card, text=note, font=ctk.CTkFont(size=8), text_color=COLOR_TEXT_MUTED
            ).pack(pady=(0, 5))

    # -------------------------------------------------------------------------
    # 3. KHU VỰC ĐIỀU KHIỂN & BẢN TIN GHI (4 THANH GHI)
    # -------------------------------------------------------------------------
    def _build_control_write_section(self):
        ctrl_box = ctk.CTkFrame(
            self, fg_color=COLOR_CARD_BG, corner_radius=8,
            border_width=1, border_color=COLOR_BORDER
        )
        ctrl_box.pack(fill="x", padx=10, pady=4)

        header = ctk.CTkFrame(ctrl_box, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(8, 4))

        ctk.CTkLabel(
            header,
            text="⚡ ĐIỀU KHIỂN & BẢN TIN GHI (MODBUS FUNCTION 16 - 4 THANH GHI)",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=11, weight="bold"),
            text_color=COLOR_TEXT_WHITE
        ).pack(side="left")

        # Nút ghi tức thời và công tắc ghi lặp
        self.sw_cyclic_write = ctk.CTkSwitch(
            header,
            text="Ghi chu kỳ (Cyclic Write)",
            font=ctk.CTkFont(size=10, weight="bold"),
            progress_color=VIETTEL_RED,
            command=self._on_toggle_cyclic_write
        )
        self.sw_cyclic_write.pack(side="right", padx=5)

        self.btn_send_write = ctk.CTkButton(
            header,
            text="⚡ GỬI LỆNH GHI (F=16)",
            width=150,
            height=28,
            fg_color=VIETTEL_RED,
            hover_color=VIETTEL_RED_HOVER,
            font=ctk.CTkFont(family=FONT_PRIMARY, size=11, weight="bold"),
            command=self._send_write_command
        )
        self.btn_send_write.pack(side="right", padx=10)

        # Lưới 4 cột điều khiển tương ứng 4 thanh ghi
        grid_ctrl = ctk.CTkFrame(ctrl_box, fg_color="transparent")
        grid_ctrl.pack(fill="x", padx=12, pady=(4, 10))
        for col in range(4):
            grid_ctrl.grid_columnconfigure(col, weight=1)

        # CỘT 0: SET_POSITION (Thanh ghi 0)
        c0 = ctk.CTkFrame(
            grid_ctrl, fg_color=COLOR_CARD_INNER, corner_radius=6,
            border_width=1, border_color=COLOR_BORDER_SUBTLE
        )
        c0.grid(row=0, column=0, padx=4, pady=2, sticky="nsew")

        ctk.CTkLabel(
            c0, text="1. VỊ TRÍ ĐẶT (Set_Position)",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=10, weight="bold"), text_color=COLOR_TEXT_WHITE
        ).pack(pady=(6, 2))

        row_pos_input = ctk.CTkFrame(c0, fg_color="transparent")
        row_pos_input.pack(fill="x", padx=8, pady=2)
        self.ent_set_position = ctk.CTkEntry(
            row_pos_input, width=75, font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            border_color=COLOR_BORDER, fg_color=COLOR_ROW_ALT1
        )
        self.ent_set_position.insert(0, "0")
        self.ent_set_position.pack(side="left", padx=2)
        ctk.CTkLabel(
            row_pos_input, text="mm (-1700..1700)", font=ctk.CTkFont(size=9), text_color=COLOR_TEXT_GRAY
        ).pack(side="left", padx=2)

        self.slider_pos = ctk.CTkSlider(
            c0,
            from_=-1700,
            to=1700,
            number_of_steps=3400,
            command=self._on_pos_slider_moved,
            button_color=VIETTEL_RED,
            button_hover_color=VIETTEL_RED_HOVER,
            progress_color=VIETTEL_RED
        )
        self.slider_pos.set(0)
        self.slider_pos.pack(fill="x", padx=8, pady=4)

        # Nút vị trí nhanh
        p_row = ctk.CTkFrame(c0, fg_color="transparent")
        p_row.pack(fill="x", padx=6, pady=(0, 6))
        for p_val in [-1700, -850, 0, 850, 1700]:
            ctk.CTkButton(
                p_row, text=f"{p_val}", width=32, height=20,
                font=ctk.CTkFont(family="Consolas", size=8, weight="bold"),
                fg_color="#223042", hover_color=VIETTEL_RED,
                command=lambda val=p_val: self._preset_pos(val)
            ).pack(side="left", padx=1, expand=True)

        # CỘT 1: STATE (Thanh ghi 1)
        c1 = ctk.CTkFrame(
            grid_ctrl, fg_color=COLOR_CARD_INNER, corner_radius=6,
            border_width=1, border_color=COLOR_BORDER_SUBTLE
        )
        c1.grid(row=0, column=1, padx=4, pady=2, sticky="nsew")

        ctk.CTkLabel(
            c1, text="2. TRẠNG THÁI (State)",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=10, weight="bold"), text_color=COLOR_TEXT_WHITE
        ).pack(pady=(6, 2))

        self.lbl_cmd_state_badge = ctk.CTkLabel(
            c1, text="LỆNH: TẮT (0)",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=11, weight="bold"), text_color=VIETTEL_RED
        )
        self.lbl_cmd_state_badge.pack(pady=4)

        btn_row_st = ctk.CTkFrame(c1, fg_color="transparent")
        btn_row_st.pack(fill="x", padx=8, pady=4)

        self.btn_state_on = ctk.CTkButton(
            btn_row_st, text="🟢 BẬT (1)", width=75, height=26,
            fg_color="#223042", hover_color=COLOR_SUCCESS_HOVER,
            font=ctk.CTkFont(family=FONT_PRIMARY, size=10, weight="bold"),
            command=lambda: self._set_cmd_state(1)
        )
        self.btn_state_on.pack(side="left", padx=3, expand=True)

        self.btn_state_off = ctk.CTkButton(
            btn_row_st, text="🔴 TẮT (0)", width=75, height=26,
            fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER,
            font=ctk.CTkFont(family=FONT_PRIMARY, size=10, weight="bold"),
            command=lambda: self._set_cmd_state(0)
        )
        self.btn_state_off.pack(side="left", padx=3, expand=True)

        self.cmd_state_val = 0

        # CỘT 2: SEL_TEST (Thanh ghi 2)
        c2 = ctk.CTkFrame(
            grid_ctrl, fg_color=COLOR_CARD_INNER, corner_radius=6,
            border_width=1, border_color=COLOR_BORDER_SUBTLE
        )
        c2.grid(row=0, column=2, padx=4, pady=2, sticky="nsew")

        ctk.CTkLabel(
            c2, text="3. TỰ KIỂM TRA (Sel_test)",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=10, weight="bold"), text_color=COLOR_TEXT_WHITE
        ).pack(pady=(6, 2))

        self.lbl_cmd_test_badge = ctk.CTkLabel(
            c2, text="SELF-TEST: TẮT (0)",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=11, weight="bold"), text_color=VIETTEL_RED
        )
        self.lbl_cmd_test_badge.pack(pady=4)

        btn_row_test = ctk.CTkFrame(c2, fg_color="transparent")
        btn_row_test.pack(fill="x", padx=8, pady=4)

        self.btn_test_on = ctk.CTkButton(
            btn_row_test, text="🟢 BẬT (1)", width=75, height=26,
            fg_color="#223042", hover_color=COLOR_SUCCESS_HOVER,
            font=ctk.CTkFont(family=FONT_PRIMARY, size=10, weight="bold"),
            command=lambda: self._set_cmd_sel_test(1)
        )
        self.btn_test_on.pack(side="left", padx=3, expand=True)

        self.btn_test_off = ctk.CTkButton(
            btn_row_test, text="🔴 TẮT (0)", width=75, height=26,
            fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER,
            font=ctk.CTkFont(family=FONT_PRIMARY, size=10, weight="bold"),
            command=lambda: self._set_cmd_sel_test(0)
        )
        self.btn_test_off.pack(side="left", padx=3, expand=True)

        self.cmd_sel_test_val = 0

        self.lbl_test_mode_desc = ctk.CTkLabel(
            c2, text="Sel_test = 0 (Tắt tự kiểm tra)",
            font=ctk.CTkFont(size=9), text_color=COLOR_SUCCESS_GLOW
        )
        self.lbl_test_mode_desc.pack(pady=(0, 6))

        # CỘT 3: PERIOD (Thanh ghi 3)
        c3 = ctk.CTkFrame(
            grid_ctrl, fg_color=COLOR_CARD_INNER, corner_radius=6,
            border_width=1, border_color=COLOR_BORDER_SUBTLE
        )
        c3.grid(row=0, column=3, padx=4, pady=2, sticky="nsew")

        ctk.CTkLabel(
            c3, text="4. CHU KỲ (Period ms)",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=10, weight="bold"), text_color=COLOR_TEXT_WHITE
        ).pack(pady=(6, 2))

        row_period = ctk.CTkFrame(c3, fg_color="transparent")
        row_period.pack(fill="x", padx=8, pady=2)

        self.ent_period = ctk.CTkEntry(
            row_period, width=75, font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
            border_color=COLOR_BORDER, fg_color=COLOR_ROW_ALT1
        )
        self.ent_period.insert(0, "500")
        self.ent_period.pack(side="left", padx=2)
        ctk.CTkLabel(
            row_period, text="ms (100..2000)", font=ctk.CTkFont(size=9), text_color=COLOR_TEXT_GRAY
        ).pack(side="left", padx=2)

        t_row = ctk.CTkFrame(c3, fg_color="transparent")
        t_row.pack(fill="x", padx=6, pady=(4, 6))
        for t_val in [100, 200, 500, 1000, 2000]:
            ctk.CTkButton(
                t_row, text=f"{t_val}", width=32, height=20,
                font=ctk.CTkFont(family="Consolas", size=8, weight="bold"),
                fg_color="#223042", hover_color=VIETTEL_RED,
                command=lambda val=t_val: self._preset_period(val)
            ).pack(side="left", padx=1, expand=True)

    # -------------------------------------------------------------------------
    # 4. BẢNG CHI TIẾT 7 THANH GHI ĐỌC & 4 THANH GHI GHI
    # -------------------------------------------------------------------------
    def _build_registers_tables(self):
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="x", padx=10, pady=4)
        container.grid_columnconfigure(0, weight=3)
        container.grid_columnconfigure(1, weight=2)

        # BẢNG 7 THANH GHI ĐỌC (BẢN TIN ĐỌC F=03)
        box_read = ctk.CTkFrame(
            container, fg_color=COLOR_CARD_BG, corner_radius=8,
            border_width=1, border_color=COLOR_BORDER
        )
        box_read.grid(row=0, column=0, padx=(0, 4), pady=2, sticky="nsew")

        r_head = ctk.CTkFrame(box_read, fg_color="#182332", height=28, corner_radius=4)
        r_head.pack(fill="x", padx=6, pady=(6, 4))
        ctk.CTkLabel(
            r_head, text="📋 BẢN TIN ĐỌC — 7 THANH GHI (FUNCTION 03)",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=10, weight="bold"), text_color=COLOR_TEXT_WHITE
        ).pack(side="left", padx=8)

        cols_spec = [("Địa chỉ", 55), ("Tên thanh ghi", 100), ("DEC", 80), ("HEX", 75), ("Mô tả / Đơn vị", 150)]
        head_row = ctk.CTkFrame(box_read, fg_color="#1F2937", height=24, corner_radius=4)
        head_row.pack(fill="x", padx=6, pady=(0, 2))
        for col_name, w in cols_spec:
            ctk.CTkLabel(
                head_row, text=col_name, width=w,
                font=ctk.CTkFont(family=FONT_PRIMARY, size=9, weight="bold"), text_color=COLOR_TEXT_GRAY
            ).pack(side="left", padx=2)

        for reg in MLD_READ_REGISTERS:
            idx = reg["index"]
            row_bg = COLOR_ROW_ALT1 if idx % 2 == 0 else COLOR_ROW_ALT2
            row = ctk.CTkFrame(box_read, fg_color=row_bg, height=24, corner_radius=3)
            row.pack(fill="x", padx=6, pady=1)

            ctk.CTkLabel(
                row, text=f"Reg #{idx}", width=55,
                font=ctk.CTkFont(family="Consolas", size=9, weight="bold"), text_color=COLOR_TEXT_MUTED
            ).pack(side="left", padx=2)
            ctk.CTkLabel(
                row, text=reg["name"], width=100,
                font=ctk.CTkFont(family=FONT_PRIMARY, size=9, weight="bold"), text_color=COLOR_TEXT_WHITE, anchor="w"
            ).pack(side="left", padx=2)

            lbl_val = ctk.CTkLabel(
                row, text="0", width=80,
                font=ctk.CTkFont(family="Consolas", size=10, weight="bold"), text_color=COLOR_SUCCESS_GLOW, anchor="e"
            )
            lbl_val.pack(side="left", padx=2)

            lbl_hex = ctk.CTkLabel(
                row, text="0x0000", width=75,
                font=ctk.CTkFont(family="Consolas", size=9), text_color=COLOR_WARNING_LIGHT, anchor="e"
            )
            lbl_hex.pack(side="left", padx=2)

            ctk.CTkLabel(
                row, text=f"{reg['desc']} ({reg['unit']})", width=150,
                font=ctk.CTkFont(size=8), text_color=COLOR_TEXT_GRAY, anchor="w"
            ).pack(side="left", padx=6)

            self.read_row_labels[idx] = {"val": lbl_val, "hex": lbl_hex}

        # BẢNG 4 THANH GHI GHI (BẢN TIN GHI F=16)
        box_write = ctk.CTkFrame(
            container, fg_color=COLOR_CARD_BG, corner_radius=8,
            border_width=1, border_color=COLOR_BORDER
        )
        box_write.grid(row=0, column=1, padx=(4, 0), pady=2, sticky="nsew")

        w_head = ctk.CTkFrame(box_write, fg_color="#182332", height=28, corner_radius=4)
        w_head.pack(fill="x", padx=6, pady=(6, 4))
        ctk.CTkLabel(
            w_head, text="📤 BẢN TIN GHI — 4 THANH GHI (FUNCTION 16)",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=10, weight="bold"), text_color=COLOR_TEXT_WHITE
        ).pack(side="left", padx=8)

        w_cols = [("Địa chỉ", 55), ("Tên thanh ghi", 95), ("DEC", 70), ("HEX", 70), ("Đơn vị", 80)]
        head_w_row = ctk.CTkFrame(box_write, fg_color="#1F2937", height=24, corner_radius=4)
        head_w_row.pack(fill="x", padx=6, pady=(0, 2))
        for col_name, w in w_cols:
            ctk.CTkLabel(
                head_w_row, text=col_name, width=w,
                font=ctk.CTkFont(family=FONT_PRIMARY, size=9, weight="bold"), text_color=COLOR_TEXT_GRAY
            ).pack(side="left", padx=2)

        for reg in MLD_WRITE_REGISTERS:
            idx = reg["index"]
            row_bg = COLOR_ROW_ALT1 if idx % 2 == 0 else COLOR_ROW_ALT2
            row = ctk.CTkFrame(box_write, fg_color=row_bg, height=24, corner_radius=3)
            row.pack(fill="x", padx=6, pady=1)

            ctk.CTkLabel(
                row, text=f"Reg #{idx}", width=55,
                font=ctk.CTkFont(family="Consolas", size=9, weight="bold"), text_color=COLOR_TEXT_MUTED
            ).pack(side="left", padx=2)
            ctk.CTkLabel(
                row, text=reg["name"], width=95,
                font=ctk.CTkFont(family=FONT_PRIMARY, size=9, weight="bold"), text_color=COLOR_TEXT_WHITE, anchor="w"
            ).pack(side="left", padx=2)

            lbl_val = ctk.CTkLabel(
                row, text=f"{reg['default']}", width=70,
                font=ctk.CTkFont(family="Consolas", size=10, weight="bold"), text_color=COLOR_CYAN, anchor="e"
            )
            lbl_val.pack(side="left", padx=2)

            lbl_hex = ctk.CTkLabel(
                row, text=f"0x{(reg['default'] & 0xFFFF):04X}", width=70,
                font=ctk.CTkFont(family="Consolas", size=9), text_color=COLOR_WARNING_LIGHT, anchor="e"
            )
            lbl_hex.pack(side="left", padx=2)

            ctk.CTkLabel(
                row, text=reg["unit"], width=80,
                font=ctk.CTkFont(size=8), text_color=COLOR_TEXT_GRAY, anchor="w"
            ).pack(side="left", padx=4)

            self.write_row_labels[idx] = {"val": lbl_val, "hex": lbl_hex}

    # -------------------------------------------------------------------------
    # 5. ĐỒ THỊ BÁM VỊ TRÍ THỜI GIAN THỰC (REAL-TIME TRACKING CHART)
    # -------------------------------------------------------------------------
    def _build_chart_section(self):
        chart_box = ctk.CTkFrame(
            self, fg_color=COLOR_CARD_BG, corner_radius=8,
            border_width=1, border_color=COLOR_BORDER
        )
        chart_box.pack(fill="x", padx=10, pady=(4, 8))

        chart_ctrl = ctk.CTkFrame(chart_box, fg_color="transparent")
        chart_ctrl.pack(fill="x", padx=10, pady=(6, 4))

        ctk.CTkLabel(
            chart_ctrl,
            text="📈 ĐỒ THỊ BÁM VỊ TRÍ & ĐÁP ỨNG THỜI GIAN THỰC MLD (Position vs Set_Position)",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=10, weight="bold"),
            text_color=COLOR_TEXT_WHITE
        ).pack(side="left")

        # Checkboxes bật tắt đường vẽ
        self.chk_pos = ctk.CTkCheckBox(chart_ctrl, text="Position", font=ctk.CTkFont(size=9, weight="bold"), text_color=COLOR_SUCCESS_GLOW, fg_color=COLOR_SUCCESS, checkmark_color="#000000", width=70)
        self.chk_pos.select()
        self.chk_pos.pack(side="left", padx=6)

        self.chk_setpos = ctk.CTkCheckBox(chart_ctrl, text="Set_Position", font=ctk.CTkFont(size=9, weight="bold"), text_color=COLOR_WARNING_LIGHT, fg_color=COLOR_WARNING, checkmark_color="#000000", width=85)
        self.chk_setpos.select()
        self.chk_setpos.pack(side="left", padx=6)

        self.chk_speed = ctk.CTkCheckBox(chart_ctrl, text="Speed/10", font=ctk.CTkFont(size=9, weight="bold"), text_color="#38BDF8", fg_color="#38BDF8", checkmark_color="#000000", width=70)
        self.chk_speed.select()
        self.chk_speed.pack(side="left", padx=6)

        self.chk_vdc = ctk.CTkCheckBox(chart_ctrl, text="Vdc_bus", font=ctk.CTkFont(size=9, weight="bold"), text_color=VIETTEL_RED_LIGHT, fg_color=VIETTEL_RED, width=70)
        self.chk_vdc.select()
        self.chk_vdc.pack(side="left", padx=6)

        # Các nút điều khiển đồ thị
        self.btn_record = ctk.CTkButton(chart_ctrl, text="🔴 Ghi log CSV", width=95, height=22, fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER, font=ctk.CTkFont(size=9, weight="bold"), command=self._toggle_recording)
        self.btn_record.pack(side="right", padx=3)

        self.btn_clear_chart = ctk.CTkButton(chart_ctrl, text="Xóa đồ thị", width=70, height=22, fg_color="#223042", hover_color="#33465C", font=ctk.CTkFont(size=9), command=self._clear_chart)
        self.btn_clear_chart.pack(side="right", padx=3)

        self.btn_pause_chart = ctk.CTkButton(chart_ctrl, text="Tạm dừng", width=70, height=22, fg_color="#223042", hover_color="#33465C", font=ctk.CTkFont(size=9), command=self._toggle_pause_chart)
        self.btn_pause_chart.pack(side="right", padx=3)

        # Khung đồ thị Matplotlib
        self.fig = Figure(figsize=(8, 2.5), dpi=100, facecolor=COLOR_CARD_INNER)
        self.ax = self.fig.add_subplot(111)
        self.ax.set_facecolor("#080B0F")
        self.ax.tick_params(colors="#94A3B8", labelsize=8)
        self.ax.grid(True, linestyle="--", alpha=0.2, color="#334155")

        for spine in self.ax.spines.values():
            spine.set_color("#1E293B")

        self.line_pos, = self.ax.plot([], [], label="Position (mm)", color=COLOR_SUCCESS_GLOW, linewidth=1.8)
        self.line_setpos, = self.ax.plot([], [], label="Set_Position (mm)", color=COLOR_WARNING_LIGHT, linewidth=1.5, linestyle="--")
        self.line_speed, = self.ax.plot([], [], label="Speed / 10", color="#38BDF8", linewidth=1.4)
        self.line_vdc, = self.ax.plot([], [], label="Vdc_bus (V)", color=VIETTEL_RED_LIGHT, linewidth=1.4)
        self.ax.legend(loc="upper left", ncol=4, facecolor="#141B24", edgecolor=COLOR_BORDER, labelcolor=COLOR_TEXT_WHITE, fontsize=8)

        self.canvas = FigureCanvasTkAgg(self.fig, master=chart_box)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=4, pady=(2, 6))

    # -------------------------------------------------------------------------
    # HÀNH ĐỘNG ĐIỀU KHIỂN & GỬI LỆNH MODBUS MLD
    # -------------------------------------------------------------------------
    def _on_pos_slider_moved(self, val):
        pos_int = int(round(val))
        pos_int = max(-1700, min(1700, pos_int))
        self.ent_set_position.delete(0, "end")
        self.ent_set_position.insert(0, str(pos_int))

    def _preset_pos(self, val: int):
        val = max(-1700, min(1700, val))
        self.slider_pos.set(val)
        self.ent_set_position.delete(0, "end")
        self.ent_set_position.insert(0, str(val))
        self._send_write_command()

    def _preset_period(self, val: int):
        val = max(100, min(2000, val))
        self.ent_period.delete(0, "end")
        self.ent_period.insert(0, str(val))
        self._send_write_command()

    def _set_cmd_state(self, state_val: int):
        self.cmd_state_val = 1 if state_val != 0 else 0
        if self.cmd_state_val == 1:
            self.lbl_cmd_state_badge.configure(text="LỆNH: BẬT (1)", text_color=COLOR_SUCCESS_GLOW)
            self.btn_state_on.configure(fg_color=COLOR_SUCCESS, hover_color=COLOR_SUCCESS_HOVER)
            self.btn_state_off.configure(fg_color="#223042", hover_color="#33465C")
        else:
            self.lbl_cmd_state_badge.configure(text="LỆNH: TẮT (0)", text_color=VIETTEL_RED)
            self.btn_state_on.configure(fg_color="#223042", hover_color="#33465C")
            self.btn_state_off.configure(fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER)
        self._send_write_command()

    def _set_cmd_sel_test(self, test_val: int):
        self.cmd_sel_test_val = 1 if test_val != 0 else 0
        if self.cmd_sel_test_val == 1:
            self.lbl_cmd_test_badge.configure(text="SELF-TEST: BẬT (1)", text_color=COLOR_SUCCESS_GLOW)
            self.lbl_test_mode_desc.configure(text="Sel_test = 1 (Bật tự kiểm tra)", text_color=COLOR_WARNING_LIGHT)
            self.btn_test_on.configure(fg_color=COLOR_SUCCESS, hover_color=COLOR_SUCCESS_HOVER)
            self.btn_test_off.configure(fg_color="#223042", hover_color="#33465C")
        else:
            self.lbl_cmd_test_badge.configure(text="SELF-TEST: TẮT (0)", text_color=VIETTEL_RED)
            self.lbl_test_mode_desc.configure(text="Sel_test = 0 (Tắt tự kiểm tra)", text_color=COLOR_SUCCESS_GLOW)
            self.btn_test_on.configure(fg_color="#223042", hover_color="#33465C")
            self.btn_test_off.configure(fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER)
        self._send_write_command()

    def _on_toggle_cyclic_write(self):
        is_cyclic = (self.sw_cyclic_write.get() == 1)
        if hasattr(self.conn, 'set_mld_cyclic_write'):
            self.conn.set_mld_cyclic_write(is_cyclic)

    def _send_write_command(self):
        """Gửi lệnh ghi 4 thanh ghi Function 16 qua kết nối Modbus"""
        try:
            set_pos = int(self.ent_set_position.get().strip())
        except Exception:
            set_pos = 0
        set_pos = max(-1700, min(1700, set_pos))
        self.slider_pos.set(set_pos)

        state = self.cmd_state_val
        sel_test = self.cmd_sel_test_val

        try:
            period_ms = int(self.ent_period.get().strip())
        except Exception:
            period_ms = 500
        period_ms = max(100, min(2000, period_ms))

        # Cập nhật hiển thị bảng ghi
        vals = [set_pos, state, sel_test, period_ms]
        for idx, v in enumerate(vals):
            if idx in self.write_row_labels:
                _safe_configure_label(self.write_row_labels[idx]["val"], f"{v}")
                _safe_configure_label(self.write_row_labels[idx]["hex"], f"0x{(v & 0xFFFF):04X}")

        if hasattr(self.conn, 'write_mld_command'):
            self.conn.write_mld_command(set_pos, state, sel_test, period_ms, immediate=True)

    # -------------------------------------------------------------------------
    # GHI LOG CSV & ĐIỀU KHIỂN ĐỒ THỊ
    # -------------------------------------------------------------------------
    def _toggle_pause_chart(self):
        self.is_monitoring = not self.is_monitoring
        self.btn_pause_chart.configure(
            text="Tiếp tục" if not self.is_monitoring else "Tạm dừng",
            fg_color=COLOR_BLUE_SEL if not self.is_monitoring else "#223042"
        )

    def _clear_chart(self):
        self.t_data.clear()
        self.pos_data.clear()
        self.set_pos_data.clear()
        self.speed_data.clear()
        self.vdc_data.clear()
        self.line_pos.set_data([], [])
        self.line_setpos.set_data([], [])
        self.line_speed.set_data([], [])
        self.line_vdc.set_data([], [])
        self.canvas.draw()

    def _toggle_recording(self):
        if not self.recording_file:
            os.makedirs("datalogger", exist_ok=True)
            fname = os.path.join("datalogger", f"MLD_Log_{time.strftime('%Y%m%d_%H%M%S')}.csv")
            try:
                self.recording_file = open(fname, "w", newline="", encoding="utf-8")
                self.csv_writer = csv.writer(self.recording_file)
                self.csv_writer.writerow([
                    "Timestamp", "Time_ms",
                    "State", "Position", "Vdc_bus", "Error_code", "Set_Position_Read", "Speed", "Hall_Value",
                    "Cmd_Set_Position", "Cmd_State", "Cmd_Sel_test", "Cmd_Period_ms"
                ])
                self.btn_record.configure(text="⏹ Dừng ghi CSV", fg_color=COLOR_SUCCESS, hover_color=COLOR_SUCCESS_HOVER)
                self.record_start_time = time.time()
            except Exception as e:
                messagebox.showerror("Lỗi mở file", f"Không thể tạo file ghi log CSV: {e}")
        else:
            try:
                self.recording_file.close()
            except Exception:
                pass
            self.recording_file = None
            self.csv_writer = None
            self.btn_record.configure(text="🔴 Ghi log CSV", fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER)
            messagebox.showinfo("Hoàn thành ghi log", "Đã lưu bản ghi telemetry MLD an toàn vào thư mục datalogger!")

    def log_csv_record(self, d: Dict[str, Any]):
        """Ghi dữ liệu CSV độc lập với việc tab đang mở hay đang ẩn"""
        if self.csv_writer and self.recording_file:
            try:
                st = d.get("mld_state", 0)
                pos = d.get("mld_position", 0)
                vdc = d.get("mld_vdc_bus", 0)
                err = d.get("mld_error_code", 0)
                set_pos = d.get("mld_set_position", 0)
                spd = d.get("mld_speed", 0)
                hall = d.get("mld_hall_value", 0)

                w_regs = d.get("mld_write_regs", [0, 0, 0, 500])
                while len(w_regs) < 4:
                    w_regs.append(0)

                self.csv_writer.writerow([
                    time.strftime("%Y-%m-%d %H:%M:%S"),
                    d.get("time_ms", 0),
                    st, pos, vdc, err, set_pos, spd, hall,
                    w_regs[0], w_regs[1], w_regs[2], w_regs[3]
                ])
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # CẬP NHẬT TELEMETRY (GỌI ĐỊNH KỲ TỪ MAIN THREAD KHI TAB MLD ĐANG MỞ)
    # -------------------------------------------------------------------------
    def update_telemetry(self, d: Dict[str, Any]):
        sid = d.get("slave_id", 1)
        sr = d.get("scan_rate_ms", 500)
        r_tx = d.get("read_tx", 0)
        r_err = d.get("read_err", 0)
        w_tx = d.get("write_tx", 0)
        w_err = d.get("write_err", 0)

        _safe_configure_label(self.lbl_read_stat, f"Tx = {r_tx}: Err = {r_err}: ID = {sid}: F = 03: SR = {sr}ms (7 Regs)")
        _safe_configure_label(self.lbl_write_stat, f"Tx = {w_tx}: Err = {w_err}: ID = {sid}: F = 16 (4 Regs)")

        if d.get("last_read_tx_hex"):
            _safe_configure_label(self.lbl_read_tx_hex, f"[TX F=03] >> {d['last_read_tx_hex']}")
        if d.get("last_read_rx_hex"):
            _safe_configure_label(self.lbl_read_rx_hex, f"[RX F=03] << {d['last_read_rx_hex']}")
        if d.get("last_write_tx_hex"):
            _safe_configure_label(self.lbl_write_tx_hex, f"[TX F=16] >> {d['last_write_tx_hex']}")

        # 1. TRÍCH XUẤT 7 THANH GHI BẢN TIN ĐỌC
        mld_read = d.get("mld_read_regs", [])
        if not mld_read or len(mld_read) < 7:
            st = d.get("mld_state", 0)
            pos = d.get("mld_position", 0)
            vdc = d.get("mld_vdc_bus", 48)
            err = d.get("mld_error_code", 0)
            set_pos = d.get("mld_set_position", 0)
            spd = d.get("mld_speed", 0)
            hall = d.get("mld_hall_value", 1)
            mld_read = [st, pos, vdc, err, set_pos, spd, hall]
        else:
            st, pos, vdc, err, set_pos, spd, hall = mld_read[:7]

        # Cập nhật 7 Hero cards
        st_text = "🟢 RUN (1)" if st == 1 else "⚪ IDLE (0)" if st == 0 else f"🔴 FAULT ({st})"
        st_color = COLOR_SUCCESS_GLOW if st == 1 else COLOR_TEXT_WHITE if st == 0 else VIETTEL_RED
        _safe_configure_label(self.hero_labels["state"], st_text, st_color)
        _safe_configure_label(self.hero_labels["position"], f"{pos}")
        _safe_configure_label(self.hero_labels["vdc_bus"], f"{vdc:.1f}" if isinstance(vdc, float) else f"{vdc}")
        _safe_configure_label(self.hero_labels["error_code"], "0 (OK)" if err == 0 else f"ERR ({err})", COLOR_SUCCESS_GLOW if err == 0 else VIETTEL_RED)
        _safe_configure_label(self.hero_labels["set_pos_read"], f"{set_pos}")
        _safe_configure_label(self.hero_labels["speed"], f"{spd}")
        _safe_configure_label(self.hero_labels["hall_val"], f"{hall} (0b{hall:03b})")

        # Cập nhật bảng 7 thanh ghi đọc
        for idx, val in enumerate(mld_read[:7]):
            if idx in self.read_row_labels:
                _safe_configure_label(self.read_row_labels[idx]["val"], f"{val}")
                _safe_configure_label(self.read_row_labels[idx]["hex"], f"0x{(val & 0xFFFF):04X}")

        # Ghi log CSV nếu đang bật
        self.log_csv_record(d)

        # Cập nhật đồ thị (tối đa 10 FPS và chỉ khi tab đang hiển thị)
        if not self.is_monitoring:
            return

        now = time.time()
        self.t_data.append(now)
        self.pos_data.append(pos)
        self.set_pos_data.append(set_pos)
        self.speed_data.append(spd / 10.0)
        self.vdc_data.append(vdc)

        if len(self.t_data) > self.max_points:
            self.t_data.pop(0)
            self.pos_data.pop(0)
            self.set_pos_data.pop(0)
            self.speed_data.pop(0)
            self.vdc_data.pop(0)

        if self.winfo_viewable() and (now - self._last_chart_redraw >= 0.10):
            self._last_chart_redraw = now
            t_rel = [t - self.t_data[0] for t in self.t_data]
            self.line_pos.set_data(t_rel, self.pos_data if self.chk_pos.get() else [])
            self.line_setpos.set_data(t_rel, self.set_pos_data if self.chk_setpos.get() else [])
            self.line_speed.set_data(t_rel, self.speed_data if self.chk_speed.get() else [])
            self.line_vdc.set_data(t_rel, self.vdc_data if self.chk_vdc.get() else [])

            self.ax.relim()
            self.ax.autoscale_view(True, True, True)
            self.canvas.draw_idle()
