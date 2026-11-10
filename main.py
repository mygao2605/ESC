"""
MGM ProTool - Điểm khởi chạy chính của ứng dụng Python (Entry point)
Phát triển cho Viettel - Tương thích hoàn chỉnh với hệ sinh thái MGM Compro ESC / BMS Controllers.
"""

import sys
import os

# Đảm bảo thư mục hiện tại nằm trong sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mgm_gui import main

if __name__ == "__main__":
    main()
