"""
VIETTEL PROPULSION & POWER CONTROL SUITE - PRODUCTION THEME SYSTEM
File: viettel_theme.py
Hệ thống thiết kế chuẩn công nghiệp quân sự / hàng không vũ trụ (Military / Aerospace SCADA)
Nhận diện thương hiệu Viettel High-Tech VMC.
Sử dụng bộ font chữ chuẩn thương hiệu: FS PF BeauSans Pro
"""

import os
import ctypes
import customtkinter as ctk

# =============================================================================
# 1. BẢNG MÀU CHUẨN AEROSPACE OBSIDIAN & VIETTEL RED
# =============================================================================
COLOR_BG            = "#0A0D12"  # Nền tối Obsidian sâu, triệt tiêu phản chiếu
COLOR_HEADER_BG     = "#0F141C"  # Thanh tiêu đề / Header
COLOR_PANEL_BG      = "#0F141C"  # Nền tab container / Khung chức năng
COLOR_CARD_BG       = "#141B24"  # Khung Card nổi (Elevated card)
COLOR_CARD_BG_HOVER = "#192230"  # Hover trên card
COLOR_CARD_INNER    = "#0D1117"  # Khung con lồng ghép / Bảng dữ liệu
COLOR_ROW_ALT1      = "#111721"  # Dòng xen kẽ 1
COLOR_ROW_ALT2      = "#151D28"  # Dòng xen kẽ 2

COLOR_BORDER        = "#1E293B"  # Viền khung chính (Slate)
COLOR_BORDER_SUBTLE = "#16202C"  # Viền mờ nhẹ
COLOR_BORDER_RED    = "#4D121B"  # Viền đỏ Viettel điểm nhấn
COLOR_BORDER_FOCUS  = "#EE0033"  # Viền khi focus / active

# Màu thương hiệu Viettel
VIETTEL_RED         = "#EE0033"  # Đỏ Viettel chuẩn nhận diện
VIETTEL_RED_HOVER   = "#C40028"  # Đỏ khi hover
VIETTEL_RED_LIGHT   = "#FF335C"  # Đỏ nhạt điểm nhấn
VIETTEL_RED_GLOW    = "#FF1744"  # Đỏ rực rỡ LED

# Màu trạng thái tiêu chuẩn công nghiệp (Safety / SCADA Colors)
COLOR_SUCCESS       = "#10B981"  # Xanh lục Emerald - Bình thường / Đang chạy
COLOR_SUCCESS_HOVER = "#059669"  # Xanh lục hover
COLOR_SUCCESS_GLOW  = "#00E676"  # Xanh lục LED neon
COLOR_CYAN          = "#00D2FF"  # Cyan điện tử - Đo lường tốc độ, vị trí
COLOR_WARNING       = "#F59E0B"  # Vàng hổ phách - Cảnh báo, cân bằng cell
COLOR_WARNING_LIGHT = "#FBBF24"  # Vàng nhạt
COLOR_CRITICAL      = "#EF4444"  # Đỏ khẩn cấp - Lỗi quá nhiệt, quá áp
COLOR_BLUE_SEL      = "#2563EB"  # Xanh dương chọn lọc Modbus
COLOR_PURPLE        = "#A855F7"  # Tím xung nhịp / Hall sensor

# Bảng phân cấp chữ (Typography Hierarchy)
COLOR_TEXT_WHITE    = "#F8FAFC"  # Chữ chính - Trắng ngà sắc nét
COLOR_TEXT_GRAY     = "#94A3B8"  # Chữ phụ / nhãn - Slate 400
COLOR_TEXT_MUTED    = "#64748B"  # Chữ mờ / đơn vị / hex - Slate 500
COLOR_TEXT_DARK     = "#334155"  # Chữ nền mờ

# =============================================================================
# 2. BỘ PHÔNG CHỮ THƯƠNG HIỆU VIETTEL: FS PF BeauSans Pro
# =============================================================================
FONT_PRIMARY = "FS PF BeauSans Pro"
FONT_MONO    = "Consolas"

def load_custom_fonts():
    """Tự động nạp font FS PF BeauSans Pro từ thư mục ứng dụng nếu có file .ttf / .otf"""
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        font_dirs = [base_dir, os.path.join(base_dir, "fonts")]
        for fdir in font_dirs:
            if os.path.exists(fdir):
                for file in os.listdir(fdir):
                    if file.lower().endswith((".ttf", ".otf")) and any(k in file.lower() for k in ["beau", "pf", "fs"]):
                        full_path = os.path.join(fdir, file)
                        # FR_PRIVATE = 0x10 (Nạp font cho riêng process hiện tại)
                        ctypes.windll.gdi32.AddFontResourceExW(full_path, 0x10, 0)
    except Exception:
        pass

# Thực thi nạp font lúc khởi động module
load_custom_fonts()

def font_brand():
    return ctk.CTkFont(family=FONT_PRIMARY, size=17, weight="bold")

def font_section_title():
    return ctk.CTkFont(family=FONT_PRIMARY, size=12, weight="bold")

def font_card_label():
    return ctk.CTkFont(family=FONT_PRIMARY, size=10, weight="bold")

def font_body(size: int = 11, weight: str = "normal"):
    return ctk.CTkFont(family=FONT_PRIMARY, size=size, weight=weight)

def font_btn(size: int = 11, weight: str = "bold"):
    return ctk.CTkFont(family=FONT_PRIMARY, size=size, weight=weight)

def font_digital_lg():
    return ctk.CTkFont(family=FONT_MONO, size=18, weight="bold")

def font_digital_md():
    return ctk.CTkFont(family=FONT_MONO, size=14, weight="bold")

def font_digital_sm():
    return ctk.CTkFont(family=FONT_MONO, size=11, weight="bold")

def font_mono():
    return ctk.CTkFont(family=FONT_MONO, size=10)

def font_mono_sm():
    return ctk.CTkFont(family=FONT_MONO, size=9)

# =============================================================================
# 3. TIỆN ÍCH CẬP NHẬT GIAO DIỆN CHỐNG GIẬT LAG (DIRTY CHECKING)
# =============================================================================
def safe_configure_label(lbl, text: str, text_color: str = None):
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

def safe_set_progress_bar(bar, ratio: float, color: str = None):
    """Cập nhật thanh tiến trình mượt mà không nhấp nháy"""
    if bar is None:
        return
    cached_ratio = getattr(bar, "_cached_ratio", None)
    cached_color = getattr(bar, "_cached_color", None)
    if cached_ratio is None or abs(cached_ratio - ratio) > 0.005:
        bar.set(ratio)
        bar._cached_ratio = ratio
    if color and cached_color != color:
        bar.configure(progress_color=color)
        bar._cached_color = color
