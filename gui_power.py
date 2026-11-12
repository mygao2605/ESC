"""
VIETTEL BLDC / ESC CONTROLLER - MODULE GIAO DIỆN QUẢN LÝ NGUỒN (POWER / PDU)
File: gui_power.py
Đặc tả kỹ thuật chuẩn Modbus RTU: Slave ID 01, Baudrate 921600-8-N-1

HỖ TRỢ 2 CHẾ ĐỘ GIÁM SÁT RIÊNG BIỆT:
1. CHẾ ĐỘ 1: GIÁM SÁT PHASE-SHIFT (10 THANH GHI ĐỌC: ADDR 0 .. 9)
   - 0: State (1: BẬT, 0: TẮT)
   - 1: Protect Time (ms)
   - 2: RampMax
   - 3: RampDec
   - 4: V_in(mV)
   - 5: V_out(mV)
   - 6: I_out(mV)
   - 7: ErrorCode
   - 8: FanSpeed (RPM)
   - 9: DeadTime (ns)
   * Toàn bộ 10 thông số là ĐỌC VỀ (Read-only telemetry).

2. CHẾ ĐỘ 2: GIÁM SÁT HỆ THỐNG NGUỒN TỔNG (36 THANH GHI ĐỌC: ADDR 0 .. 35)
   - 0..3   : Sạc & Nguồn vào (Charge_BatVolt, Charge_BatChargeCurr, Charge_InpVolt, Charge_InpCurr)
   - 4..9   : Buck 12V_1 (Vout_1, Vout_2, Iout_1, Iout_2, Temp_1, Temp_2)
   - 10..15 : Buck 12V_2 (Vout_1, Vout_2, Iout_1, Iout_2, Temp_1, Temp_2)
   - 16..21 : Buck 5V_1 (Vout_1, Vout_2, Iout_1, Iout_2, Temp_1, Temp_2)
   - 22..27 : Buck 5V_2 (Vout_1, Vout_2, Iout_1, Iout_2, Temp_1, Temp_2)
   - 28..35 : Master & Slave (Error Master, Vbus, Vout Master, Iout Master, Vout Slave, Iout Slave, Error Slave, Fanspeed)

QUYỀN ĐIỀU KHIỂN DUY NHẤT:
- Nút BẬT NGUỒN (Set State = 1) và TẮT NGUỒN (Set State = 0) ghi vào thanh ghi Address 0.
"""

from typing import Dict, Any, List
import customtkinter as ctk

from mgm_comm import POWER_READ_REGISTERS, POWER_WRITE_REGISTERS

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


def _safe_configure_label(lbl, text: str, text_color: str = None):
    """Chỉ gọi lbl.configure() khi text hoặc text_color thực sự thay đổi nhằm triệt tiêu giật lag/flicker"""
    if lbl is None:
        return
    cached_text = getattr(lbl, "_cached_text", None)
    cached_color = getattr(lbl, "_cached_color", None)
    changed = False
    kwargs = {}
    if cached_text != text:
        kwargs["text"] = text
        lbl._cached_text = text
        changed = True
    if text_color is not None and cached_color != text_color:
        kwargs["text_color"] = text_color
        lbl._cached_color = text_color
        changed = True
    if changed:
        lbl.configure(**kwargs)


class PowerTabFrame(ctk.CTkScrollableFrame):
    """Giao diện Quản lý Nguồn & Hệ thống Phân phối Điện (Power & PDU) với 2 chế độ giám sát"""
    def __init__(self, master, conn, **kwargs):
        super().__init__(
            master,
            fg_color="transparent",
            scrollbar_button_color="#3D2024",
            scrollbar_button_hover_color=VIETTEL_RED,
            **kwargs
        )
        self.conn = conn

        # Bộ lưu trữ widgets để cập nhật dữ liệu nhanh
        self.read_row_labels: Dict[int, Dict[str, ctk.CTkLabel]] = {}
        self.phase_shift_labels: Dict[int, Dict[str, Any]] = {}
        self.phase_shift_row_labels: Dict[int, Dict[str, ctk.CTkLabel]] = {}
        self.hero_labels: Dict[str, ctk.CTkLabel] = {}
        self.group_val_labels: Dict[str, ctk.CTkLabel] = {}

        self._build_ui()

    def _build_ui(self):
        # =====================================================================
        # 1. HERO BANNER: ĐIỀU KHIỂN TRẠNG THÁI NGUỒN (CHỈ SET STATE: 1 HOẶC 0)
        # =====================================================================
        hero_frame = ctk.CTkFrame(self, fg_color=VIETTEL_PANEL_BG, corner_radius=8, border_width=2, border_color=VIETTEL_BORDER)
        hero_frame.pack(fill="x", padx=4, pady=(2, 6))

        top_row = ctk.CTkFrame(hero_frame, fg_color="transparent")
        top_row.pack(fill="x", padx=12, pady=(10, 6))

        title_box = ctk.CTkFrame(top_row, fg_color="transparent")
        title_box.pack(side="left")

        ctk.CTkLabel(
            title_box, text="⚡ ĐIỀU KHIỂN TRẠNG THÁI NGUỒN (CHỈ SET STATE: 1 HOẶC 0)",
            font=ctk.CTkFont(size=14, weight="bold"), text_color=VIETTEL_RED_LIGHT
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_box, text="Giao thức Modbus RTU: Slave ID 01 | Baudrate 921600-8-N-1 | Lệnh ghi duy nhất: State (Addr 0: 1=BẬT / 0=TẮT)",
            font=ctk.CTkFont(size=11), text_color=VIETTEL_TEXT_GRAY
        ).pack(anchor="w")

        # Huy hiệu hiển thị State hiện tại
        state_badge = ctk.CTkFrame(top_row, fg_color="#181214", corner_radius=6, border_width=1, border_color=VIETTEL_BORDER)
        state_badge.pack(side="right", padx=4)

        ctk.CTkLabel(state_badge, text="TRẠNG THÁI NGUỒN:", font=ctk.CTkFont(size=10, weight="bold"), text_color=VIETTEL_TEXT_GRAY).pack(side="left", padx=(10, 4), pady=6)
        self.lbl_state_badge = ctk.CTkLabel(
            state_badge, text="BẬT (STATE = 1)",
            font=ctk.CTkFont(family="Consolas", size=13, weight="bold"), text_color="#00E676"
        )
        self.lbl_state_badge.pack(side="left", padx=(0, 10), pady=6)

        # Hàng 2 Nút bấm lớn điều khiển Set State = 1 hoặc 0 (QUYỀN ĐIỀU KHIỂN DUY NHẤT)
        btn_action_box = ctk.CTkFrame(hero_frame, fg_color="transparent")
        btn_action_box.pack(fill="x", padx=12, pady=(4, 10))

        self.btn_set_state_1 = ctk.CTkButton(
            btn_action_box, text="🟢 BẬT NGUỒN (SET STATE = 1)", height=44,
            fg_color="#1E8E3E", hover_color="#16692D",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda: self._set_state(1)
        )
        self.btn_set_state_1.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_set_state_0 = ctk.CTkButton(
            btn_action_box, text="⚪ TẮT NGUỒN (SET STATE = 0)", height=44,
            fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=lambda: self._set_state(0)
        )
        self.btn_set_state_0.pack(side="left", fill="x", expand=True, padx=(8, 0))

        # =====================================================================
        # 2. KHU VỰC 2 CHẾ ĐỘ GIÁM SÁT: PHASE-SHIFT (10 READ) & NGUỒN TỔNG (36 READ)
        # =====================================================================
        self.sub_tabview = ctk.CTkTabview(
            self,
            corner_radius=8,
            fg_color=VIETTEL_PANEL_BG,
            segmented_button_selected_color=VIETTEL_RED,
            segmented_button_selected_hover_color=VIETTEL_RED_HOVER,
            segmented_button_unselected_color="#2A2022",
            segmented_button_unselected_hover_color="#3D2B2E",
            command=self._on_subtab_changed
        )
        self.sub_tabview.pack(fill="both", expand=True, padx=4, pady=(2, 6))

        # 2 Tab con cho 2 chế độ giám sát
        self.tab_phase_shift = self.sub_tabview.add("📊 CHẾ ĐỘ 1: PHASE-SHIFT (10 READ: 0 .. 9)")
        self.tab_power_full = self.sub_tabview.add("⚡ CHẾ ĐỘ 2: HỆ THỐNG NGUỒN TỔNG (36 READ: 0 .. 35)")

        # Xây dựng nội dung cho cả 2 tab
        self._build_phase_shift_tab(self.tab_phase_shift)
        self._build_power_full_tab(self.tab_power_full)

    # =========================================================================
    # CHẾ ĐỘ 1: PHASE-SHIFT (10 THANH GHI ĐỌC: 0 .. 9)
    # =========================================================================
    def _build_phase_shift_tab(self, parent):
        # Thanh thông tin dải quét
        info_bar = ctk.CTkFrame(parent, height=32, fg_color="#2A171B", corner_radius=6)
        info_bar.pack(fill="x", padx=6, pady=(4, 6))

        ctk.CTkLabel(
            info_bar,
            text="📡 CHẾ ĐỘ QUÉT: MODBUS F=03 | START ADDR: 0 | QUANTITY: 10 THANH GHI (TEST PHASE-SHIFT)",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_WHITE
        ).pack(side="left", padx=10, pady=4)

        ctk.CTkLabel(
            info_bar,
            text="● Tương thích cửa sổ Modbus Slave 10 thanh ghi (Addr 0..9)",
            font=ctk.CTkFont(size=10, weight="bold"), text_color="#00E676"
        ).pack(side="right", padx=10, pady=4)

        # 10 Thẻ đo chỉ số thời gian thực
        cards_frame = ctk.CTkFrame(parent, fg_color="transparent")
        cards_frame.pack(fill="x", padx=4, pady=4)

        for i, reg in enumerate(POWER_WRITE_REGISTERS):
            row_idx = i // 5
            col_idx = i % 5

            card = ctk.CTkFrame(cards_frame, fg_color=VIETTEL_CARD_BG, corner_radius=6, border_width=1, border_color=VIETTEL_BORDER)
            card.grid(row=row_idx, column=col_idx, padx=4, pady=4, sticky="nsew")
            cards_frame.grid_columnconfigure(col_idx, weight=1)

            t_row = ctk.CTkFrame(card, fg_color="transparent")
            t_row.pack(fill="x", padx=6, pady=(4, 1))
            ctk.CTkLabel(t_row, text=f"[{reg['index']}] {reg['name']}", font=ctk.CTkFont(size=10, weight="bold"), text_color=VIETTEL_RED_LIGHT).pack(side="left")
            if reg["unit"]:
                ctk.CTkLabel(t_row, text=f"({reg['unit']})", font=ctk.CTkFont(size=9), text_color=VIETTEL_TEXT_GRAY).pack(side="right")

            v_frame = ctk.CTkFrame(card, fg_color="transparent")
            v_frame.pack(fill="x", padx=6, pady=(2, 2))

            lbl_val = ctk.CTkLabel(v_frame, text="--", font=ctk.CTkFont(family="Consolas", size=14, weight="bold"), text_color=VIETTEL_TEXT_WHITE)
            lbl_val.pack(side="left")

            lbl_scale = ctk.CTkLabel(v_frame, text="", font=ctk.CTkFont(size=10), text_color=VIETTEL_TEXT_GRAY)
            lbl_scale.pack(side="left", padx=(4, 0))

            b_row = ctk.CTkFrame(card, fg_color="transparent")
            b_row.pack(fill="x", padx=6, pady=(0, 4))
            ctk.CTkLabel(b_row, text=reg["desc"][:24], font=ctk.CTkFont(size=9), text_color=VIETTEL_TEXT_GRAY).pack(side="left")
            lbl_hex = ctk.CTkLabel(b_row, text="0x0000", font=ctk.CTkFont(family="Consolas", size=9), text_color="#7A686B")
            lbl_hex.pack(side="right")

            self.phase_shift_labels[reg["index"]] = {
                "val": lbl_val,
                "scale": lbl_scale,
                "hex": lbl_hex,
                "card": card
            }

        # Bảng Modbus chi tiết 10 thanh ghi Phase-Shift
        tbl_frame = ctk.CTkFrame(parent, fg_color=VIETTEL_CARD_BG, corner_radius=6, border_width=1, border_color=VIETTEL_BORDER)
        tbl_frame.pack(fill="x", padx=6, pady=(8, 8))

        t_title = ctk.CTkFrame(tbl_frame, height=28, fg_color="#33181E", corner_radius=4)
        t_title.pack(fill="x", padx=4, pady=(4, 4))
        ctk.CTkLabel(t_title, text="📋 BẢNG CHI TIẾT 10 THANH GHI PHASE-SHIFT ĐỌC VỀ (MODBUS RTU: ADDR 0 .. 9)", font=ctk.CTkFont(size=10, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=8)

        # Header bảng
        hdr = ctk.CTkFrame(tbl_frame, height=26, fg_color="#2D1E22", corner_radius=4)
        hdr.pack(fill="x", padx=4, pady=(2, 2))
        ctk.CTkLabel(hdr, text="Addr", width=45, font=ctk.CTkFont(size=10, weight="bold"), text_color=VIETTEL_RED_LIGHT).pack(side="left", padx=2)
        ctk.CTkLabel(hdr, text="Tên thông số (Name)", width=180, anchor="w", font=ctk.CTkFont(size=10, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=4)
        ctk.CTkLabel(hdr, text="Giá trị Raw (00000)", width=120, anchor="e", font=ctk.CTkFont(size=10, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=4)
        ctk.CTkLabel(hdr, text="HEX", width=70, anchor="center", font=ctk.CTkFont(size=10, weight="bold"), text_color=VIETTEL_TEXT_GRAY).pack(side="left", padx=3)
        ctk.CTkLabel(hdr, text="Quy đổi chuẩn (Scale)", width=150, anchor="center", font=ctk.CTkFont(size=10, weight="bold"), text_color="#00E676").pack(side="left", padx=4)
        ctk.CTkLabel(hdr, text="Mô tả chức năng", anchor="w", font=ctk.CTkFont(size=10, weight="bold"), text_color=VIETTEL_TEXT_GRAY).pack(side="left", fill="x", expand=True, padx=4)

        for reg in POWER_WRITE_REGISTERS:
            idx = reg["index"]
            row_bg = "#1E1618" if idx % 2 == 0 else "#251B1E"

            row = ctk.CTkFrame(tbl_frame, height=26, fg_color=row_bg, corner_radius=3)
            row.pack(fill="x", padx=4, pady=1)

            ctk.CTkLabel(row, text=f"{idx}", width=45, font=ctk.CTkFont(family="Consolas", size=10, weight="bold"), text_color=VIETTEL_TEXT_GRAY).pack(side="left", padx=2)
            ctk.CTkLabel(row, text=f"  {reg['name']}", width=180, anchor="w", font=ctk.CTkFont(size=10, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=4)

            lbl_val = ctk.CTkLabel(row, text="0", width=120, anchor="e", font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color="#00E676")
            lbl_val.pack(side="left", padx=4)

            lbl_hex = ctk.CTkLabel(row, text="0x0000", width=70, anchor="center", font=ctk.CTkFont(family="Consolas", size=10), text_color=VIETTEL_TEXT_GRAY)
            lbl_hex.pack(side="left", padx=3)

            lbl_scale = ctk.CTkLabel(row, text="--", width=150, anchor="center", font=ctk.CTkFont(family="Consolas", size=10, weight="bold"), text_color="#FFD54F")
            lbl_scale.pack(side="left", padx=4)

            ctk.CTkLabel(row, text=reg["desc"], anchor="w", font=ctk.CTkFont(size=10), text_color=VIETTEL_TEXT_GRAY).pack(side="left", fill="x", expand=True, padx=4)

            self.phase_shift_row_labels[idx] = {
                "val": lbl_val,
                "hex": lbl_hex,
                "scale": lbl_scale
            }

    # =========================================================================
    # CHẾ ĐỘ 2: HỆ THỐNG NGUỒN TỔNG (36 THANH GHI ĐỌC: 0 .. 35)
    # =========================================================================
    def _build_power_full_tab(self, parent):
        # Thanh thông tin dải quét
        info_bar = ctk.CTkFrame(parent, height=32, fg_color="#2A171B", corner_radius=6)
        info_bar.pack(fill="x", padx=6, pady=(4, 6))

        ctk.CTkLabel(
            info_bar,
            text="📡 CHẾ ĐỘ QUÉT: MODBUS F=03 | START ADDR: 0 | QUANTITY: 36 THANH GHI (TEST MORNITOR / GIÁM SÁT)",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_WHITE
        ).pack(side="left", padx=10, pady=4)

        ctk.CTkLabel(
            info_bar,
            text="● Tương thích cửa sổ Modbus Slave 36 thanh ghi (Addr 0..35)",
            font=ctk.CTkFont(size=10, weight="bold"), text_color="#FFD54F"
        ).pack(side="right", padx=10, pady=4)

        # 6 Đồng hồ tóm tắt nhanh trên Hero
        quick_grid = ctk.CTkFrame(parent, fg_color="transparent")
        quick_grid.pack(fill="x", padx=4, pady=(2, 6))

        quick_metrics = [
            ("vbus",        "ĐIỆN ÁP VBUS",        "48.00", "V",   VIETTEL_RED_LIGHT),
            ("vout_master", "VOUT MASTER",         "47.90", "V",   "#00E676"),
            ("iout_master", "IOUT MASTER",         "0.00",  "A",   "#FF7043"),
            ("vout_slave",  "VOUT SLAVE",          "47.85", "V",   "#4FC3F7"),
            ("fanspeed",    "TỐC ĐỘ QUẠT SLAVE",   "2400",  "RPM", "#FFD54F"),
            ("err_code",    "MÃ LỖI (M / S)",      "0 / 0", "HEX", "#E0E0E0")
        ]

        for idx, (key, title, init_v, unit, col) in enumerate(quick_metrics):
            card = ctk.CTkFrame(quick_grid, fg_color=VIETTEL_CARD_BG, corner_radius=6, border_width=1, border_color=VIETTEL_BORDER)
            card.pack(side="left", fill="x", expand=True, padx=3)

            ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=9, weight="bold"), text_color=VIETTEL_TEXT_GRAY).pack(anchor="w", padx=8, pady=(4, 1))
            val_b = ctk.CTkFrame(card, fg_color="transparent")
            val_b.pack(anchor="w", padx=8, pady=(0, 4))
            lbl = ctk.CTkLabel(val_b, text=init_v, font=ctk.CTkFont(family="Consolas", size=14, weight="bold"), text_color=col)
            lbl.pack(side="left")
            if unit:
                ctk.CTkLabel(val_b, text=f" {unit}", font=ctk.CTkFont(size=10), text_color=VIETTEL_TEXT_GRAY).pack(side="left", padx=(2, 0), pady=(2, 0))
            self.hero_labels[key] = lbl

        # 4 Khối chức năng (Charger, Master/Slave, Buck 12V, Buck 5V)
        blocks_container = ctk.CTkFrame(parent, fg_color="transparent")
        blocks_container.pack(fill="x", padx=4, pady=2)
        blocks_container.grid_columnconfigure(0, weight=1)
        blocks_container.grid_columnconfigure(1, weight=1)

        # KHỐI 1: SẠC & NGUỒN VÀO (CHARGER & INPUT - REGS 0..3)
        chg_box = ctk.CTkFrame(blocks_container, fg_color=VIETTEL_PANEL_BG, corner_radius=8, border_width=1, border_color=VIETTEL_BORDER)
        chg_box.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=3)

        t_chg = ctk.CTkFrame(chg_box, height=26, fg_color="#2A171B", corner_radius=4)
        t_chg.pack(fill="x", padx=4, pady=(4, 4))
        ctk.CTkLabel(t_chg, text="🔋 [REGS 0..3] SẠC & NGUỒN VÀO (CHARGER & INPUT)", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=6)

        chg_grid = ctk.CTkFrame(chg_box, fg_color="transparent")
        chg_grid.pack(fill="x", padx=6, pady=4)

        chg_items = [
            ("reg_0", "[0] Charge_BatVolt", "48250 mV (48.25 V)", VIETTEL_RED_LIGHT),
            ("reg_1", "[1] Charge_BatChargeCurr", "1500 mA (1.50 A)", "#FF7043"),
            ("reg_2", "[2] Charge_InpVolt", "54000 mV (54.00 V)", "#00E676"),
            ("reg_3", "[3] Charge_InpCurr", "1850 mA (1.85 A)", "#FFD54F"),
        ]

        for k, name, init_val, col in chg_items:
            r_frame = ctk.CTkFrame(chg_grid, fg_color=VIETTEL_CARD_BG, corner_radius=4, height=26)
            r_frame.pack(fill="x", padx=2, pady=1.5)
            ctk.CTkLabel(r_frame, text=name, font=ctk.CTkFont(size=10), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=6)
            lbl = ctk.CTkLabel(r_frame, text=init_val, font=ctk.CTkFont(family="Consolas", size=10, weight="bold"), text_color=col)
            lbl.pack(side="right", padx=6)
            self.group_val_labels[k] = lbl

        # KHỐI 2: MASTER & SLAVE HIGH POWER BUS (REGS 28..35)
        bus_box = ctk.CTkFrame(blocks_container, fg_color=VIETTEL_PANEL_BG, corner_radius=8, border_width=1, border_color=VIETTEL_BORDER)
        bus_box.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=3)

        t_bus = ctk.CTkFrame(bus_box, height=26, fg_color="#2A171B", corner_radius=4)
        t_bus.pack(fill="x", padx=4, pady=(4, 4))
        ctk.CTkLabel(t_bus, text="⚡ [REGS 28..35] NGUỒN CÔNG SUẤT MASTER & SLAVE", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=6)

        bus_grid = ctk.CTkFrame(bus_box, fg_color="transparent")
        bus_grid.pack(fill="x", padx=6, pady=4)

        bus_items = [
            ("reg_28_34", "Mã lỗi Master / Slave:", "0 / 0 (OK)", "#00E676"),
            ("reg_29",    "[29] Vbus x 100:", "4800 (48.00 V)", VIETTEL_RED_LIGHT),
            ("reg_30_31", "Master Vout / Iout:", "47.90 V / 0.00 A", "#FF7043"),
            ("reg_32_33", "Slave Vout / Iout:", "47.85 V / 0.00 A", "#4FC3F7"),
        ]

        for k, name, init_val, col in bus_items:
            r_frame = ctk.CTkFrame(bus_grid, fg_color=VIETTEL_CARD_BG, corner_radius=4, height=26)
            r_frame.pack(fill="x", padx=2, pady=1.5)
            ctk.CTkLabel(r_frame, text=name, font=ctk.CTkFont(size=10), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=6)
            lbl = ctk.CTkLabel(r_frame, text=init_val, font=ctk.CTkFont(family="Consolas", size=10, weight="bold"), text_color=col)
            lbl.pack(side="right", padx=6)
            self.group_val_labels[k] = lbl

        # KHỐI 3: MODULE HẠ ÁP BUCK 12V (REGS 4..15)
        b12_box = ctk.CTkFrame(blocks_container, fg_color=VIETTEL_PANEL_BG, corner_radius=8, border_width=1, border_color=VIETTEL_BORDER)
        b12_box.grid(row=1, column=0, sticky="nsew", padx=(0, 4), pady=3)

        t_b12 = ctk.CTkFrame(b12_box, height=26, fg_color="#2A171B", corner_radius=4)
        t_b12.pack(fill="x", padx=4, pady=(4, 4))
        ctk.CTkLabel(t_b12, text="🔌 [REGS 4..15] MODULE HẠ ÁP BUCK 12V_1 & 12V_2", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=6)

        b12_grid = ctk.CTkFrame(b12_box, fg_color="transparent")
        b12_grid.pack(fill="x", padx=6, pady=4)

        b12_items = [
            ("b12_1_v", "Buck 12V_1 Vout 1/2:", "12050 / 12040 mV", "#00E676"),
            ("b12_1_i", "Buck 12V_1 Iout 1/2:", "2450 / 1850 mA", "#FF7043"),
            ("b12_1_t", "Buck 12V_1 Nhiệt độ 1/2:", "32 / 33 °C", "#FFD54F"),
            ("b12_2_v", "Buck 12V_2 Vout 1/2:", "12030 / 12020 mV", "#00E676"),
            ("b12_2_i", "Buck 12V_2 Iout 1/2:", "1950 / 1750 mA", "#FF7043"),
            ("b12_2_t", "Buck 12V_2 Nhiệt độ 1/2:", "31 / 32 °C", "#FFD54F"),
        ]

        for k, name, init_val, col in b12_items:
            r_frame = ctk.CTkFrame(b12_grid, fg_color=VIETTEL_CARD_BG, corner_radius=4, height=26)
            r_frame.pack(fill="x", padx=2, pady=1.5)
            ctk.CTkLabel(r_frame, text=name, font=ctk.CTkFont(size=10), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=6)
            lbl = ctk.CTkLabel(r_frame, text=init_val, font=ctk.CTkFont(family="Consolas", size=10, weight="bold"), text_color=col)
            lbl.pack(side="right", padx=6)
            self.group_val_labels[k] = lbl

        # KHỐI 4: MODULE HẠ ÁP BUCK 5V (REGS 16..27)
        b5_box = ctk.CTkFrame(blocks_container, fg_color=VIETTEL_PANEL_BG, corner_radius=8, border_width=1, border_color=VIETTEL_BORDER)
        b5_box.grid(row=1, column=1, sticky="nsew", padx=(4, 0), pady=3)

        t_b5 = ctk.CTkFrame(b5_box, height=26, fg_color="#2A171B", corner_radius=4)
        t_b5.pack(fill="x", padx=4, pady=(4, 4))
        ctk.CTkLabel(t_b5, text="💡 [REGS 16..27] MODULE HẠ ÁP BUCK 5V_1 & 5V_2", font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=6)

        b5_grid = ctk.CTkFrame(b5_box, fg_color="transparent")
        b5_grid.pack(fill="x", padx=6, pady=4)

        b5_items = [
            ("b5_1_v", "Buck 5V_1 Vout 1/2:", "5180 / 5175 mV", "#00E676"),
            ("b5_1_i", "Buck 5V_1 Iout 1/2:", "1650 / 1200 mA", "#FF7043"),
            ("b5_1_t", "Buck 5V_1 Nhiệt độ 1/2:", "29 / 30 °C", "#FFD54F"),
            ("b5_2_v", "Buck 5V_2 Vout 1/2:", "5190 / 5185 mV", "#00E676"),
            ("b5_2_i", "Buck 5V_2 Iout 1/2:", "1450 / 1100 mA", "#FF7043"),
            ("b5_2_t", "Buck 5V_2 Nhiệt độ 1/2:", "28 / 29 °C", "#FFD54F"),
        ]

        for k, name, init_val, col in b5_items:
            r_frame = ctk.CTkFrame(b5_grid, fg_color=VIETTEL_CARD_BG, corner_radius=4, height=26)
            r_frame.pack(fill="x", padx=2, pady=1.5)
            ctk.CTkLabel(r_frame, text=name, font=ctk.CTkFont(size=10), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=6)
            lbl = ctk.CTkLabel(r_frame, text=init_val, font=ctk.CTkFont(family="Consolas", size=10, weight="bold"), text_color=col)
            lbl.pack(side="right", padx=6)
            self.group_val_labels[k] = lbl

        # BẢNG CHI TIẾT ĐẦY ĐỦ 36 THANH GHI MODBUS
        full_table_frame = ctk.CTkFrame(parent, fg_color=VIETTEL_CARD_BG, corner_radius=8, border_width=1, border_color=VIETTEL_BORDER)
        full_table_frame.pack(fill="x", padx=6, pady=(8, 8))

        tbl_title_bar = ctk.CTkFrame(full_table_frame, height=30, fg_color="#2E1C20", corner_radius=6)
        tbl_title_bar.pack(fill="x", padx=6, pady=(6, 4))
        ctk.CTkLabel(
            tbl_title_bar,
            text="📋 BẢNG CHI TIẾT 36 THANH GHI MODBUS READ (SLAVE ID 01, BAUDRATE 921600-8-N-1: ADDR 0 .. 35)",
            font=ctk.CTkFont(size=11, weight="bold"), text_color=VIETTEL_TEXT_WHITE
        ).pack(side="left", padx=8, pady=3)

        # Header bảng
        hdr = ctk.CTkFrame(full_table_frame, height=28, fg_color="#2D1E22", corner_radius=4)
        hdr.pack(fill="x", padx=6, pady=(2, 2))
        ctk.CTkLabel(hdr, text="Addr", width=45, font=ctk.CTkFont(size=10, weight="bold"), text_color=VIETTEL_RED_LIGHT).pack(side="left", padx=2)
        ctk.CTkLabel(hdr, text="Tên thanh ghi (Name)", width=230, anchor="w", font=ctk.CTkFont(size=10, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=4)
        ctk.CTkLabel(hdr, text="Giá trị Raw (00000)", width=120, anchor="e", font=ctk.CTkFont(size=10, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=4)
        ctk.CTkLabel(hdr, text="HEX", width=70, anchor="center", font=ctk.CTkFont(size=10, weight="bold"), text_color=VIETTEL_TEXT_GRAY).pack(side="left", padx=3)
        ctk.CTkLabel(hdr, text="Quy đổi chuẩn (Scale)", width=140, anchor="center", font=ctk.CTkFont(size=10, weight="bold"), text_color="#00E676").pack(side="left", padx=4)
        ctk.CTkLabel(hdr, text="Mô tả chức năng", anchor="w", font=ctk.CTkFont(size=10, weight="bold"), text_color=VIETTEL_TEXT_GRAY).pack(side="left", fill="x", expand=True, padx=4)

        for reg in POWER_READ_REGISTERS:
            idx = reg["index"]
            row_bg = "#1E1618" if idx % 2 == 0 else "#251B1E"

            row = ctk.CTkFrame(full_table_frame, height=26, fg_color=row_bg, corner_radius=3)
            row.pack(fill="x", padx=6, pady=1)

            ctk.CTkLabel(row, text=f"{idx}", width=45, font=ctk.CTkFont(family="Consolas", size=10, weight="bold"), text_color=VIETTEL_TEXT_GRAY).pack(side="left", padx=2)
            ctk.CTkLabel(row, text=f"  {reg['name']}", width=230, anchor="w", font=ctk.CTkFont(size=10, weight="bold"), text_color=VIETTEL_TEXT_WHITE).pack(side="left", padx=4)

            lbl_val = ctk.CTkLabel(row, text="0", width=120, anchor="e", font=ctk.CTkFont(family="Consolas", size=11, weight="bold"), text_color="#00E676")
            lbl_val.pack(side="left", padx=4)

            lbl_hex = ctk.CTkLabel(row, text="0x0000", width=70, anchor="center", font=ctk.CTkFont(family="Consolas", size=10), text_color=VIETTEL_TEXT_GRAY)
            lbl_hex.pack(side="left", padx=3)

            lbl_scale = ctk.CTkLabel(row, text="0.0", width=140, anchor="center", font=ctk.CTkFont(family="Consolas", size=10, weight="bold"), text_color="#FFD54F")
            lbl_scale.pack(side="left", padx=4)

            ctk.CTkLabel(row, text=reg["desc"], anchor="w", font=ctk.CTkFont(size=10), text_color=VIETTEL_TEXT_GRAY).pack(side="left", fill="x", expand=True, padx=4)

            self.read_row_labels[idx] = {
                "val": lbl_val,
                "hex": lbl_hex,
                "scale": lbl_scale
            }

    # -------------------------------------------------------------------------
    # HÀNH ĐỘNG ĐIỀU KHIỂN NGUỒN: DUY NHẤT LÀ SET STATE (1 HOẶC 0)
    # -------------------------------------------------------------------------
    def _set_state(self, state: int):
        """Đặt trạng thái State = 1 (BẬT NGUỒN) hoặc State = 0 (TẮT NGUỒN)"""
        s = 1 if state != 0 else 0
        if hasattr(self.conn, 'set_power_state'):
            self.conn.set_power_state(s)
        self._update_state_ui(s)

    def _update_state_ui(self, s: int):
        if getattr(self, "_last_pwr_state", None) == s:
            return
        self._last_pwr_state = s
        if s == 1:
            self.lbl_state_badge.configure(text="BẬT (STATE = 1)", text_color="#00E676")
            self.btn_set_state_1.configure(fg_color="#1E8E3E", hover_color="#16692D")
            self.btn_set_state_0.configure(fg_color="#4D353A", hover_color="#332427")
        else:
            self.lbl_state_badge.configure(text="TẮT (STATE = 0)", text_color=VIETTEL_RED)
            self.btn_set_state_1.configure(fg_color="#332427", hover_color="#4D353A")
            self.btn_set_state_0.configure(fg_color=VIETTEL_RED, hover_color=VIETTEL_RED_HOVER)

    def _on_subtab_changed(self):
        """Xử lý khi người dùng chuyển giữa 2 chế độ: 10 Read (Phase-Shift) hoặc 36 Read (Nguồn tổng)"""
        sel = self.sub_tabview.get()
        if hasattr(self.conn, 'set_power_read_count'):
            count = 10 if "10" in sel else 36
            self.conn.set_power_read_count(count)

    # -------------------------------------------------------------------------
    # CẬP NHẬT DỮ LIỆU TELEMETRY (GỌI ĐỊNH KỲ TỪ MAIN GUI MỖI 500MS)
    # -------------------------------------------------------------------------
    def update_telemetry(self, d: Dict[str, Any]):
        pwr_state = d.get("pwr_state", 0)
        self._update_state_ui(pwr_state)

        # 1. CẬP NHẬT 10 THÔNG SỐ ĐIỀU KHIỂN & BẢO VỆ PHASE-SHIFT (ĐỌC VỀ TỪ MODBUS)
        pwr_ctrl = d.get("pwr_ctrl_regs", [0] * 10)
        while len(pwr_ctrl) < 10:
            pwr_ctrl.append(0)

        for reg in POWER_WRITE_REGISTERS:
            idx = reg["index"]
            v_raw = pwr_ctrl[idx]

            # Cập nhật Thẻ Card
            if idx in self.phase_shift_labels:
                w = self.phase_shift_labels[idx]
                _safe_configure_label(w["hex"], f"0x{(v_raw & 0xFFFF):04X}")

                if idx == 0:
                    if v_raw == 1:
                        _safe_configure_label(w["val"], "🟢 BẬT (1)", "#00E676")
                    else:
                        _safe_configure_label(w["val"], "⚪ TẮT (0)", VIETTEL_RED)
                    _safe_configure_label(w["scale"], "")
                elif idx in (4, 5):
                    _safe_configure_label(w["val"], f"{v_raw}", VIETTEL_TEXT_WHITE)
                    _safe_configure_label(w["scale"], f"({v_raw * 0.001:.2f} V)")
                elif idx == 6:
                    _safe_configure_label(w["val"], f"{v_raw}", VIETTEL_TEXT_WHITE)
                    _safe_configure_label(w["scale"], f"({v_raw * 0.001:.2f} A)")
                elif idx == 1:
                    _safe_configure_label(w["val"], f"{v_raw}", VIETTEL_TEXT_WHITE)
                    _safe_configure_label(w["scale"], "ms")
                elif idx == 8:
                    _safe_configure_label(w["val"], f"{v_raw}", "#FFD54F")
                    _safe_configure_label(w["scale"], "RPM")
                elif idx == 9:
                    _safe_configure_label(w["val"], f"{v_raw}", VIETTEL_TEXT_WHITE)
                    _safe_configure_label(w["scale"], "ns")
                elif idx == 7:
                    _safe_configure_label(w["val"], f"{v_raw}", "#00E676" if v_raw == 0 else VIETTEL_RED)
                    _safe_configure_label(w["scale"], "(Bình thường)" if v_raw == 0 else "(LỖI)")
                else:
                    _safe_configure_label(w["val"], f"{v_raw}", VIETTEL_TEXT_WHITE)
                    _safe_configure_label(w["scale"], "")

            # Cập nhật Hàng Bảng chi tiết Phase-Shift
            if idx in self.phase_shift_row_labels:
                rw = self.phase_shift_row_labels[idx]
                _safe_configure_label(rw["val"], f"{v_raw}")
                _safe_configure_label(rw["hex"], f"0x{(v_raw & 0xFFFF):04X}")
                if idx == 0:
                    _safe_configure_label(rw["scale"], "BẬT (1)" if v_raw == 1 else "TẮT (0)", "#00E676" if v_raw == 1 else VIETTEL_RED)
                elif idx in (4, 5):
                    _safe_configure_label(rw["scale"], f"{v_raw * 0.001:.2f} V", "#00E676")
                elif idx == 6:
                    _safe_configure_label(rw["scale"], f"{v_raw * 0.001:.2f} A", "#FF7043")
                elif idx == 1:
                    _safe_configure_label(rw["scale"], f"{v_raw} ms", VIETTEL_TEXT_WHITE)
                elif idx == 8:
                    _safe_configure_label(rw["scale"], f"{v_raw} RPM", "#FFD54F")
                elif idx == 9:
                    _safe_configure_label(rw["scale"], f"{v_raw} ns", VIETTEL_TEXT_WHITE)
                elif idx == 7:
                    _safe_configure_label(rw["scale"], "OK (0)" if v_raw == 0 else f"ERR ({v_raw})", "#00E676" if v_raw == 0 else VIETTEL_RED)
                else:
                    _safe_configure_label(rw["scale"], f"{v_raw}")

        # 2. CẬP NHẬT 36 THANH GHI HỆ THỐNG NGUỒN TỔNG
        pwr_read = d.get("pwr_read_regs", [0] * 36)
        while len(pwr_read) < 36:
            pwr_read.append(0)

        # Cập nhật bảng chi tiết 36 thanh ghi
        for reg in POWER_READ_REGISTERS:
            idx = reg["index"]
            if idx in self.read_row_labels:
                v_raw = pwr_read[idx]
                w = self.read_row_labels[idx]
                _safe_configure_label(w["val"], f"{v_raw}")
                _safe_configure_label(w["hex"], f"0x{(v_raw & 0xFFFF):04X}")

                scale = reg.get("scale", 1.0)
                unit_s = reg.get("scale_unit", "")
                val_scaled = v_raw * scale
                if scale < 1.0:
                    _safe_configure_label(w["scale"], f"{val_scaled:.2f} {unit_s}")
                else:
                    _safe_configure_label(w["scale"], f"{int(val_scaled)} {unit_s}")

        # Cập nhật 6 thẻ Hero
        vbus = pwr_read[29] * 0.01
        vout_m = pwr_read[30] * 0.01
        iout_m = pwr_read[31] * 0.01
        vout_s = pwr_read[32] * 0.01
        fanspeed = pwr_read[35]
        err_m = pwr_read[28]
        err_s = pwr_read[34]

        if "vbus" in self.hero_labels:
            _safe_configure_label(self.hero_labels["vbus"], f"{vbus:.2f}")
            _safe_configure_label(self.hero_labels["vout_master"], f"{vout_m:.2f}")
            _safe_configure_label(self.hero_labels["iout_master"], f"{iout_m:.2f}")
            _safe_configure_label(self.hero_labels["vout_slave"], f"{vout_s:.2f}")
            _safe_configure_label(self.hero_labels["fanspeed"], f"{fanspeed}")
            err_ok = (err_m == 0 and err_s == 0)
            _safe_configure_label(
                self.hero_labels["err_code"],
                f"{err_m} / {err_s}" + (" (OK)" if err_ok else " (ERR)"),
                "#00E676" if err_ok else VIETTEL_RED
            )

        # Cập nhật các thẻ nhóm
        if "reg_0" in self.group_val_labels:
            _safe_configure_label(self.group_val_labels["reg_0"], f"{pwr_read[0]} mV ({pwr_read[0]*0.001:.2f} V)")
            _safe_configure_label(self.group_val_labels["reg_1"], f"{pwr_read[1]} mA ({pwr_read[1]*0.001:.2f} A)")
            _safe_configure_label(self.group_val_labels["reg_2"], f"{pwr_read[2]} mV ({pwr_read[2]*0.001:.2f} V)")
            _safe_configure_label(self.group_val_labels["reg_3"], f"{pwr_read[3]} mA ({pwr_read[3]*0.001:.2f} A)")

            _safe_configure_label(self.group_val_labels["reg_28_34"], f"{err_m} / {err_s} (OK)" if err_ok else f"{err_m} / {err_s} (ERROR)")
            _safe_configure_label(self.group_val_labels["reg_29"], f"{pwr_read[29]} ({vbus:.2f} V)")
            _safe_configure_label(self.group_val_labels["reg_30_31"], f"{vout_m:.2f} V / {iout_m:.2f} A")
            _safe_configure_label(self.group_val_labels["reg_32_33"], f"{vout_s:.2f} V / {pwr_read[33]*0.01:.2f} A")

            _safe_configure_label(self.group_val_labels["b12_1_v"], f"{pwr_read[4]} / {pwr_read[5]} mV")
            _safe_configure_label(self.group_val_labels["b12_1_i"], f"{pwr_read[6]} / {pwr_read[7]} mA")
            _safe_configure_label(self.group_val_labels["b12_1_t"], f"{pwr_read[8]} / {pwr_read[9]} °C")
            _safe_configure_label(self.group_val_labels["b12_2_v"], f"{pwr_read[10]} / {pwr_read[11]} mV")
            _safe_configure_label(self.group_val_labels["b12_2_i"], f"{pwr_read[12]} / {pwr_read[13]} mA")
            _safe_configure_label(self.group_val_labels["b12_2_t"], f"{pwr_read[14]} / {pwr_read[15]} °C")

            _safe_configure_label(self.group_val_labels["b5_1_v"], f"{pwr_read[16]} / {pwr_read[17]} mV")
            _safe_configure_label(self.group_val_labels["b5_1_i"], f"{pwr_read[18]} / {pwr_read[19]} mA")
            _safe_configure_label(self.group_val_labels["b5_1_t"], f"{pwr_read[20]} / {pwr_read[21]} °C")
            _safe_configure_label(self.group_val_labels["b5_2_v"], f"{pwr_read[22]} / {pwr_read[23]} mV")
            _safe_configure_label(self.group_val_labels["b5_2_i"], f"{pwr_read[24]} / {pwr_read[25]} mA")
            _safe_configure_label(self.group_val_labels["b5_2_t"], f"{pwr_read[26]} / {pwr_read[27]} °C")
