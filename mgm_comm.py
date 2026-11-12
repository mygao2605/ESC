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
# BẢNG ĐẶC TẢ THANH GHI MODBUS MODULE POWER (SLAVE ID 01, BAUDRATE 921600)
# =============================================================================
POWER_READ_REGISTERS = [
    {"index": 0,  "name": "Charge_BatVolt (mV)",       "unit": "mV",   "scale": 0.001, "scale_unit": "V",  "desc": "Điện áp Pin sạc"},
    {"index": 1,  "name": "Charge_BatChargeCurr (mA)", "unit": "mA",   "scale": 0.001, "scale_unit": "A",  "desc": "Dòng điện sạc Pin"},
    {"index": 2,  "name": "Charge_InpVolt (mV)",       "unit": "mV",   "scale": 0.001, "scale_unit": "V",  "desc": "Điện áp ngõ vào sạc"},
    {"index": 3,  "name": "Charge_InpCurr",            "unit": "mA",   "scale": 0.001, "scale_unit": "A",  "desc": "Dòng điện ngõ vào sạc"},
    {"index": 4,  "name": "Buck_12V_1_Vout_1 (mV)",    "unit": "mV",   "scale": 0.001, "scale_unit": "V",  "desc": "Buck 12V_1 Áp ra 1"},
    {"index": 5,  "name": "Buck_12V_1_Vout_2 (mV)",    "unit": "mV",   "scale": 0.001, "scale_unit": "V",  "desc": "Buck 12V_1 Áp ra 2"},
    {"index": 6,  "name": "Buck_12V_1_Iout_1 (mA)",    "unit": "mA",   "scale": 0.001, "scale_unit": "A",  "desc": "Buck 12V_1 Dòng ra 1"},
    {"index": 7,  "name": "Buck_12V_1_Iout_2 (mA)",    "unit": "mA",   "scale": 0.001, "scale_unit": "A",  "desc": "Buck 12V_1 Dòng ra 2"},
    {"index": 8,  "name": "Buck_12V_1_Temp_1 (degC)",  "unit": "°C",   "scale": 1.0,   "scale_unit": "°C", "desc": "Buck 12V_1 Nhiệt độ 1"},
    {"index": 9,  "name": "Buck_12V_1_Temp_2 (degC)",  "unit": "°C",   "scale": 1.0,   "scale_unit": "°C", "desc": "Buck 12V_1 Nhiệt độ 2"},
    {"index": 10, "name": "Buck_12V_2_Vout_1 (mV)",    "unit": "mV",   "scale": 0.001, "scale_unit": "V",  "desc": "Buck 12V_2 Áp ra 1"},
    {"index": 11, "name": "Buck_12V_2_Vout_2 (mV)",    "unit": "mV",   "scale": 0.001, "scale_unit": "V",  "desc": "Buck 12V_2 Áp ra 2"},
    {"index": 12, "name": "Buck_12V_2_Iout_1 (mA)",    "unit": "mA",   "scale": 0.001, "scale_unit": "A",  "desc": "Buck 12V_2 Dòng ra 1"},
    {"index": 13, "name": "Buck_12V_2_Iout_2 (mA)",    "unit": "mA",   "scale": 0.001, "scale_unit": "A",  "desc": "Buck 12V_2 Dòng ra 2"},
    {"index": 14, "name": "Buck_12V_2_Temp_1 (degC)",  "unit": "°C",   "scale": 1.0,   "scale_unit": "°C", "desc": "Buck 12V_2 Nhiệt độ 1"},
    {"index": 15, "name": "Buck_12V_2_Temp_2 (degC)",  "unit": "°C",   "scale": 1.0,   "scale_unit": "°C", "desc": "Buck 12V_2 Nhiệt độ 2"},
    {"index": 16, "name": "Buck_5V_1_Vout_1 (mV)",     "unit": "mV",   "scale": 0.001, "scale_unit": "V",  "desc": "Buck 5V_1 Áp ra 1"},
    {"index": 17, "name": "Buck_5V_1_Vout_2 (mV)",     "unit": "mV",   "scale": 0.001, "scale_unit": "V",  "desc": "Buck 5V_1 Áp ra 2"},
    {"index": 18, "name": "Buck_5V_1_Iout_1 (mA)",     "unit": "mA",   "scale": 0.001, "scale_unit": "A",  "desc": "Buck 5V_1 Dòng ra 1"},
    {"index": 19, "name": "Buck_5V_1_Iout_2 (mA)",     "unit": "mA",   "scale": 0.001, "scale_unit": "A",  "desc": "Buck 5V_1 Dòng ra 2"},
    {"index": 20, "name": "Buck_5V_1_Temp_1 (degC)",   "unit": "°C",   "scale": 1.0,   "scale_unit": "°C", "desc": "Buck 5V_1 Nhiệt độ 1"},
    {"index": 21, "name": "Buck_5V_1_Temp_2 (degC)",   "unit": "°C",   "scale": 1.0,   "scale_unit": "°C", "desc": "Buck 5V_1 Nhiệt độ 2"},
    {"index": 22, "name": "Buck_5V_2_Vout_1 (mV)",     "unit": "mV",   "scale": 0.001, "scale_unit": "V",  "desc": "Buck 5V_2 Áp ra 1"},
    {"index": 23, "name": "Buck_5V_2_Vout_2 (mV)",     "unit": "mV",   "scale": 0.001, "scale_unit": "V",  "desc": "Buck 5V_2 Áp ra 2"},
    {"index": 24, "name": "Buck_5V_2_Iout_1 (mA)",     "unit": "mA",   "scale": 0.001, "scale_unit": "A",  "desc": "Buck 5V_2 Dòng ra 1"},
    {"index": 25, "name": "Buck_5V_2_Iout_2 (mA)",     "unit": "mA",   "scale": 0.001, "scale_unit": "A",  "desc": "Buck 5V_2 Dòng ra 2"},
    {"index": 26, "name": "Buck_5V_2_Temp_1 (degC)",   "unit": "°C",   "scale": 1.0,   "scale_unit": "°C", "desc": "Buck 5V_2 Nhiệt độ 1"},
    {"index": 27, "name": "Buck_5V_2_Temp_2 (degC)",   "unit": "°C",   "scale": 1.0,   "scale_unit": "°C", "desc": "Buck 5V_2 Nhiệt độ 2"},
    {"index": 28, "name": "Error code (master)",       "unit": "HEX",  "scale": 1,     "scale_unit": "HEX", "desc": "Mã lỗi Master"},
    {"index": 29, "name": "Vbus x 100",                "unit": "V*100","scale": 0.01,  "scale_unit": "V",  "desc": "Điện áp DC Bus tổng"},
    {"index": 30, "name": "Vout_master x 100",         "unit": "V*100","scale": 0.01,  "scale_unit": "V",  "desc": "Điện áp ra Master"},
    {"index": 31, "name": "Iout_master x 100",         "unit": "A*100","scale": 0.01,  "scale_unit": "A",  "desc": "Dòng điện ra Master"},
    {"index": 32, "name": "Vout_slave x 100",          "unit": "V*100","scale": 0.01,  "scale_unit": "V",  "desc": "Điện áp ra Slave"},
    {"index": 33, "name": "I_out_slave x 100",         "unit": "A*100","scale": 0.01,  "scale_unit": "A",  "desc": "Dòng điện ra Slave"},
    {"index": 34, "name": "Error code (slave)",        "unit": "HEX",  "scale": 1,     "scale_unit": "HEX", "desc": "Mã lỗi Slave"},
    {"index": 35, "name": "Fanspeed (slave)",          "unit": "RPM",  "scale": 1,     "scale_unit": "RPM", "desc": "Tốc độ quạt Slave"},
]

POWER_WRITE_REGISTERS = [
    {"index": 0, "name": "State",        "unit": "0/1", "desc": "Trạng thái Bật/Tắt nguồn (0: TẮT, 1: BẬT)"},
    {"index": 1, "name": "Protect Time", "unit": "ms",  "desc": "Thời gian bảo vệ ngắt"},
    {"index": 2, "name": "RampMax",      "unit": "",    "desc": "Giá trị đặt Iin"},
    {"index": 3, "name": "RampDec",      "unit": "",    "desc": "Giá trị bù dốc"},
    {"index": 4, "name": "V_in(mV)",     "unit": "mV",  "desc": "V_in đo"},
    {"index": 5, "name": "V_out(mV)",    "unit": "mV",  "desc": "V_out đo"},
    {"index": 6, "name": "I_out(mV)",    "unit": "mV",  "desc": "I_out đo"},
    {"index": 7, "name": "ErrorCode",    "unit": "HEX", "desc": "Mã lỗi điều khiển"},
    {"index": 8, "name": "FanSpeed",     "unit": "RPM", "desc": "Tốc độ quạt làm mát"},
    {"index": 9, "name": "DeadTime",     "unit": "ns",  "desc": "Thời gian chết MOSFET"},
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
    """Giải mã khung phản hồi Function 03 (hoặc Function 04) thành danh sách các thanh ghi int16 có dấu"""
    expected_len = 5 + expected_count * 2
    if len(frame) < expected_len:
        return None
    frame = frame[:expected_len]
    if not verify_crc16(frame):
        return None
    slave_id, func_code, byte_count = frame[0], frame[1], frame[2]
    if slave_id != expected_slave or func_code not in (0x03, 0x04) or byte_count != expected_count * 2:
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

        # Thông số BMU (Battery Management Unit - 16S LiPo/Li-Ion Pack)
        self.bmu_cell_count = 16
        self.bmu_cells = [round(3.820 + ((i * 7) % 5) * 0.004 - 0.008, 3) for i in range(16)]
        self.bmu_soc = 86.5   # %
        self.bmu_soh = 99.0   # %
        self.bmu_balancing_active = True
        self.bmu_balancing_cells = [2, 7, 11]
        self.bmu_temps = [28.4, 29.1, 28.7, 29.5]
        self.bmu_board_temp = 31.2
        self.bmu_cycle_count = 42
        self.bmu_ov_limit = 4.25
        self.bmu_uv_limit = 3.00
        self.bmu_ot_limit = 65.0
        self.bmu_max_discharge_a = 220.0

        # Thông số Power / PDU (Power Distribution Unit)
        self.pwr_main_contactor = 1     # 1: CLOSED, 0: OPEN
        self.pwr_precharge_done = 1     # 1: READY / DONE, 0: OFF / CHARGING
        self.pwr_estop_tripped = 0      # 0: NORMAL, 1: TRIPPED
        self.pwr_rail_28v_en = True
        self.pwr_rail_28v_v = 28.08
        self.pwr_rail_28v_i = 2.45
        self.pwr_rail_12v_en = True
        self.pwr_rail_12v_v = 12.04
        self.pwr_rail_12v_i = 3.12
        self.pwr_rail_5v_en = True
        self.pwr_rail_5v_v = 5.18
        self.pwr_rail_5v_i = 1.65
        self.pwr_insulation_mohm = 14.8
        self.pwr_efficiency = 96.5

        # 10 Thanh ghi điều khiển Module Power (Address 0..9)
        # 0: State (0: OFF, 1: ON), 1: Protect Time, 2: RampMax, 3: RampDec, 4: V_in(mV), 5: V_out(mV), 6: I_out(mV), 7: ErrorCode, 8: FanSpeed, 9: DeadTime
        self.pwr_ctrl_regs: List[int] = [1, 100, 50, 50, 48000, 48000, 20000, 0, 2400, 150]

        # 36 Thanh ghi giám sát Module Power (Address 0..35)
        self.pwr_read_regs: List[int] = [0] * 36

        # 4 Thanh ghi ghi Bộ điều khiển MLD (F=16: Set_Position, State, Sel_test, Period)
        self.mld_set_position: int = 0
        self.mld_state: int = 0
        self.mld_sel_test: int = 0
        self.mld_period_ms: int = 500

        # 7 Thanh ghi đọc Bộ điều khiển MLD (F=03: State, Position, Vdc_bus, Error_code, Set_Position, Speed, Hall_Value)
        self.mld_read_state: int = 0
        self.mld_read_position: int = 0
        self.mld_read_vdc_bus: int = 48
        self.mld_read_error_code: int = 0
        self.mld_read_set_pos: int = 0
        self.mld_read_speed: int = 0
        self.mld_read_hall: int = 1
        self._mld_pos_f: float = 0.0
        self._mld_speed_f: float = 0.0
        self._mld_test_timer: float = 0.0

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

            # Dòng tổng hợp khi dừng/không tải
            i_total = math.hypot(self.reg_d_curr, self.reg_q_curr)

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

        # Cập nhật 36 thanh ghi Module Power theo thanh ghi State (Address 0: 1 or 0)
        pwr_state = self.pwr_ctrl_regs[0]
        if pwr_state == 1:
            bat_v = 48250 + random.randint(-40, 40)
            chg_i = 1500 + random.randint(-15, 15)
            inp_v = 54000 + random.randint(-30, 30)
            inp_i = 1850 + random.randint(-10, 10)
            # Buck 12V_1 (4..9)
            b12_1_v1 = 12050 + random.randint(-10, 10)
            b12_1_v2 = 12040 + random.randint(-10, 10)
            b12_1_i1 = 2450 + random.randint(-20, 20)
            b12_1_i2 = 1850 + random.randint(-15, 15)
            b12_1_t1 = 32 + random.randint(0, 1)
            b12_1_t2 = 33 + random.randint(0, 1)
            # Buck 12V_2 (10..15)
            b12_2_v1 = 12030 + random.randint(-10, 10)
            b12_2_v2 = 12020 + random.randint(-10, 10)
            b12_2_i1 = 1950 + random.randint(-20, 20)
            b12_2_i2 = 1750 + random.randint(-15, 15)
            b12_2_t1 = 31 + random.randint(0, 1)
            b12_2_t2 = 32 + random.randint(0, 1)
            # Buck 5V_1 (16..21)
            b5_1_v1 = 5180 + random.randint(-5, 5)
            b5_1_v2 = 5175 + random.randint(-5, 5)
            b5_1_i1 = 1650 + random.randint(-15, 15)
            b5_1_i2 = 1200 + random.randint(-10, 10)
            b5_1_t1 = 29
            b5_1_t2 = 30
            # Buck 5V_2 (22..27)
            b5_2_v1 = 5190 + random.randint(-5, 5)
            b5_2_v2 = 5185 + random.randint(-5, 5)
            b5_2_i1 = 1450 + random.randint(-15, 15)
            b5_2_i2 = 1100 + random.randint(-10, 10)
            b5_2_t1 = 28
            b5_2_t2 = 29
            # Master/Slave (28..35)
            err_m = 0
            vbus_100 = 4800 + random.randint(-5, 5)
            vout_m_100 = 4790 + random.randint(-5, 5)
            iout_base = 1.5 + (i_total * 0.95 if self.cmd_on_off == 1 else 0.0)
            iout_m_100 = int(round(iout_base * 100))
            vout_s_100 = 4785 + random.randint(-5, 5)
            iout_s_100 = int(round((iout_base * 0.9) * 100))
            err_s = 0
            fan_s = self.pwr_ctrl_regs[8] if self.pwr_ctrl_regs[8] > 0 else 2400

            # Cập nhật 10 thanh ghi Phase-Shift trong mô phỏng khi State = 1
            self.pwr_ctrl_regs[1] = 5000
            self.pwr_ctrl_regs[2] = 100
            self.pwr_ctrl_regs[3] = 100
            self.pwr_ctrl_regs[4] = 48000 + random.randint(-30, 30)
            self.pwr_ctrl_regs[5] = 47900 + random.randint(-30, 30)
            self.pwr_ctrl_regs[6] = 15200 + random.randint(-50, 50)
            self.pwr_ctrl_regs[7] = 0
            self.pwr_ctrl_regs[8] = 2400 + random.randint(-15, 15)
            self.pwr_ctrl_regs[9] = 150
        else:
            bat_v = 48000
            chg_i = 0
            inp_v = 0
            inp_i = 0
            b12_1_v1, b12_1_v2, b12_1_i1, b12_1_i2, b12_1_t1, b12_1_t2 = 0, 0, 0, 0, 26, 26
            b12_2_v1, b12_2_v2, b12_2_i1, b12_2_i2, b12_2_t1, b12_2_t2 = 0, 0, 0, 0, 26, 26
            b5_1_v1, b5_1_v2, b5_1_i1, b5_1_i2, b5_1_t1, b5_1_t2 = 0, 0, 0, 0, 25, 25
            b5_2_v1, b5_2_v2, b5_2_i1, b5_2_i2, b5_2_t1, b5_2_t2 = 0, 0, 0, 0, 25, 25
            err_m = 0
            vbus_100 = 0
            vout_m_100 = 0
            iout_m_100 = 0
            vout_s_100 = 0
            iout_s_100 = 0
            err_s = 0
            fan_s = 0

            # Cập nhật 10 thanh ghi Phase-Shift trong mô phỏng khi State = 0
            self.pwr_ctrl_regs[1] = 5000
            self.pwr_ctrl_regs[2] = 100
            self.pwr_ctrl_regs[3] = 100
            self.pwr_ctrl_regs[4] = 48000
            self.pwr_ctrl_regs[5] = 0
            self.pwr_ctrl_regs[6] = 0
            self.pwr_ctrl_regs[7] = 0
            self.pwr_ctrl_regs[8] = 0
            self.pwr_ctrl_regs[9] = 150

        self.pwr_read_regs = [
            bat_v, chg_i, inp_v, inp_i,
            b12_1_v1, b12_1_v2, b12_1_i1, b12_1_i2, b12_1_t1, b12_1_t2,
            b12_2_v1, b12_2_v2, b12_2_i1, b12_2_i2, b12_2_t1, b12_2_t2,
            b5_1_v1, b5_1_v2, b5_1_i1, b5_1_i2, b5_1_t1, b5_1_t2,
            b5_2_v1, b5_2_v2, b5_2_i1, b5_2_i2, b5_2_t1, b5_2_t2,
            err_m, vbus_100, vout_m_100, iout_m_100, vout_s_100, iout_s_100, err_s, fan_s
        ]

        # Mô phỏng Bộ điều khiển MLD (7 thanh ghi đọc, 4 thanh ghi ghi)
        self._mld_test_timer += dt
        target_pos = float(max(-1700, min(1700, self.mld_set_position)))
        if self.mld_state == 1:
            if self.mld_sel_test == 1:
                step_period = max(0.1, self.mld_period_ms / 1000.0)
                target_pos = 1000.0 if (int(self._mld_test_timer / step_period) % 2 == 1) else -1000.0

            pos_diff = target_pos - self._mld_pos_f
            pos_speed = max(-1500.0, min(1500.0, pos_diff * 8.0))
            self._mld_pos_f += pos_speed * dt
            self.mld_read_state = 1
            self.mld_read_position = int(round(self._mld_pos_f))
            self.mld_read_speed = int(round(pos_speed))
            self.mld_read_vdc_bus = 48 + random.randint(-1, 1)
            self.mld_read_error_code = 0
            self.mld_read_set_pos = int(round(target_pos))
            self.mld_read_hall = ((int(abs(self._mld_pos_f) / 100) % 6) + 1)
        else:
            self.mld_read_state = 0
            self.mld_read_speed = 0
            self.mld_read_vdc_bus = 48
            self.mld_read_error_code = 0
            self.mld_read_set_pos = int(target_pos)
            self.mld_read_position = int(round(self._mld_pos_f))

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
            self.update_physics()
            if count == 7:
                regs = [
                    self.mld_read_state,
                    self.mld_read_position,
                    self.mld_read_vdc_bus,
                    self.mld_read_error_code,
                    self.mld_read_set_pos,
                    self.mld_read_speed,
                    self.mld_read_hall
                ]
            elif count >= 30:
                regs = self.pwr_read_regs
            elif count == 10:
                regs = self.pwr_ctrl_regs
            else:
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
                if count == 4 and start_addr == 0:
                    self.mld_set_position = vals[0]
                    self.mld_state = vals[1]
                    self.mld_sel_test = vals[2]
                    self.mld_period_ms = vals[3]
                elif start_addr == 0 and len(vals) >= 2:
                    self.set_write_registers(vals[0], vals[1])
                elif start_addr == 0 and len(vals) == 1:
                    self.set_write_registers(vals[0], self.cmd_speed_rpm)
                # Cập nhật các thanh ghi Power điều khiển
                for i, v in enumerate(vals):
                    p_idx = start_addr + i
                    if 0 <= p_idx < len(self.pwr_ctrl_regs):
                        self.pwr_ctrl_regs[p_idx] = v
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

        # Tab đang kích hoạt: "ESC", "BMU", "POWER", "MLD"
        self.active_tab: str = "ESC"
        self.hardware_pwr_read_regs: List[int] = [0] * 36
        self.hardware_pwr_ctrl_regs: List[int] = [0] * 10
        self.hardware_mld_read_regs: List[int] = [0] * 7
        self.hardware_mld_write_regs: List[int] = [0, 0, 0, 500]

        self._poll_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._serial_lock = threading.Lock()
        self._pending_write: Optional[Tuple[int, int]] = None
        self._pending_power_write: Optional[Tuple[int, List[int]]] = None
        self._pending_mld_write: Optional[List[int]] = None
        self.mld_cyclic_write_enabled: bool = False

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

    def set_active_tab(self, tab: str):
        """Chuyển đổi cấu hình đọc Modbus theo tab đang xem (ESC, BMU, POWER hoặc MLD)"""
        tab_upper = tab.upper()
        if "MLD" in tab_upper:
            self.active_tab = "MLD"
            self.read_count = 7
            self.read_start_addr = 0
            self.write_count = 4
            self.write_start_addr = 0
            self.log("Đã chuyển cấu hình Modbus sang Module MLD (Read 7 Regs, Write 4 Regs)", "INFO")
        elif "POWER" in tab_upper:
            self.active_tab = "POWER"
            # Mặc định đọc 10 thanh ghi Phase-Shift (0..9) theo yêu cầu, hoặc 36 thanh ghi
            if not hasattr(self, 'power_read_count') or self.power_read_count not in (10, 36):
                self.power_read_count = 10
            self.read_count = self.power_read_count
            self.read_start_addr = 0
            self.write_count = 1
            self.write_start_addr = 0
            self.log(f"Đã chuyển cấu hình Modbus sang Module POWER (Read {self.read_count} Regs, Set State Addr 0)", "INFO")
        elif "BMU" in tab_upper:
            self.active_tab = "BMU"
            self.read_count = 11
            self.read_start_addr = 0
            self.write_count = 2
            self.write_start_addr = 0
            self.log("Đã chuyển cấu hình Modbus sang Module BMU (Read 11 Regs)", "INFO")
        else:
            self.active_tab = "ESC"
            self.read_count = 11
            self.read_start_addr = 0
            self.write_count = 2
            self.write_start_addr = 0
            self.log("Đã chuyển cấu hình Modbus sang Module ESC (Read 11 Regs, Write 2 Regs)", "INFO")

    def set_power_read_count(self, count: int):
        """Thay đổi số lượng thanh ghi đọc cho module Power (10 thanh ghi Phase-Shift hoặc 36 thanh ghi Nguồn)"""
        self.power_read_count = 10 if count <= 10 else 36
        if self.active_tab == "POWER":
            self.read_count = self.power_read_count
            self.read_start_addr = 0
            self.log(f"POWER: Đã chuyển sang chế độ đọc {self.read_count} thanh ghi từ Addr #0", "INFO")

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

    def write_mld_command(self, set_pos: int, state: int, sel_test: int, period_ms: int, immediate: bool = True) -> bool:
        """Ghi 4 thanh ghi điều khiển MLD qua Modbus Function 16"""
        pos_val = max(-1700, min(1700, int(set_pos)))
        vals = [to_int16(pos_val), 1 if int(state) != 0 else 0, 1 if int(sel_test) != 0 else 0, max(100, min(2000, int(period_ms)))]
        self.hardware_mld_write_regs = list(vals)
        if immediate and self.is_connected:
            self._pending_mld_write = vals
            self.log(f"MLD: Lệnh ghi F=16: Set_Pos={vals[0]}mm, State={vals[1]}, Sel_test={vals[2]}, Period={vals[3]}ms", "INFO")
            return True
        return False

    def set_mld_cyclic_write(self, enabled: bool):
        """Bật/tắt chế độ gửi chu kỳ cho MLD (F=16)"""
        self.mld_cyclic_write_enabled = enabled
        self.log(f"MLD: {'BẬT' if enabled else 'TẮT'} chế độ Ghi chu kỳ (Cyclic Write F=16)", "INFO")

    def _execute_mld_fc16_write(self, vals: List[int]) -> bool:
        """Thực thi ghi 4 thanh ghi MLD bằng Function 16"""
        req = build_fc16_request(self.slave_id, 0, vals)
        self.write_tx_count += 1
        self.last_write_tx_hex = req.hex(" ").upper()

        if self.is_simulator:
            resp = self.simulator.handle_raw_modbus(req, slave_id=self.slave_id)
            if resp:
                self.last_write_rx_hex = resp.hex(" ").upper()
                if parse_fc16_response(resp, self.slave_id, 0, len(vals)):
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
                if parse_fc16_response(resp, self.slave_id, 0, len(vals)):
                    return True
                else:
                    self.write_err_count += 1
                    return False
            except Exception as e:
                self.write_err_count += 1
                self.log(f"MLD: Lỗi ngoại lệ khi ghi Modbus F=16: {e}", "ERROR")
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
                # 1. Nếu có lệnh ghi MLD (F=16) hoặc chế độ Cyclic Write của MLD đang bật
                if self._pending_mld_write is not None:
                    m_vals = self._pending_mld_write
                    self._pending_mld_write = None
                    self._execute_mld_fc16_write(m_vals)
                elif self.mld_cyclic_write_enabled and self.active_tab == "MLD":
                    self._execute_mld_fc16_write(self.hardware_mld_write_regs)

                # 2. Nếu có lệnh ghi Power tức thời (F=16)
                elif self._pending_power_write is not None:
                    p_addr, p_vals = self._pending_power_write
                    self._pending_power_write = None
                    self._execute_power_fc16_write(p_addr, p_vals)

                # 3. Nếu có lệnh ghi ESC tức thời hoặc chế độ Cyclic Write (F=16) đang bật
                elif self._pending_write is not None:
                    on_v, rpm_v = self._pending_write
                    self._pending_write = None
                    self._execute_fc16_write(on_v, rpm_v)
                elif self.cyclic_write_enabled and self.active_tab == "ESC":
                    self._execute_fc16_write(self.current_write_regs[0], self.current_write_regs[1])

                # 4. Thực hiện đọc thanh ghi bằng Function 03 (Read Holding Registers)
                self._execute_fc03_read()

                # 5. Đóng gói snapshot gửi lên GUI
                snapshot = self._build_snapshot()
                if self.on_telemetry_callback:
                    self.on_telemetry_callback(snapshot)

            except Exception as e:
                logger.error(f"Lỗi trong chu kỳ quét Modbus: {e}")

            # Ngủ đúng theo Scan Rate (SR), nhưng kiểm tra nhanh nếu có lệnh ghi tức thời
            sr_sec = max(0.05, self.scan_rate_ms / 1000.0)
            while (time.time() - cycle_start) < sr_sec and not self._stop_event.is_set():
                if self._pending_write is not None or self._pending_power_write is not None:
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
                    if self.active_tab == "POWER":
                        if len(regs) == 10:
                            self.hardware_pwr_ctrl_regs = list(regs)
                            self.hardware_pwr_read_regs = list(regs) + [0] * 26
                        elif len(regs) >= 36:
                            self.hardware_pwr_read_regs = list(regs[:36])
                            self.hardware_pwr_ctrl_regs = list(regs[:10])
                        else:
                            self.hardware_pwr_read_regs = list(regs)
                    elif self.active_tab == "MLD":
                        self.hardware_mld_read_regs = list(regs[:7])
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

    def _execute_power_fc16_write(self, addr: int, vals: List[int]) -> bool:
        """Gửi yêu cầu F=16 (0x10) ghi các thanh ghi điều khiển Power Module (an toàn thread-safe)"""
        req = build_fc16_request(self.slave_id, addr, vals)
        self.write_tx_count += 1
        self.last_write_tx_hex = req.hex(" ").upper()

        if self.is_simulator:
            resp = self.simulator.handle_raw_modbus(req, slave_id=self.slave_id)
            if resp:
                self.last_write_rx_hex = resp.hex(" ").upper()
                if parse_fc16_response(resp, self.slave_id, addr, len(vals)):
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
                if parse_fc16_response(resp, self.slave_id, addr, len(vals)):
                    self.log(f"POWER: Gửi thành công Modbus F=16 ghi {len(vals)} thanh ghi từ Addr #{addr}", "SUCCESS")
                    return True
                else:
                    self.write_err_count += 1
                    self.log(f"POWER: Modbus Slave không phản hồi hoặc phản hồi lỗi F=16", "WARNING")
                    return False
            except Exception as e:
                self.write_err_count += 1
                self.log(f"POWER: Lỗi ngoại lệ khi ghi Modbus F=16: {e}", "ERROR")
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

        # Tính toán các chỉ số BMU (Battery Management Unit)
        cells = list(self.simulator.bmu_cells)
        min_v = min(cells)
        max_v = max(cells)
        delta_mv = round((max_v - min_v) * 1000.0, 1)
        min_cell_idx = cells.index(min_v) + 1
        max_cell_idx = cells.index(max_v) + 1
        pack_v = round(sum(cells), 2)
        pack_current = round(i_total + (2.5 if self.simulator.pwr_rail_28v_en else 0) + (1.2 if self.simulator.pwr_rail_12v_en else 0), 2)

        pwr_kw = round((dc_bus_volt * i_total) / 1000.0, 2)
        pwr_kwh = round(self.simulator.consumed_wh / 1000.0, 3)

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
            # Các trường tương thích với Dashboard & Đồ thị ESC
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

            # DỮ LIỆU BMU (BATTERY MANAGEMENT UNIT)
            "bmu_cells": cells,
            "bmu_cell_min": min_v,
            "bmu_cell_max": max_v,
            "bmu_cell_delta_mv": delta_mv,
            "bmu_cell_min_idx": min_cell_idx,
            "bmu_cell_max_idx": max_cell_idx,
            "bmu_pack_voltage": pack_v,
            "bmu_pack_current": pack_current,
            "bmu_soc": round(self.simulator.bmu_soc, 1),
            "bmu_soh": round(self.simulator.bmu_soh, 1),
            "bmu_balancing_active": self.simulator.bmu_balancing_active,
            "bmu_balancing_cells": list(self.simulator.bmu_balancing_cells),
            "bmu_temps": list(self.simulator.bmu_temps),
            "bmu_board_temp": round(self.simulator.bmu_board_temp, 1),
            "bmu_cycle_count": self.simulator.bmu_cycle_count,
            "bmu_ov_limit": self.simulator.bmu_ov_limit,
            "bmu_uv_limit": self.simulator.bmu_uv_limit,
            "bmu_ot_limit": self.simulator.bmu_ot_limit,
            "bmu_max_discharge_a": self.simulator.bmu_max_discharge_a,

            # DỮ LIỆU POWER (POWER DISTRIBUTION UNIT)
            "pwr_main_contactor": self.simulator.pwr_main_contactor,
            "pwr_precharge_done": self.simulator.pwr_precharge_done,
            "pwr_estop_tripped": self.simulator.pwr_estop_tripped,
            "pwr_rail_28v_en": self.simulator.pwr_rail_28v_en,
            "pwr_rail_28v_v": self.simulator.pwr_rail_28v_v,
            "pwr_rail_28v_i": self.simulator.pwr_rail_28v_i,
            "pwr_rail_12v_en": self.simulator.pwr_rail_12v_en,
            "pwr_rail_12v_v": self.simulator.pwr_rail_12v_v,
            "pwr_rail_12v_i": self.simulator.pwr_rail_12v_i,
            "pwr_rail_5v_en": self.simulator.pwr_rail_5v_en,
            "pwr_rail_5v_v": self.simulator.pwr_rail_5v_v,
            "pwr_rail_5v_i": self.simulator.pwr_rail_5v_i,
            "pwr_insulation_mohm": self.simulator.pwr_insulation_mohm,
            "pwr_efficiency": self.simulator.pwr_efficiency,
            "pwr_total_kw": pwr_kw,
            "pwr_total_kwh": pwr_kwh,

            # BẢNG DỮ LIỆU ĐẶC TẢ MODBUS POWER (36 READ REGS + 10 CTRL REGS)
            "pwr_state": self.hardware_pwr_ctrl_regs[0] if not self.is_simulator else self.simulator.pwr_ctrl_regs[0],
            "pwr_ctrl_regs": list(self.hardware_pwr_ctrl_regs) if not self.is_simulator else list(self.simulator.pwr_ctrl_regs),
            "pwr_read_regs": list(self.hardware_pwr_read_regs) if not self.is_simulator else list(self.simulator.pwr_read_regs),

            # BẢNG DỮ LIỆU ĐẶC TẢ BỘ ĐIỀU KHIỂN MLD (7 READ REGS + 4 WRITE REGS)
            "mld_read_regs": list(self.hardware_mld_read_regs) if not self.is_simulator else [
                self.simulator.mld_read_state,
                self.simulator.mld_read_position,
                self.simulator.mld_read_vdc_bus,
                self.simulator.mld_read_error_code,
                self.simulator.mld_read_set_pos,
                self.simulator.mld_read_speed,
                self.simulator.mld_read_hall
            ],
            "mld_write_regs": list(self.hardware_mld_write_regs) if not self.is_simulator else [
                self.simulator.mld_set_position,
                self.simulator.mld_state,
                self.simulator.mld_sel_test,
                self.simulator.mld_period_ms
            ],
            "mld_state": self.simulator.mld_read_state if self.is_simulator else (self.hardware_mld_read_regs[0] if len(self.hardware_mld_read_regs) > 0 else 0),
            "mld_position": self.simulator.mld_read_position if self.is_simulator else (self.hardware_mld_read_regs[1] if len(self.hardware_mld_read_regs) > 1 else 0),
            "mld_vdc_bus": self.simulator.mld_read_vdc_bus if self.is_simulator else (self.hardware_mld_read_regs[2] if len(self.hardware_mld_read_regs) > 2 else 0),
            "mld_error_code": self.simulator.mld_read_error_code if self.is_simulator else (self.hardware_mld_read_regs[3] if len(self.hardware_mld_read_regs) > 3 else 0),
            "mld_set_position": self.simulator.mld_read_set_pos if self.is_simulator else (self.hardware_mld_read_regs[4] if len(self.hardware_mld_read_regs) > 4 else 0),
            "mld_speed": self.simulator.mld_read_speed if self.is_simulator else (self.hardware_mld_read_regs[5] if len(self.hardware_mld_read_regs) > 5 else 0),
            "mld_hall_value": self.simulator.mld_read_hall if self.is_simulator else (self.hardware_mld_read_regs[6] if len(self.hardware_mld_read_regs) > 6 else 0),
        }

    def set_power_state(self, state: int):
        """Đặt trạng thái nguồn Power Module: State = 1 (BẬT) hoặc State = 0 (TẮT)"""
        s = 1 if int(state) != 0 else 0
        self.simulator.pwr_ctrl_regs[0] = s
        state_str = "BẬT (STATE = 1)" if s == 1 else "TẮT (STATE = 0)"
        self.log(f"POWER: Đặt lệnh {state_str} (Modbus F=16 -> Addr 0)", "SUCCESS" if s == 1 else "INFO")
        # Đưa vào hàng đợi ghi Modbus tức thời (Addr 0, Value [s])
        self._pending_power_write = (0, [s])

    def write_power_ctrl_register(self, addr: int, val: int):
        """Ghi một thanh ghi điều khiển Module Power (Address 0..9)"""
        clean_val = int(val)
        if 0 <= addr < len(self.simulator.pwr_ctrl_regs):
            self.simulator.pwr_ctrl_regs[addr] = clean_val
            name = POWER_WRITE_REGISTERS[addr]["name"] if addr < len(POWER_WRITE_REGISTERS) else f"Reg#{addr}"
            self.log(f"POWER: Đặt ghi thanh ghi #{addr} ({name}) = {clean_val}", "INFO")
        self._pending_power_write = (addr, [clean_val])

    def write_power_all_ctrl_registers(self, values: List[int]):
        """Ghi đồng loạt các thanh ghi điều khiển Module Power (F=16)"""
        clean_vals = [int(v) for v in values[:10]]
        for i, v in enumerate(clean_vals):
            if i < len(self.simulator.pwr_ctrl_regs):
                self.simulator.pwr_ctrl_regs[i] = v
        self.log(f"POWER: Đặt ghi {len(clean_vals)} thanh ghi điều khiển xuống Modbus (F=16 Addr 0)", "INFO")
        self._pending_power_write = (0, clean_vals)

    def set_bmu_balancing(self, active: bool):
        """Bật/tắt chế độ cân bằng cell BMU"""
        self.simulator.bmu_balancing_active = bool(active)
        self.log(f"BMU: Đã {'bật' if active else 'tắt'} chế độ cân bằng tự động (Auto Balancing)", "INFO")

    def set_bmu_protection_limits(self, ov: float, uv: float, ot: float, max_cur: float):
        """Cài đặt ngưỡng bảo vệ BMU"""
        self.simulator.bmu_ov_limit = float(ov)
        self.simulator.bmu_uv_limit = float(uv)
        self.simulator.bmu_ot_limit = float(ot)
        self.simulator.bmu_max_discharge_a = float(max_cur)
        self.log(f"BMU: Cập nhật ngưỡng bảo vệ: OV={ov}V, UV={uv}V, OT={ot}°C, MaxI={max_cur}A", "SUCCESS")

    def set_main_contactor(self, closed: bool):
        """Đóng hoặc ngắt Contactor nguồn cao áp chính"""
        self.simulator.pwr_main_contactor = 1 if closed else 0
        state = "ĐÓNG (CLOSED)" if closed else "NGẮT (OPEN)"
        self.log(f"POWER: Contactor chính đã chuyển sang trạng thái: {state}", "INFO")

    def set_estop(self, tripped: bool):
        """Kích hoạt hoặc giải tỏa nút dừng khẩn cấp E-Stop"""
        self.simulator.pwr_estop_tripped = 1 if tripped else 0
        if tripped:
            self.write_control_command(0, 0, immediate=True)
            self.log("POWER: [NGUY CẤP] Nút E-Stop đã KÍCH HOẠT! Động cơ bị ngắt khẩn cấp!", "WARNING")
        else:
            self.log("POWER: E-Stop đã được RESET về trạng thái BÌNH THƯỜNG", "SUCCESS")

    def toggle_power_rail(self, rail_name: str, state: bool):
        """Bật/tắt các nhánh nguồn hạ áp phụ trợ"""
        if rail_name == "28V":
            self.simulator.pwr_rail_28v_en = bool(state)
        elif rail_name == "12V":
            self.simulator.pwr_rail_12v_en = bool(state)
        elif rail_name == "5V":
            self.simulator.pwr_rail_5v_en = bool(state)
        self.log(f"POWER: Nhánh nguồn {rail_name} đã {'BẬT' if state else 'TẮT'}", "INFO")

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
