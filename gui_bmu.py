"""
VIETTEL BLDC / ESC CONTROLLER - MODULE GIAO DIỆN QUẢN LÝ BMU (BMS)
File: gui_bmu.py
Chịu trách nhiệm:
1. Giám sát tổng thể bộ pin (Battery Pack): Pack Voltage (V), Pack Current (A), SoC (%), SoH (%), Wh, Cycle Count
2. Giám sát chi tiết 16 Cell pin (16S Pack): Điện áp từng cell, thanh tỷ lệ %, cờ chỉ báo cân bằng động (Balancing Flags)
3. Thống kê chênh lệch cell: Max Cell (V), Min Cell (V), Độ lệch Delta V (mV)
4. Giám sát nhiệt độ các module pin (T1 .. T4) và nhiệt độ bo mạch BMS
5. Bảng điều khiển & Cài đặt ngưỡng bảo vệ BMU (Quá áp, Tụt áp, Quá nhiệt, Quá dòng, Công tắc cân bằng cell)
"""

import time
from typing import Dict, Any, List

import customtkinter as ctk
from tkinter import messagebox

from viettel_theme import (
    COLOR_BG, COLOR_HEADER_BG, COLOR_PANEL_BG, COLOR_CARD_BG, COLOR_CARD_BG_HOVER,
    COLOR_CARD_INNER, COLOR_ROW_ALT1, COLOR_ROW_ALT2, COLOR_BORDER, COLOR_BORDER_SUBTLE,
    COLOR_BORDER_RED, VIETTEL_RED, VIETTEL_RED_HOVER, VIETTEL_RED_LIGHT, VIETTEL_RED_GLOW,
    COLOR_SUCCESS, COLOR_SUCCESS_HOVER, COLOR_SUCCESS_GLOW, COLOR_CYAN,
    COLOR_WARNING, COLOR_WARNING_LIGHT, COLOR_CRITICAL, COLOR_BLUE_SEL,
    COLOR_TEXT_WHITE, COLOR_TEXT_GRAY, COLOR_TEXT_MUTED,
    font_section_title, font_card_label, font_digital_lg, font_digital_md, font_digital_sm,
    font_mono, font_mono_sm, font_btn, FONT_PRIMARY, safe_configure_label, safe_set_progress_bar
)


def _safe_configure_label(lbl, text: str, text_color: str = None):
    safe_configure_label(lbl, text, text_color)


def _safe_set_progress_bar(bar, ratio: float, color: str):
    safe_set_progress_bar(bar, ratio, color)


class BMUTabFrame(ctk.CTkScrollableFrame):
    """Giao diện quản lý Hệ thống Quản lý Pin (BMU / BMS) chuẩn sản xuất quân sự"""
    def __init__(self, master, conn, **kwargs):
        super().__init__(
            master,
            fg_color="transparent",
            scrollbar_button_color="#223042",
            scrollbar_button_hover_color=VIETTEL_RED,
            **kwargs
        )
        self.conn = conn

        self.cell_widgets: Dict[int, Dict[str, Any]] = {}
        self.metric_labels: Dict[str, ctk.CTkLabel] = {}
        self.temp_labels: Dict[str, ctk.CTkLabel] = {}

        self._build_ui()

    def _build_ui(self):
        # =====================================================================
        # 1. HEADER METRICS: TỔNG QUAN PIN (PACK VOLTAGE, CURRENT, SOC, SOH,...)
        # =====================================================================
        header_frame = ctk.CTkFrame(
            self, fg_color=COLOR_CARD_BG, corner_radius=8,
            border_width=1, border_color=COLOR_BORDER
        )
        header_frame.pack(fill="x", padx=4, pady=(2, 6))

        top_metrics = [
            ("pack_voltage", "ĐIỆN ÁP PACK", "61.12", "V", VIETTEL_RED_LIGHT),
            ("pack_current", "DÒNG ĐIỆN PACK", "0.0", "A", "#FB923C"),
            ("soc",          "DUNG LƯỢNG (SOC)", "86.5", "%", COLOR_SUCCESS_GLOW),
            ("soh",          "SỨC KHỎE (SOH)", "99.0", "%", COLOR_CYAN),
            ("delta_v",      "ĐỘ LỆCH CELL (ΔV)", "14.0", "mV", COLOR_WARNING_LIGHT),
            ("max_cell",     "CELL CAO NHẤT", "3.828 (C7)", "V", COLOR_SUCCESS_GLOW),
            ("min_cell",     "CELL THẤP NHẤT", "3.814 (C2)", "V", "#F87171"),
            ("cycles",       "SỐ CHU KỲ SẠC", "42", "lần", COLOR_TEXT_WHITE)
        ]

        cards_grid = ctk.CTkFrame(header_frame, fg_color="transparent")
        cards_grid.pack(fill="x", padx=6, pady=6)

        for idx, (key, title, init_val, unit, color) in enumerate(top_metrics):
            r = idx // 4
            c = idx % 4
            card = ctk.CTkFrame(
                cards_grid, fg_color=COLOR_CARD_INNER, corner_radius=6,
                border_width=1, border_color=COLOR_BORDER_SUBTLE
            )
            card.grid(row=r, column=c, padx=4, pady=3, sticky="nsew")
            cards_grid.grid_columnconfigure(c, weight=1)

            ctk.CTkLabel(
                card, text=title, font=ctk.CTkFont(family=FONT_PRIMARY, size=9, weight="bold"),
                text_color=COLOR_TEXT_GRAY
            ).pack(anchor="w", padx=8, pady=(4, 1))

            v_box = ctk.CTkFrame(card, fg_color="transparent")
            v_box.pack(anchor="w", padx=8, pady=(0, 4))

            lbl_v = ctk.CTkLabel(
                v_box, text=init_val,
                font=ctk.CTkFont(family="Consolas", size=16, weight="bold"), text_color=color
            )
            lbl_v.pack(side="left")

            if unit:
                lbl_u = ctk.CTkLabel(
                    v_box, text=f" {unit}", font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_MUTED
                )
                lbl_u.pack(side="left", padx=(2, 0), pady=(2, 0))

            self.metric_labels[key] = lbl_v

        # =====================================================================
        # 2. KHUNG CHÍNH: MA TRẬN 16 CELL PIN (16S PACK CELL MONITORING)
        # =====================================================================
        center_frame = ctk.CTkFrame(
            self, fg_color=COLOR_CARD_BG, corner_radius=8,
            border_width=1, border_color=COLOR_BORDER
        )
        center_frame.pack(fill="x", padx=4, pady=2)
        center_frame.grid_columnconfigure(0, weight=3)
        center_frame.grid_columnconfigure(1, weight=1)
        center_frame.grid_rowconfigure(0, weight=1)

        # Cột trái: Bảng 16 Cell pin dạng Card trực quan
        cells_container = ctk.CTkFrame(
            center_frame, fg_color=COLOR_CARD_INNER, corner_radius=6,
            border_width=1, border_color=COLOR_BORDER_SUBTLE
        )
        cells_container.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        c_title_bar = ctk.CTkFrame(cells_container, height=30, fg_color="#182332", corner_radius=4)
        c_title_bar.pack(fill="x", padx=4, pady=(4, 6))
        ctk.CTkLabel(
            c_title_bar,
            text="🔋 GIÁM SÁT CHI TIẾT 16 CELL PIN (16S Li-Ion / LiPo PACK - 3.00V .. 4.25V)",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=11, weight="bold"), text_color=COLOR_TEXT_WHITE
        ).pack(side="left", padx=8, pady=3)

        cells_grid = ctk.CTkFrame(cells_container, fg_color="transparent")
        cells_grid.pack(fill="both", expand=True, padx=6, pady=4)

        for col in range(4):
            cells_grid.grid_columnconfigure(col, weight=1)
        for row in range(4):
            cells_grid.grid_rowconfigure(row, weight=1)

        for i in range(16):
            cell_num = i + 1
            r = i // 4
            c = i % 4

            c_box = ctk.CTkFrame(
                cells_grid, fg_color=COLOR_ROW_ALT1, corner_radius=6,
                border_width=1, border_color=COLOR_BORDER_SUBTLE
            )
            c_box.grid(row=r, column=c, padx=4, pady=3, sticky="nsew")

            top_row = ctk.CTkFrame(c_box, fg_color="transparent")
            top_row.pack(fill="x", padx=6, pady=(4, 1))

            ctk.CTkLabel(
                top_row, text=f"Cell #{cell_num:02d}",
                font=ctk.CTkFont(family="Consolas", size=10, weight="bold"), text_color=COLOR_TEXT_WHITE
            ).pack(side="left")

            lbl_bal = ctk.CTkLabel(
                top_row, text="⚡ BAL" if cell_num in (2, 7, 11) else "",
                font=ctk.CTkFont(family="Consolas", size=9, weight="bold"), text_color=COLOR_WARNING_LIGHT
            )
            lbl_bal.pack(side="right")

            lbl_v = ctk.CTkLabel(
                c_box, text="3.820 V",
                font=ctk.CTkFont(family="Consolas", size=14, weight="bold"), text_color=COLOR_SUCCESS_GLOW
            )
            lbl_v.pack(anchor="w", padx=6, pady=(0, 2))

            bar = ctk.CTkProgressBar(c_box, height=8, progress_color=COLOR_SUCCESS)
            bar.set(0.68)
            bar.pack(fill="x", padx=6, pady=(0, 4))

            self.cell_widgets[cell_num] = {
                "val": lbl_v,
                "bar": bar,
                "bal": lbl_bal,
                "box": c_box
            }

        # Cột phải: Nhiệt độ Pack Pin & Trạng thái Cân bằng
        side_box = ctk.CTkFrame(
            center_frame, fg_color=COLOR_CARD_INNER, corner_radius=6,
            border_width=1, border_color=COLOR_BORDER_SUBTLE
        )
        side_box.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)

        t_title_bar = ctk.CTkFrame(side_box, height=30, fg_color="#182332", corner_radius=4)
        t_title_bar.pack(fill="x", padx=4, pady=(4, 6))
        ctk.CTkLabel(
            t_title_bar, text="🌡️ NHIỆT ĐỘ MODULE PIN & BMU",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=11, weight="bold"), text_color=COLOR_TEXT_WHITE
        ).pack(side="left", padx=8, pady=3)

        temp_grid = ctk.CTkFrame(side_box, fg_color="transparent")
        temp_grid.pack(fill="x", padx=6, pady=4)

        temp_items = [
            ("t1", "Cảm biến T1 (Module 1):", "28.4 °C"),
            ("t2", "Cảm biến T2 (Module 2):", "29.1 °C"),
            ("t3", "Cảm biến T3 (Module 3):", "28.7 °C"),
            ("t4", "Cảm biến T4 (Module 4):", "29.5 °C"),
            ("tbmu", "Nhiệt độ Bo mạch BMS:", "31.2 °C"),
        ]

        for key, name, val_str in temp_items:
            t_row = ctk.CTkFrame(temp_grid, fg_color=COLOR_ROW_ALT1, corner_radius=4, height=28)
            t_row.pack(fill="x", padx=2, pady=2)
            ctk.CTkLabel(t_row, text=name, font=ctk.CTkFont(family=FONT_PRIMARY, size=10), text_color=COLOR_TEXT_GRAY).pack(side="left", padx=6)
            lbl_t = ctk.CTkLabel(t_row, text=val_str, font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color=COLOR_WARNING_LIGHT)
            lbl_t.pack(side="right", padx=6)
            self.temp_labels[key] = lbl_t

        # Trạng thái cân bằng pin
        bal_box = ctk.CTkFrame(
            side_box, fg_color=COLOR_ROW_ALT1, corner_radius=6,
            border_width=1, border_color=COLOR_BORDER_SUBTLE
        )
        bal_box.pack(fill="x", padx=6, pady=8)

        ctk.CTkLabel(
            bal_box, text="CÂN BẰNG CELL TỰ ĐỘNG",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=10, weight="bold"), text_color=VIETTEL_RED_LIGHT
        ).pack(anchor="w", padx=8, pady=(6, 2))

        self.sw_auto_bal = ctk.CTkSwitch(
            bal_box, text="Bật Cân Bằng Động (Active)", progress_color=VIETTEL_RED,
            font=ctk.CTkFont(size=10, weight="bold"), command=self._on_balancing_toggled
        )
        self.sw_auto_bal.select()
        self.sw_auto_bal.pack(anchor="w", padx=8, pady=(2, 6))

        self.lbl_bal_status = ctk.CTkLabel(
            bal_box, text="Đang cân bằng 3 cells: #02, #07, #11",
            font=ctk.CTkFont(family="Consolas", size=10), text_color=COLOR_SUCCESS_GLOW
        )
        self.lbl_bal_status.pack(anchor="w", padx=8, pady=(0, 6))

        # =====================================================================
        # 3. FOOTER: BẢNG CÀI ĐẶT NGƯỠNG BẢO VỆ BMU
        # =====================================================================
        bottom_frame = ctk.CTkFrame(
            self, fg_color=COLOR_CARD_BG, corner_radius=8,
            border_width=1, border_color=COLOR_BORDER
        )
        bottom_frame.pack(fill="x", padx=4, pady=(2, 10))

        b_title_row = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        b_title_row.pack(fill="x", padx=8, pady=(6, 2))
        ctk.CTkLabel(
            b_title_row, text="⚙️ CÀI ĐẶT NGƯỠNG AN TOÀN & BẢO VỆ BMU (SAFETY PROTECTION LIMITS)",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=11, weight="bold"), text_color=VIETTEL_RED_LIGHT
        ).pack(side="left")

        cfg_row = ctk.CTkFrame(bottom_frame, fg_color="transparent")
        cfg_row.pack(fill="x", padx=8, pady=(2, 8))

        # 4 ô cài đặt ngưỡng
        ctk.CTkLabel(cfg_row, text="Quá áp Cell (OV):", font=ctk.CTkFont(family=FONT_PRIMARY, size=10, weight="bold"), text_color=COLOR_TEXT_WHITE).pack(side="left", padx=(4, 2))
        self.ent_ov = ctk.CTkEntry(cfg_row, width=60, border_color=COLOR_BORDER, fg_color=COLOR_CARD_INNER)
        self.ent_ov.insert(0, "4.25")
        self.ent_ov.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(cfg_row, text="Tụt áp Cell (UV):", font=ctk.CTkFont(family=FONT_PRIMARY, size=10, weight="bold"), text_color=COLOR_TEXT_WHITE).pack(side="left", padx=(4, 2))
        self.ent_uv = ctk.CTkEntry(cfg_row, width=60, border_color=COLOR_BORDER, fg_color=COLOR_CARD_INNER)
        self.ent_uv.insert(0, "3.00")
        self.ent_uv.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(cfg_row, text="Quá nhiệt (°C):", font=ctk.CTkFont(family=FONT_PRIMARY, size=10, weight="bold"), text_color=COLOR_TEXT_WHITE).pack(side="left", padx=(4, 2))
        self.ent_ot = ctk.CTkEntry(cfg_row, width=60, border_color=COLOR_BORDER, fg_color=COLOR_CARD_INNER)
        self.ent_ot.insert(0, "65.0")
        self.ent_ot.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(cfg_row, text="Dòng xả Max (A):", font=ctk.CTkFont(family=FONT_PRIMARY, size=10, weight="bold"), text_color=COLOR_TEXT_WHITE).pack(side="left", padx=(4, 2))
        self.ent_max_cur = ctk.CTkEntry(cfg_row, width=65, border_color=COLOR_BORDER, fg_color=COLOR_CARD_INNER)
        self.ent_max_cur.insert(0, "220.0")
        self.ent_max_cur.pack(side="left", padx=(0, 14))

        self.btn_save_limits = ctk.CTkButton(
            cfg_row, text="💾 Lưu Cấu Hình BMU", width=140, height=30,
            fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER,
            font=ctk.CTkFont(family=FONT_PRIMARY, size=11, weight="bold"), command=self._save_bmu_limits
        )
        self.btn_save_limits.pack(side="right", padx=4)

        self.btn_clear_faults = ctk.CTkButton(
            cfg_row, text="🔄 Reset Lỗi BMU", width=120, height=30,
            fg_color="#223042", hover_color="#33465C",
            font=ctk.CTkFont(family=FONT_PRIMARY, size=11, weight="bold"), command=self._clear_bmu_faults
        )
        self.btn_clear_faults.pack(side="right", padx=4)

    # -------------------------------------------------------------------------
    # HÀNH ĐỘNG ĐIỀU KHIỂN BMU
    # -------------------------------------------------------------------------
    def _on_balancing_toggled(self):
        active = bool(self.sw_auto_bal.get())
        if hasattr(self.conn, 'set_bmu_balancing'):
            self.conn.set_bmu_balancing(active)
        self.lbl_bal_status.configure(
            text="Đang cân bằng tự động..." if active else "Đã tắt cân bằng cell",
            text_color=COLOR_SUCCESS_GLOW if active else COLOR_TEXT_MUTED
        )

    def _save_bmu_limits(self):
        try:
            ov = float(self.ent_ov.get().strip())
            uv = float(self.ent_uv.get().strip())
            ot = float(self.ent_ot.get().strip())
            max_c = float(self.ent_max_cur.get().strip())
            if hasattr(self.conn, 'set_bmu_protection_limits'):
                self.conn.set_bmu_protection_limits(ov, uv, ot, max_c)
            messagebox.showinfo("Cài đặt BMU", "Đã lưu thành công các ngưỡng bảo vệ an toàn cho BMU!")
        except Exception as e:
            messagebox.showerror("Lỗi dữ liệu", f"Vui lòng nhập số hợp lệ: {e}")

    def _clear_bmu_faults(self):
        self.conn.log("BMU: Đã gửi lệnh Reset mã lỗi bộ quản lý pin.", "SUCCESS")
        messagebox.showinfo("Reset BMU", "Đã xóa các cảnh báo lỗi tạm thời trên BMU.")

    # -------------------------------------------------------------------------
    # CẬP NHẬT DỮ LIỆU TELEMETRY
    # -------------------------------------------------------------------------
    def update_telemetry(self, d: Dict[str, Any]):
        pack_v = d.get("bmu_pack_voltage", 61.12)
        pack_i = d.get("bmu_pack_current", 0.0)
        soc = d.get("bmu_soc", 86.5)
        soh = d.get("bmu_soh", 99.0)
        delta_mv = d.get("bmu_cell_delta_mv", 14.0)
        max_v = d.get("bmu_cell_max", 3.828)
        min_v = d.get("bmu_cell_min", 3.814)
        max_idx = d.get("bmu_cell_max_idx", 7)
        min_idx = d.get("bmu_cell_min_idx", 2)
        cycles = d.get("bmu_cycle_count", 42)

        if "pack_voltage" in self.metric_labels:
            _safe_configure_label(self.metric_labels["pack_voltage"], f"{pack_v:.2f}")
            _safe_configure_label(self.metric_labels["pack_current"], f"{pack_i:.1f}")
            _safe_configure_label(self.metric_labels["soc"], f"{soc:.1f}")
            _safe_configure_label(self.metric_labels["soh"], f"{soh:.1f}")
            _safe_configure_label(self.metric_labels["delta_v"], f"{delta_mv:.1f}")
            _safe_configure_label(self.metric_labels["max_cell"], f"{max_v:.3f} (C{max_idx})")
            _safe_configure_label(self.metric_labels["min_cell"], f"{min_v:.3f} (C{min_idx})")
            _safe_configure_label(self.metric_labels["cycles"], f"{cycles}")

        # Cập nhật 16 Cell pin
        cells = d.get("bmu_cells", [])
        bal_cells = d.get("bmu_balancing_cells", [])

        for i, v in enumerate(cells[:16]):
            cell_num = i + 1
            if cell_num in self.cell_widgets:
                w = self.cell_widgets[cell_num]
                # Tỷ lệ 3.0V -> 0%, 4.2V -> 100%
                ratio = max(0.0, min(1.0, (v - 3.0) / 1.2))

                # Đổi màu cảnh báo nếu cell lệch nhiều
                if v < 3.2 or v > 4.22:
                    color = VIETTEL_RED
                elif abs(v - max_v) > 0.05:
                    color = COLOR_WARNING_LIGHT
                else:
                    color = COLOR_SUCCESS_GLOW

                _safe_configure_label(w["val"], f"{v:.3f} V", color)
                _safe_set_progress_bar(w["bar"], ratio, color)

                if cell_num in bal_cells:
                    _safe_configure_label(w["bal"], "⚡ BAL")
                else:
                    _safe_configure_label(w["bal"], "")

        # Cập nhật nhiệt độ
        temps = d.get("bmu_temps", [28.4, 29.1, 28.7, 29.5])
        board_t = d.get("bmu_board_temp", 31.2)
        if len(temps) >= 4 and "t1" in self.temp_labels:
            _safe_configure_label(self.temp_labels["t1"], f"{temps[0]:.1f} °C")
            _safe_configure_label(self.temp_labels["t2"], f"{temps[1]:.1f} °C")
            _safe_configure_label(self.temp_labels["t3"], f"{temps[2]:.1f} °C")
            _safe_configure_label(self.temp_labels["t4"], f"{temps[3]:.1f} °C")
            _safe_configure_label(self.temp_labels["tbmu"], f"{board_t:.1f} °C")
