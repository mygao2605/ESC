"""
MGM ProTool Data Engine
Chịu trách nhiệm giải mã và nạp toàn bộ cấu hình, thông số, kênh đo và sự kiện
từ các file cấu hình chuẩn của MGM Compro (device.ini, parameter.ini, metadata.ini, event.ini)
sử dụng thuật toán XOR 0xE0.
"""

import os
import json
import logging

logger = logging.getLogger("MGM_Data")

DEFAULT_MGM_PATH = r"C:\Program Files (x86)\MGM Compro\MGM ProTool"

def decode_ini_content(raw_bytes: bytes) -> str:
    """Giải mã file INI bị mã hóa bằng byte XOR 0xE0"""
    return bytes(b ^ 0xE0 for b in raw_bytes).decode('latin-1', errors='replace')

def parse_raw_ini(text: str) -> dict:
    """Phân tích cấu trúc file INI thành dictionary của các section"""
    sections = {}
    current = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(';'):
            continue
        if line.startswith('[') and line.endswith(']'):
            current = line[1:-1]
            if current not in sections:
                sections[current] = []
            sections[current].append({})
        elif current and '=' in line:
            k, v = line.split('=', 1)
            sections[current][-1][k.strip()] = v.strip()
    return sections

class MGMDatabase:
    """Quản lý toàn bộ cơ sở dữ liệu thiết bị, tham số, telemetry và sự kiện của MGM Compro"""
    def __init__(self, mgm_dir: str = None):
        self.mgm_dir = mgm_dir or DEFAULT_MGM_PATH
        self.devices = {}       # id -> dict
        self.parameters = {}    # id -> dict
        self.telemetry = {}     # id -> dict
        self.events = {}        # id -> dict
        self.categories = [
            "Tất cả (All)",
            "Cơ bản (Basic)",
            "Động cơ (Motor)",
            "Pin & Nguồn (Battery)",
            "Điều khiển & Phanh (Controller & Brake)",
            "Tay ga & Tín hiệu (IN/OUT Throttle)",
            "Nhiệt độ & Bảo vệ (Temperature)",
            "Dữ liệu & Truyền thông (Data/Comm)",
            "BMS & Cân bằng Pin (BMS)",
            "Nâng cao & Khác (Special & Advanced)"
        ]
        self.load_all()

    def _read_file(self, filename: str) -> str:
        # Kiểm tra thư mục cài đặt MGM trước, sau đó tìm trong thư mục hiện tại
        candidates = [
            os.path.join(self.mgm_dir, filename),
            os.path.join(os.path.dirname(__file__), filename),
            os.path.join(os.path.dirname(__file__), "config", filename)
        ]
        for p in candidates:
            if os.path.exists(p):
                try:
                    with open(p, 'rb') as f:
                        return decode_ini_content(f.read())
                except Exception as e:
                    logger.error(f"Lỗi đọc file {p}: {e}")
        return ""

    def load_all(self):
        self._load_devices()
        self._load_parameters()
        self._load_telemetry()
        self._load_events()

    def _load_devices(self):
        text = self._read_file("device.ini")
        if not text:
            # Dữ liệu dự phòng nếu chưa cài MGM ProTool
            self._fallback_devices()
            return
        parsed = parse_raw_ini(text)
        for sec, items in parsed.items():
            if sec.startswith("DEVICE_"):
                try:
                    dev_id = int(sec.split("_")[1])
                    d = items[0]
                    name = d.get("name_en", d.get("name_cz", f"Device {dev_id}"))
                    self.devices[dev_id] = {
                        "id": dev_id,
                        "name": name,
                        "name_cz": d.get("name_cz", name),
                        "settings": int(d.get("settings", 1)),
                        "monitoring": int(d.get("monitoring", 1)),
                        "history": int(d.get("history", 1)),
                        "log": int(d.get("log", 1)),
                        "command_file": d.get("commandFile", "")
                    }
                except Exception:
                    pass

    def _load_parameters(self):
        text = self._read_file("parameter.ini")
        if not text:
            return
        parsed = parse_raw_ini(text)
        for sec, items in parsed.items():
            if sec.startswith("PARAMETER_"):
                try:
                    pid = int(sec.split("_")[1])
                    d = items[0]
                    dev_str = d.get("device", "")
                    dev_ids = [int(x.strip()) for x in dev_str.split(",") if x.strip().isdigit()]
                    name = d.get("name_en", d.get("name_cz", f"Param {pid}"))
                    unit = d.get("unit_en", d.get("unit_cz", ""))
                    
                    options = []
                    for i in range(50):
                        k_en = f"item{i}_en"
                        k_cz = f"item{i}_cz"
                        if k_en in d:
                            options.append(d[k_en])
                        elif k_cz in d:
                            options.append(d[k_cz])
                        else:
                            break

                    category = self._classify_category(name)

                    self.parameters[pid] = {
                        "id": pid,
                        "name": name,
                        "name_cz": d.get("name_cz", name),
                        "unit": unit,
                        "devices": dev_ids,
                        "options": options,
                        "category": category,
                        "is_enum": len(options) > 0,
                        "default_val": options[0] if options else "0"
                    }
                except Exception:
                    pass

    def _classify_category(self, name: str) -> str:
        name_upper = name.upper()
        if name_upper.startswith("MOTOR") or "POLE" in name_upper or "KV" in name_upper or "TIMING" in name_upper:
            return "Động cơ (Motor)"
        elif name_upper.startswith("BATTERY") or "VOLTAGE" in name_upper or "CELL" in name_upper or "LIPO" in name_upper:
            return "Pin & Nguồn (Battery)"
        elif name_upper.startswith("IN/OUT") or "THROTTLE" in name_upper or "PWM PULSE" in name_upper or "PLYNU" in name_upper:
            return "Tay ga & Tín hiệu (IN/OUT Throttle)"
        elif name_upper.startswith("TEMPERATURE") or "TEPLOTA" in name_upper or "THERMAL" in name_upper:
            return "Nhiệt độ & Bảo vệ (Temperature)"
        elif name_upper.startswith("DATA/COMM") or "UART" in name_upper or "CAN" in name_upper or "BAUD" in name_upper:
            return "Dữ liệu & Truyền thông (Data/Comm)"
        elif name_upper.startswith("CONTROLLER") or "BRAKE" in name_upper or "PID" in name_upper or "RAMP" in name_upper:
            return "Điều khiển & Phanh (Controller & Brake)"
        elif "BMS" in name_upper or "BALANC" in name_upper:
            return "BMS & Cân bằng Pin (BMS)"
        elif name.startswith("P1.") or name.startswith("P2.") or name.startswith("P3.") or name.startswith("P4.") or name.startswith("P5.") or name.startswith("P6."):
            return "Cơ bản (Basic)"
        return "Nâng cao & Khác (Special & Advanced)"

    def _load_telemetry(self):
        text = self._read_file("metadata.ini")
        if not text:
            return
        parsed = parse_raw_ini(text)
        for sec, items in parsed.items():
            if sec.startswith("PARAMETER_"):
                try:
                    tid = int(sec.split("_")[1])
                    d = items[0]
                    dev_str = d.get("device", "")
                    dev_ids = [int(x.strip()) for x in dev_str.split(",") if x.strip().isdigit()]
                    name = d.get("name_en", d.get("name_cz", f"Channel {tid}"))
                    unit = d.get("unit_en", d.get("unit_cz", ""))
                    self.telemetry[tid] = {
                        "id": tid,
                        "name": name,
                        "name_cz": d.get("name_cz", name),
                        "unit": unit,
                        "devices": dev_ids
                    }
                except Exception:
                    pass

    def _load_events(self):
        text = self._read_file("event.ini")
        if not text:
            return
        parsed = parse_raw_ini(text)
        for sec, items in parsed.items():
            if sec.startswith("PARAMETER_"):
                try:
                    eid = int(sec.split("_")[1])
                    d = items[0]
                    dev_str = d.get("device", "")
                    dev_ids = [int(x.strip()) for x in dev_str.split(",") if x.strip().isdigit()]
                    self.events[eid] = {
                        "id": eid,
                        "text": d.get("text_en", d.get("text_cz", f"Event #{eid}")),
                        "text_cz": d.get("text_cz", ""),
                        "priority": int(d.get("priority", 5)),
                        "devices": dev_ids
                    }
                except Exception:
                    pass

    def _fallback_devices(self):
        """Danh sách thiết bị mặc định tiêu biểu của MGM COMPRO"""
        self.devices = {
            10: {"id": 10, "name": "HBC-Series ESC", "settings": 1, "monitoring": 1, "history": 1, "log": 1},
            7: {"id": 7, "name": "X2-Series ESC", "settings": 1, "monitoring": 1, "history": 1, "log": 1},
            8: {"id": 8, "name": "X2-Series PRO", "settings": 1, "monitoring": 1, "history": 1, "log": 1},
            13: {"id": 13, "name": "HBC-Multicopter", "settings": 1, "monitoring": 1, "history": 1, "log": 1},
            1001: {"id": 1001, "name": "HBCi-Series (NextGen)", "settings": 1, "monitoring": 1, "history": 1, "log": 1},
            1002: {"id": 1002, "name": "X3-SERIES", "settings": 1, "monitoring": 1, "history": 1, "log": 1},
            101: {"id": 101, "name": "BMS-16i Battery Management", "settings": 1, "monitoring": 1, "history": 1, "log": 1},
            100: {"id": 100, "name": "BMS-8i Battery Management", "settings": 1, "monitoring": 1, "history": 1, "log": 1},
        }

    def get_parameters_for_device(self, device_id: int, category: str = "Tất cả (All)"):
        """Lọc danh sách tham số theo mã thiết bị và danh mục"""
        res = []
        for p in self.parameters.values():
            if not p["devices"] or device_id in p["devices"]:
                if category == "Tất cả (All)" or p["category"] == category:
                    res.append(p)
        res.sort(key=lambda x: x["id"])
        return res

    def get_telemetry_for_device(self, device_id: int):
        """Lọc các kênh đo telemetry theo thiết bị"""
        res = []
        for t in self.telemetry.values():
            if not t["devices"] or device_id in t["devices"]:
                res.append(t)
        res.sort(key=lambda x: x["id"])
        return res
