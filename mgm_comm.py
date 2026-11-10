"""
MGM Compro & Viettel BLDC Driver Communication Layer (Modbus RTU & MGM Protocol)
Tích hợp giao thức chuẩn Modbus RTU theo bản tin thực tế (bantin.jpeg):
- Serial: Port COM11 (hoặc tùy chọn), Baudrate 921600, 8-N-1
- Slave ID = 1, Scan Rate (SR) = 500ms
- Modbus Read (F = 03 - Read Holding Registers, Start = 0, Qty = 11):
    [0] StateAct     : Trạng thái hoạt động thực tế
    [1] SpeedRpm     : Tốc độ vòng quay thực tế (RPM)
    [2] DcBusVolt    : Điện áp DC Bus (V)
    [3] D_Curr       : Dòng điện trục D (Id)
    [4] Q_Curr       : Dòng điện trục Q (Iq)
    [5] Fault_H      : Thanh ghi mã lỗi cao (Fault High)
    [6] Fault_L      : Thanh ghi mã lỗi thấp (Fault Low)
    [7] MotorTemp    : Nhiệt độ động cơ (°C)
    [8] TempA        : Nhiệt độ pha A (°C)
    [9] TempB        : Nhiệt độ pha B (°C)
    [10] TempC       : Nhiệt độ pha C (°C)
- Modbus Write (F = 16 / 0x10 - Write Multiple Registers, Start = 0, Qty = 2):
    [0] ON/OFF       : Lệnh bật/tắt động cơ (0 = OFF, 1 = ON)
    [1] SpeedRpm     : Lệnh đặt tốc độ mục tiêu (RPM)
"""

import time
import math
import struct
import random
import threading
import logging
from typing import Dict, Any, List, Optional, Callable, Tuple
import serial
import serial.tools.list_ports

logger = logging.getLogger("MGM_Comm")

# Danh sách 11 thanh ghi đọc (F=03) theo đúng thứ tự trong bantin.jpeg
MODBUS_READ_REGISTERS = [
    {"index": 0,  "name": "StateAct",   "unit": "",    "desc": "Trạng thái thực tế (0: OFF/IDLE, 1: RUN, 2: FAULT)"},
    {"index": 1,  "name": "SpeedRpm",   "unit": "RPM", "desc": "Tốc độ động cơ thực tế"},
    {"index": 2,  "name": "DcBusVolt",  "unit": "V",   "desc": "Điện áp DC Bus"},
    {"index": 3,  "name": "D_Curr",     "unit": "A",   "desc": "Dòng điện trục D (Id)"},
    {"index": 4,  "name": "Q_Curr",     "unit": "A",   "desc": "Dòng điện trục Q (Iq)"},
    {"index": 5,  "name": "Fault_H",    "unit": "HEX", "desc": "Thanh ghi lỗi Word cao (High)"},
    {"index": 6,  "name": "Fault_L",    "unit": "HEX", "desc": "Thanh ghi lỗi Word thấp (Low)"},
    {"index": 7,  "name": "MotorTemp",  "unit": "°C",  "desc": "Nhiệt độ động cơ (Motor)"},
    {"index": 8,  "name": "TempA",      "unit": "°C",  "desc": "Nhiệt độ pha A (IGBT/MOSFET A)"},
    {"index": 9,  "name": "TempB",      "unit": "°C",  "desc": "Nhiệt độ pha B (IGBT/MOSFET B)"},
    {"index": 10, "name": "TempC",      "unit": "°C",  "desc": "Nhiệt độ pha C (IGBT/MOSFET C)"},
]

# Danh sách 2 thanh ghi ghi (F=16) theo đúng thứ tự trong bantin.jpeg
MODBUS_WRITE_REGISTERS = [
    {"index": 0, "name": "ON/OFF",   "unit": "0/1", "desc": "Lệnh Bật / Tắt động cơ (0: OFF, 1: ON)"},
    {"index": 1, "name": "SpeedRpm", "unit": "RPM", "desc": "Lệnh đặt tốc độ mục tiêu (Target RPM)"},
]


# =============================================================================
# HÀM TIỆN ÍCH MODBUS RTU (CRC16 & FRAME BUILDER / PARSER)
# =============================================================================
def calc_crc16(data: bytes) -> int:
    """Tính mã kiểm tra CRC-16 chuẩn Modbus RTU (Đa thức 0xA001, Init 0xFFFF)"""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def append_crc16(pdu: bytes) -> bytes:
    """Gắn 2 byte CRC16 (Low byte trước, High byte sau) vào cuối khung tin Modbus"""
    crc = calc_crc16(pdu)
    return pdu + bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def verify_crc16(frame: bytes) -> bool:
    """Kiểm tra tính hợp lệ CRC16 của khung tin nhận được"""
    if len(frame) < 4:
        return False
    calc = calc_crc16(frame[:-2])
    recv = frame[-2] | (frame[-1] << 8)
    return calc == recv


def to_int16(val: int) -> int:
    """Chuyển số nguyên sang phạm vi signed 16-bit (-32768 .. 32767)"""
    val = int(val) & 0xFFFF
    return val - 0x10000 if val >= 0x8000 else val


def to_uint16(val: int) -> int:
    """Chuyển số nguyên sang phạm vi unsigned 16-bit (0 .. 65535)"""
    return int(val) & 0xFFFF


def build_fc03_request(slave_id: int = 1, start_addr: int = 0, count: int = 11) -> bytes:
    """Tạo khung lệnh Modbus RTU Function 03 (Read Holding Registers)"""
    pdu = struct.pack(">BBHH", slave_id & 0xFF, 0x03, start_addr & 0xFFFF, count & 0xFFFF)
    return append_crc16(pdu)


def parse_fc03_response(frame: bytes, expected_slave: int = 1, expected_count: int = 11) -> Optional[List[int]]:
    """Giải mã khung phản hồi Function 03 thành danh sách các thanh ghi int16 có dấu"""
    expected_len = 5 + expected_count * 2
    if len(frame) < expected_len:
        return None
    frame = frame[:expected_len]
    if not verify_crc16(frame):
        return None
    slave_id, func_code, byte_count = frame[0], frame[1], frame[2]
    if slave_id != expected_slave or func_code != 0x03 or byte_count != expected_count * 2:
        return None
    regs = []
    for i in range(expected_count):
        offset = 3 + i * 2
        raw_val = struct.unpack(">h", frame[offset:offset + 2])[0]
        regs.append(raw_val)
    return regs


def build_fc16_request(slave_id: int = 1, start_addr: int = 0, values: List[int] = None) -> bytes:
    """Tạo khung lệnh Modbus RTU Function 16 / 0x10 (Write Multiple Registers)"""
    if values is None:
        values = [0, 0]
    count = len(values)
    byte_count = count * 2
    header = struct.pack(">BBHHB", slave_id & 0xFF, 0x10, start_addr & 0xFFFF, count & 0xFFFF, byte_count & 0xFF)
    payload = b"".join(struct.pack(">h", to_int16(v)) for v in values)
    return append_crc16(header + payload)


def parse_fc16_response(frame: bytes, expected_slave: int = 1, start_addr: int = 0, count: int = 2) -> bool:
    """Kiểm tra phản hồi 8 byte của lệnh Function 16 (0x10)"""
    if len(frame) < 8:
        return False
    frame = frame[:8]
    if not verify_crc16(frame):
        return False
    slave_id, func_code, r_addr, r_count = struct.unpack(">BBHH", frame[:6])
    return (slave_id == expected_slave and func_code == 0x10 and r_addr == (start_addr & 0xFFFF) and r_count == (count & 0xFFFF))


def get_available_ports() -> List[Dict[str, str]]:
    """Liệt kê danh sách cổng COM hiện có trên máy tính"""
    ports = []
    for p in serial.tools.list_ports.comports():
        desc = p.description or "Generic Serial Port"
        is_ftdi = "FTDI" in (p.manufacturer or "").upper() or "FT232" in desc.upper() or "USB" in desc.upper()
        ports.append({
            "device": p.device,
            "description": f"{p.device} - {desc}" + (" [USB/UART]" if is_ftdi else ""),
            "is_ftdi": is_ftdi
        })
    return ports


# =============================================================================
# BỘ MÔ PHỎNG ĐỘNG CƠ BLDC & MODBUS SLAVE (KHỚP 100% BANTIN.JPEG)
# =============================================================================
class MGMSimulator:
    """
    Bộ mô phỏng hoạt động thực tế của Viettel BLDC Driver qua Modbus RTU
    Khởi tạo mặc định khớp chính xác với giá trị trong ảnh bantin.jpeg:
    - Read (F=03):
        [0] StateAct   = 0
        [1] SpeedRpm   = 0
        [2] DcBusVolt  = 0 (khi OFF) / ~48V (khi ON)
        [3] D_Curr     = 9
        [4] Q_Curr     = -1
        [5] Fault_H    = 0
        [6] Fault_L    = 0
        [7] MotorTemp  = 30
        [8] TempA      = 24
        [9] TempB      = 26
        [10] TempC     = 26
    - Write (F=16):
        [0] ON/OFF     = 0
        [1] SpeedRpm   = 0
    """
    def __init__(self, device_id: int = 10, device_name: str = "Viettel BLDC Driver"):
        self.device_id = device_id
        self.device_name = device_name

        # 2 thanh ghi Write (F=16)
        self.cmd_on_off: int = 0
        self.cmd_speed_rpm: int = 0

        # 11 thanh ghi Read (F=03) khởi tạo đúng như ảnh bantin.jpeg
        self.reg_state_act: int = 0
        self.reg_speed_rpm: int = 0
        self.reg_dc_bus_volt: int = 0
        self.reg_d_curr: int = 9
        self.reg_q_curr: int = -1
        self.reg_fault_h: int = 0
        self.reg_fault_l: int = 0
        self.reg_motor_temp: int = 30
        self.reg_temp_a: int = 24
        self.reg_temp_b: int = 26
        self.reg_temp_c: int = 26

        # Biến thực phục vụ mô phỏng vật lý mượt mà
        self._actual_rpm_f: float = 0.0
        self._motor_temp_f: float = 30.0
        self._temp_a_f: float = 24.0
        self._temp_b_f: float = 26.0
        self._temp_c_f: float = 26.0
        self.consumed_ah: float = 0.0
        self.consumed_wh: float = 0.0

        # Bảng tham số cấu hình lưu trữ
        self.stored_params: Dict[int, Any] = {
            1: "memory bank 1",
            2: "one-way",
            3: "multicopter",
            4: "Modbus RTU (921600-8-N-1)",
            5: "safe start",
            6: "2000",
            7: "1500",
            8: "1000",
            10: "1500",
            20: "100",
            47: "14",
            50: "12000",
            51: "16",
            55: "1.2",
            83: "5",
            134: "5.2",
        }

        # Lịch sử sự kiện
        self.simulated_events: List[Dict[str, Any]] = [
            {"time": time.strftime("%H:%M:%S", time.localtime(time.time() - 90)), "code": 1, "prio": 5, "desc": "Khởi tạo cổng truyền thông Modbus RTU: Port 11 (921600-8-N-1), Slave ID = 1"},
            {"time": time.strftime("%H:%M:%S", time.localtime(time.time() - 45)), "code": 2, "prio": 5, "desc": "Bản tin F=03 (Read 11 thanh ghi) & F=16 (Write 2 thanh ghi) hoạt động ổn định (SR=500ms)"},
            {"time": time.strftime("%H:%M:%S", time.localtime(time.time() - 10)), "code": 3, "prio": 5, "desc": "Trạng thái ban đầu: StateAct=0, MotorTemp=30°C, TempA=24°C, TempB=26°C, TempC=26°C"},
        ]

        self._last_tick = time.time()

    def set_write_registers(self, on_off: int, target_rpm: int):
        """Cập nhật 2 thanh ghi điều khiển từ bản tin Modbus Write (F=16)"""
        prev_on = self.cmd_on_off
        self.cmd_on_off = 1 if int(on_off) != 0 else 0
        self.cmd_speed_rpm = int(target_rpm)

        if self.cmd_on_off != prev_on:
            state_str = "ON (CHẠY)" if self.cmd_on_off == 1 else "OFF (DỪNG)"
            self.simulated_events.append({
                "time": time.strftime("%H:%M:%S"),
                "code": 10 if self.cmd_on_off else 11,
                "prio": 5,
                "desc": f"Lệnh Modbus Write (F=16): Đặt ON/OFF = {self.cmd_on_off} ({state_str}), SpeedRpm = {self.cmd_speed_rpm}"
            })

    def set_throttle(self, percent: float):
        """Tương thích thanh trượt %: quy đổi 0..100% sang ON/OFF và SpeedRpm (0..6000 RPM)"""
        pct = max(0.0, min(100.0, float(percent)))
        if pct > 0.5:
            self.cmd_on_off = 1
            self.cmd_speed_rpm = int((pct / 100.0) * 6000)
        else:
            self.cmd_on_off = 0
            self.cmd_speed_rpm = 0

    def update_physics(self):
        """Cập nhật mô hình vật lý của động cơ BLDC theo lệnh ON/OFF và SpeedRpm"""
        now = time.time()
        dt = max(0.005, min(0.5, now - self._last_tick))
        self._last_tick = now

        if self.cmd_on_off == 0:
            # Khi OFF = 0: Giữ đúng trạng thái chuẩn như trong ảnh bantin.jpeg khi động cơ dừng
            self.reg_state_act = 0
            if abs(self._actual_rpm_f) > 5.0:
                # Giảm tốc theo quán tính
                decay = 3500.0 * dt
                if self._actual_rpm_f > 0:
                    self._actual_rpm_f = max(0.0, self._actual_rpm_f - decay)
                else:
                    self._actual_rpm_f = min(0.0, self._actual_rpm_f + decay)
                self.reg_speed_rpm = int(round(self._actual_rpm_f))
                self.reg_dc_bus_volt = 48
                self.reg_d_curr = 4
                self.reg_q_curr = -2
            else:
                self._actual_rpm_f = 0.0
                self.reg_speed_rpm = 0
                self.reg_dc_bus_volt = 0
                self.reg_d_curr = 9
                self.reg_q_curr = -1

            # Nhiệt độ hồi dần về mức nền trong ảnh (30, 24, 26, 26)
            self._motor_temp_f += (30.0 - self._motor_temp_f) * 0.08 * dt
            self._temp_a_f += (24.0 - self._temp_a_f) * 0.08 * dt
            self._temp_b_f += (26.0 - self._temp_b_f) * 0.08 * dt
            self._temp_c_f += (26.0 - self._temp_c_f) * 0.08 * dt
        else:
            # Khi ON = 1: Động cơ hoạt động (StateAct = 1)
            self.reg_state_act = 1
            target = float(self.cmd_speed_rpm)
            accel = 2500.0 * dt
            if self._actual_rpm_f < target:
                self._actual_rpm_f = min(target, self._actual_rpm_f + accel)
            elif self._actual_rpm_f > target:
                self._actual_rpm_f = max(target, self._actual_rpm_f - accel * 1.2)

            jitter = random.choice([-1, 0, 0, 1]) if abs(self._actual_rpm_f) > 0 else 0
            self.reg_speed_rpm = int(round(self._actual_rpm_f)) + jitter

            # Điện áp DC Bus và dòng D/Q theo tải
            load_ratio = abs(self._actual_rpm_f) / 6000.0
            self.reg_dc_bus_volt = max(12, int(round(48.0 - load_ratio * 2.5)))
            self.reg_d_curr = int(round(9 + load_ratio * 6.0 + random.uniform(-0.8, 0.8)))
            q_base = 2.0 + (load_ratio ** 1.4) * 85.0
            if self._actual_rpm_f < 0:
                q_base = -q_base
            elif abs(self._actual_rpm_f) < 1.0:
                q_base = -1.0
            self.reg_q_curr = int(round(q_base + random.uniform(-0.6, 0.6)))

            # Gia nhiệt nhẹ khi chạy tải
            i_total = math.hypot(self.reg_d_curr, self.reg_q_curr)
            self._motor_temp_f += ((30.0 + i_total * 0.35) - self._motor_temp_f) * 0.05 * dt
            self._temp_a_f += ((24.0 + i_total * 0.28) - self._temp_a_f) * 0.06 * dt
            self._temp_b_f += ((26.0 + i_total * 0.29) - self._temp_b_f) * 0.06 * dt
            self._temp_c_f += ((26.0 + i_total * 0.28) - self._temp_c_f) * 0.06 * dt

            # Tích lũy năng lượng
            power_w = self.reg_dc_bus_volt * abs(self.reg_q_curr)
            self.consumed_ah += (abs(self.reg_q_curr) * dt) / 3600.0
            self.consumed_wh += (power_w * dt) / 3600.0

        self.reg_motor_temp = int(round(self._motor_temp_f))
        self.reg_temp_a = int(round(self._temp_a_f))
        self.reg_temp_b = int(round(self._temp_b_f))
        self.reg_temp_c = int(round(self._temp_c_f))

    def get_read_registers_list(self) -> List[int]:
        """Trả về mảng 11 thanh ghi đọc (0..10)"""
        self.update_physics()
        return [
            self.reg_state_act,
            self.reg_speed_rpm,
            self.reg_dc_bus_volt,
            self.reg_d_curr,
            self.reg_q_curr,
            self.reg_fault_h,
            self.reg_fault_l,
            self.reg_motor_temp,
            self.reg_temp_a,
            self.reg_temp_b,
            self.reg_temp_c,
        ]

    def get_write_registers_list(self) -> List[int]:
        """Trả về mảng 2 thanh ghi ghi (0..1)"""
        return [self.cmd_on_off, self.cmd_speed_rpm]

    def handle_raw_modbus(self, req: bytes, slave_id: int = 1) -> Optional[bytes]:
        """Xử lý gói tin Modbus RTU thô trong chế độ mô phỏng để trả về frame phản hồi thực"""
        if len(req) < 8 or not verify_crc16(req):
            return None
        sid, fcode = req[0], req[1]
        if sid != slave_id:
            return None
        if fcode == 0x03:
            start_addr, count = struct.unpack(">HH", req[2:6])
            regs = self.get_read_registers_list()
            out_regs = []
            for i in range(count):
                idx = start_addr + i
                val = regs[idx] if 0 <= idx < len(regs) else 0
                out_regs.append(to_int16(val))
            pdu = bytes([sid, 0x03, (count * 2) & 0xFF]) + b"".join(struct.pack(">h", v) for v in out_regs)
            return append_crc16(pdu)
        elif fcode == 0x10 and len(req) >= 9:
            start_addr, count, byte_cnt = struct.unpack(">HHB", req[2:7])
            if len(req) >= 7 + byte_cnt + 2:
                vals = []
                for i in range(count):
                    v = struct.unpack(">h", req[7 + i * 2: 9 + i * 2])[0]
                    vals.append(v)
                if start_addr == 0 and len(vals) >= 2:
                    self.set_write_registers(vals[0], vals[1])
                elif start_addr == 0 and len(vals) == 1:
                    self.set_write_registers(vals[0], self.cmd_speed_rpm)
                pdu = struct.pack(">BBHH", sid, 0x10, start_addr, count)
                return append_crc16(pdu)
        return None


# =============================================================================
# QUẢN LÝ KẾT NỐI MODBUS RTU & ĐỒNG BỘ GIAO DIỆN
# =============================================================================
class MGMConnection:
    """Quản lý kết nối Serial Modbus RTU (921600-8-N-1) và chế độ Simulator"""
    def __init__(self):
        self.serial_port: Optional[serial.Serial] = None
        self.port_name: str = "COM11"
        self.baud_rate: int = 921600
        self.slave_id: int = 1
        self.scan_rate_ms: int = 500
        self.read_start_addr: int = 0
        self.read_count: int = 11
        self.write_start_addr: int = 0
        self.write_count: int = 2
        self.cyclic_write_enabled: bool = True

        self.is_connected: bool = False
        self.is_simulator: bool = False

        # Bộ đếm thống kê giống Modbus Poll (Tx / Err cho Read F=03 và Write F=16)
        self.read_tx_count: int = 0
        self.read_err_count: int = 0
        self.write_tx_count: int = 0
        self.write_err_count: int = 0

        # Lưu trữ giá trị hiện tại của các thanh ghi
        self.current_read_regs: List[int] = [0, 0, 0, 9, -1, 0, 0, 30, 24, 26, 26]
        self.current_write_regs: List[int] = [0, 0]  # [ON/OFF, SpeedRpm]

        self.last_read_tx_hex: str = ""
        self.last_read_rx_hex: str = ""
        self.last_write_tx_hex: str = ""
        self.last_write_rx_hex: str = ""

        self.simulator = MGMSimulator()
        self.device_id = 10
        self.device_name = "Viettel BLDC Driver (Modbus RTU)"

        self._poll_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._serial_lock = threading.Lock()
        self._pending_write: Optional[Tuple[int, int]] = None

        # Callbacks
        self.on_telemetry_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_log_callback: Optional[Callable[[str, str], None]] = None
        self.on_status_change: Optional[Callable[[bool, str], None]] = None

    def log(self, msg: str, level: str = "INFO"):
        if self.on_log_callback:
            self.on_log_callback(msg, level)
        else:
            logger.info(f"[{level}] {msg}")

    def reset_counters(self):
        """Đặt lại bộ đếm Tx / Err về 0"""
        self.read_tx_count = 0
        self.read_err_count = 0
        self.write_tx_count = 0
        self.write_err_count = 0

    def connect(self, port: str = "COM11", baud: int = 921600, use_simulator: bool = False,
                slave_id: int = 1, scan_rate_ms: int = 500) -> bool:
        """Kết nối tới cổng COM thực (Modbus RTU 8-N-1) hoặc bật Simulator"""
        self.disconnect()
        self.port_name = port
        self.baud_rate = baud
        self.slave_id = max(1, min(247, int(slave_id)))
        self.scan_rate_ms = max(50, min(5000, int(scan_rate_ms)))
        self.is_simulator = use_simulator

        if use_simulator:
            self.is_connected = True
            self.simulator = MGMSimulator(device_id=self.device_id, device_name=self.device_name)
            self.simulator.set_write_registers(self.current_write_regs[0], self.current_write_regs[1])
            self._start_poll_worker()
            self.log(
                f"Đã bật Mô phỏng Modbus RTU (ID={self.slave_id}, F=03 Read 11 regs, F=16 Write 2 regs, SR={self.scan_rate_ms}ms)",
                "SUCCESS"
            )
            if self.on_status_change:
                self.on_status_change(True, f"Simulator Modbus RTU (ID={self.slave_id}, {self.baud_rate}-8-N-1)")
            return True

        try:
            self.log(f"Đang mở cổng {port}: {baud}-8-N-1 (Modbus RTU Slave ID={self.slave_id})...", "INFO")
            self.serial_port = serial.Serial(
                port=port,
                baudrate=baud,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.25,
                write_timeout=0.25
            )
            self.is_connected = True
            self._start_poll_worker()
            self.log(f"Kết nối thành công {port}: {baud}-8-N-1 (ID={self.slave_id}, SR={self.scan_rate_ms}ms)", "SUCCESS")
            if self.on_status_change:
                self.on_status_change(True, f"{port}: {baud}-8-N-1 (ID={self.slave_id})")
            return True
        except Exception as e:
            self.log(f"Lỗi mở cổng {port} ({baud}-8-N-1): {e}", "ERROR")
            self.disconnect()
            return False

    def disconnect(self):
        """Ngắt kết nối an toàn"""
        self._stop_event.set()
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=1.0)
        self._poll_thread = None
        self._stop_event.clear()

        with self._serial_lock:
            if self.serial_port and self.serial_port.is_open:
                try:
                    self.serial_port.close()
                except Exception:
                    pass
            self.serial_port = None

        self.is_connected = False
        self.is_simulator = False
        if self.on_status_change:
            self.on_status_change(False, "Chưa kết nối (Disconnected)")

    def write_control_command(self, on_off: int, speed_rpm: int, immediate: bool = True) -> bool:
        """
        Ghi bản tin điều khiển Modbus Write (F=16):
        - Reg 0: ON/OFF (0 hoặc 1)
        - Reg 1: SpeedRpm (int16)
        """
        on_val = 1 if int(on_off) != 0 else 0
        rpm_val = to_int16(speed_rpm)
        self.current_write_regs = [on_val, rpm_val]

        if immediate and self.is_connected:
            self._pending_write = (on_val, rpm_val)
            self.log(f"Lệnh điều khiển F=16: ON/OFF = {on_val}, SpeedRpm = {rpm_val} RPM", "INFO")
            return True
        return False

    def _start_poll_worker(self):
        self._stop_event.clear()
        self._poll_thread = threading.Thread(target=self._modbus_poll_loop, daemon=True)
        self._poll_thread.start()

    def _modbus_poll_loop(self):
        """Vòng lặp quét định kỳ theo Scan Rate (SR = 500ms mặc định)"""
        while not self._stop_event.is_set():
            cycle_start = time.time()
            try:
                # 1. Nếu có lệnh ghi tức thời hoặc chế độ Cyclic Write (F=16) đang bật
                if self._pending_write is not None:
                    on_v, rpm_v = self._pending_write
                    self._pending_write = None
                    self._execute_fc16_write(on_v, rpm_v)
                elif self.cyclic_write_enabled:
                    self._execute_fc16_write(self.current_write_regs[0], self.current_write_regs[1])

                # 2. Thực hiện đọc 11 thanh ghi bằng Function 03 (Read Holding Registers)
                self._execute_fc03_read()

                # 3. Đóng gói snapshot gửi lên GUI
                snapshot = self._build_snapshot()
                if self.on_telemetry_callback:
                    self.on_telemetry_callback(snapshot)

            except Exception as e:
                logger.error(f"Lỗi trong chu kỳ quét Modbus: {e}")

            # Ngủ đúng theo Scan Rate (SR), nhưng kiểm tra nhanh nếu có lệnh ghi tức thời
            sr_sec = max(0.05, self.scan_rate_ms / 1000.0)
            while (time.time() - cycle_start) < sr_sec and not self._stop_event.is_set():
                if self._pending_write is not None:
                    break
                time.sleep(0.02)

    def _execute_fc03_read(self) -> bool:
        """Gửi yêu cầu F=03 đọc 11 thanh ghi và nhận phản hồi"""
        req = build_fc03_request(self.slave_id, self.read_start_addr, self.read_count)
        self.read_tx_count += 1
        self.last_read_tx_hex = req.hex(" ").upper()

        if self.is_simulator:
            resp = self.simulator.handle_raw_modbus(req, slave_id=self.slave_id)
            if resp:
                self.last_read_rx_hex = resp.hex(" ").upper()
                regs = parse_fc03_response(resp, self.slave_id, self.read_count)
                if regs is not None:
                    self.current_read_regs = regs
                    return True
            self.read_err_count += 1
            return False

        with self._serial_lock:
            if not self.serial_port or not self.serial_port.is_open:
                self.read_err_count += 1
                return False
            try:
                self.serial_port.reset_input_buffer()
                self.serial_port.write(req)
                expected_len = 5 + self.read_count * 2
                resp = self.serial_port.read(expected_len)
                if resp:
                    self.last_read_rx_hex = resp.hex(" ").upper()
                regs = parse_fc03_response(resp, self.slave_id, self.read_count)
                if regs is not None:
                    self.current_read_regs = regs
                    return True
                else:
                    self.read_err_count += 1
                    return False
            except Exception:
                self.read_err_count += 1
                return False

    def _execute_fc16_write(self, on_off: int, speed_rpm: int) -> bool:
        """Gửi yêu cầu F=16 (0x10) ghi 2 thanh ghi [ON/OFF, SpeedRpm]"""
        req = build_fc16_request(self.slave_id, self.write_start_addr, [on_off, speed_rpm])
        self.write_tx_count += 1
        self.last_write_tx_hex = req.hex(" ").upper()

        if self.is_simulator:
            resp = self.simulator.handle_raw_modbus(req, slave_id=self.slave_id)
            if resp:
                self.last_write_rx_hex = resp.hex(" ").upper()
                if parse_fc16_response(resp, self.slave_id, self.write_start_addr, 2):
                    return True
            self.write_err_count += 1
            return False

        with self._serial_lock:
            if not self.serial_port or not self.serial_port.is_open:
                self.write_err_count += 1
                return False
            try:
                self.serial_port.reset_input_buffer()
                self.serial_port.write(req)
                resp = self.serial_port.read(8)
                if resp:
                    self.last_write_rx_hex = resp.hex(" ").upper()
                if parse_fc16_response(resp, self.slave_id, self.write_start_addr, 2):
                    return True
                else:
                    self.write_err_count += 1
                    return False
            except Exception:
                self.write_err_count += 1
                return False

    def _build_snapshot(self) -> Dict[str, Any]:
        """Tổng hợp dữ liệu từ 11 thanh ghi Read và 2 thanh ghi Write"""
        r = self.current_read_regs
        while len(r) < 11:
            r.append(0)

        state_act = r[0]
        speed_rpm = r[1]
        dc_bus_volt = r[2]
        d_curr = r[3]
        q_curr = r[4]
        fault_h = r[5]
        fault_l = r[6]
        motor_temp = r[7]
        temp_a = r[8]
        temp_b = r[9]
        temp_c = r[10]

        max_phase_temp = max(temp_a, temp_b, temp_c)
        i_total = round(math.hypot(d_curr, q_curr), 2)
        power_w = round(dc_bus_volt * abs(q_curr), 1)
        fault_code_32 = ((fault_h & 0xFFFF) << 16) | (fault_l & 0xFFFF)

        return {
            "time_ms": int(time.time() * 1000) % 1000000,
            # 11 thanh ghi chuẩn trong bantin.jpeg
            "StateAct": state_act,
            "SpeedRpm": speed_rpm,
            "DcBusVolt": dc_bus_volt,
            "D_Curr": d_curr,
            "Q_Curr": q_curr,
            "Fault_H": fault_h,
            "Fault_L": fault_l,
            "MotorTemp": motor_temp,
            "TempA": temp_a,
            "TempB": temp_b,
            "TempC": temp_c,
            "read_regs": list(r[:11]),
            # 2 thanh ghi ghi trong bantin.jpeg
            "cmd_on_off": self.current_write_regs[0],
            "cmd_speed_rpm": self.current_write_regs[1],
            "write_regs": list(self.current_write_regs[:2]),
            # Thống kê Modbus Poll
            "read_tx": self.read_tx_count,
            "read_err": self.read_err_count,
            "write_tx": self.write_tx_count,
            "write_err": self.write_err_count,
            "slave_id": self.slave_id,
            "scan_rate_ms": self.scan_rate_ms,
            "last_read_tx_hex": self.last_read_tx_hex,
            "last_read_rx_hex": self.last_read_rx_hex,
            "last_write_tx_hex": self.last_write_tx_hex,
            "last_write_rx_hex": self.last_write_rx_hex,
            # Các trường tương thích với Dashboard & Đồ thị
            "voltage": float(dc_bus_volt),
            "current": float(q_curr),
            "current_total": i_total,
            "rpm": float(speed_rpm),
            "power": power_w,
            "esc_temp": float(max_phase_temp),
            "motor_temp": float(motor_temp),
            "throttle": 100.0 if self.current_write_regs[0] else 0.0,
            "consumed_ah": round(self.simulator.consumed_ah, 3),
            "consumed_wh": round(self.simulator.consumed_wh, 1),
            "fault_code_32": fault_code_32,
            "flag_low_voltage": False,
            "flag_overtemp": (motor_temp > 85 or max_phase_temp > 85),
        }

    def send_raw_frame(self, raw_bytes: bytes) -> Optional[bytes]:
        """Gửi chuỗi byte thô từ tab Terminal và nhận phản hồi"""
        if self.is_simulator:
            resp = self.simulator.handle_raw_modbus(raw_bytes, slave_id=self.slave_id)
            if resp:
                return resp
            return append_crc16(bytes([self.slave_id, 0x03, 0x02, 0x00, 0x00]))
        with self._serial_lock:
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.reset_input_buffer()
                self.serial_port.write(raw_bytes)
                time.sleep(0.06)
                if self.serial_port.in_waiting > 0:
                    return self.serial_port.read(self.serial_port.in_waiting)
        return None

    def read_all_parameters(self) -> Dict[int, Any]:
        """Đọc thông số cấu hình"""
        time.sleep(0.2)
        return dict(self.simulator.stored_params)

    def write_parameter(self, param_id: int, value: Any) -> bool:
        self.simulator.stored_params[param_id] = value
        return True

    def write_all_parameters(self, params_dict: Dict[int, Any]) -> bool:
        for pid, val in params_dict.items():
            self.write_parameter(pid, val)
        self.log(f"Đã lưu {len(params_dict)} tham số cấu hình.", "SUCCESS")
        return True

    def get_event_log(self) -> List[Dict[str, Any]]:
        return list(self.simulator.simulated_events)

    def set_throttle(self, percent: float):
        """Điều khiển nhanh từ thanh trượt"""
        pct = max(0.0, min(100.0, float(percent)))
        on_val = 1 if pct > 0.5 else 0
        rpm_val = int((pct / 100.0) * 6000) if on_val else 0
        self.write_control_command(on_val, rpm_val, immediate=True)
