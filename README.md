# VIETTEL BLDC / ESC CONTROLLER - Modbus RTU Propulsion Suite

Phần mềm điều khiển, giám sát và cấu hình các dòng bộ điều khiển động cơ **BLDC Driver / ESC công nghiệp** do **Viettel Aerospace & Defense** phát triển, tương thích hoàn toàn giao thức chuẩn **Modbus RTU** theo đặc tả bản tin thực tế từ `bantin.jpeg` (Modbus Poll).

---

## 🚀 Đóng gói & Xuất ra file `.exe` độc lập (Standalone Executable)

Phần mềm đã được thiết lập sẵn file cấu hình đóng gói **`Viettel_BLDC_Controller.spec`** và script tự động **`build_exe.bat`**.

Sau khi đóng gói, toàn bộ:
* **Môi trường Python**
* **Tất cả các thư viện** (`customtkinter`, `pyserial`, `matplotlib`, `pillow`,...)
* **Tài nguyên** (Logo Viettel, Icon `.ico`, font chữ, themes đồ họa)

sẽ được nén thành **1 file `.exe` duy nhất** nằm trong thư mục `dist\Viettel_BLDC_Controller.exe`. Bạn có thể mang file này sang bất kỳ máy tính Windows nào để chạy trực tiếp **mà không cần cài đặt Python hay bất kỳ thư viện nào**!

### Các bước xuất file `.exe`:

- **Cách 1 (Nhanh nhất)**: Nhấp đúp chuột vào file:
  ```cmd
  build_exe.bat
  ```
  *(Script sẽ tự động cài `pyinstaller`, các thư viện cần thiết và tiến hành đóng gói trong 1–2 phút).*

- **Cách 2 (Bằng dòng lệnh)**:
  ```bash
  # 1. Cài đặt các thư viện đóng gói
  pip install -r requirements.txt

  # 2. Chạy lệnh đóng gói
  pyinstaller --clean Viettel_BLDC_Controller.spec
  ```

File kết quả sau khi hoàn thành:
```
dist\Viettel_BLDC_Controller.exe
```

---

## 📦 Yêu cầu môi trường & Cài đặt thư viện (Dành cho nhà phát triển)

### 1. Yêu cầu hệ thống:
* **Hệ điều hành**: Windows 10 / 11 (64-bit)
* **Phiên bản Python**: Python 3.8 trở lên (Khuyến nghị Python 3.10 hoặc 3.11)

### 2. Cài đặt các thư viện phụ thuộc:

Mở cửa sổ dòng lệnh (**Command Prompt** hoặc **PowerShell**) tại thư mục dự án và chạy lệnh sau:

```bash
pip install -r requirements.txt
```

Hoặc cài đặt từng thư viện riêng lẻ:

```bash
pip install customtkinter pyserial pillow matplotlib pyinstaller
```

### 3. Chi tiết chức năng các thư viện:
| Tên thư viện | Phiên bản khuyến nghị | Mục đích sử dụng trong phần mềm |
| :--- | :---: | :--- |
| **`customtkinter`** | `>= 5.2.0` | Thiết kế giao diện hiện đại chuẩn Dark Mode công nghiệp, tùy biến theo bộ nhận diện thương hiệu Đỏ Viettel (`#EE0033`). |
| **`pyserial`** | `>= 3.5` | Giao tiếp truyền thông phần cứng qua cổng COM / USB-UART với tốc độ cao (Baudrate 921600 bps, 8-N-1). |
| **`pillow` (PIL)** | `>= 9.5.0` | Nạp và xử lý hình ảnh logo biểu tượng Viettel (`viettel_logo.png` & `viettel_logo.ico`). |
| **`matplotlib`** | `>= 3.7.0` | Vẽ đồ thị sóng telemetry thời gian thực đa kênh (10–20Hz) và phân tích dữ liệu Datalogger BlackBox. |
| **`pyinstaller`** | `>= 5.13.0` | Đóng gói toàn bộ code và thư viện thành file `.exe` duy nhất không cần cài đặt Python. |

---

## 📸 Phân tích bản tin từ ảnh `bantin.jpeg`

Trong ảnh `bantin.jpeg`, hệ thống đang sử dụng công cụ Modbus Poll với thông số cấu hình vật lý:
- **Cổng truyền thông (Serial Port)**: `Port 11` (COM11)
- **Thông số khung truyền**: `921600-8-N-1` (Baudrate 921600 bps, 8 Data bits, No Parity, 1 Stop bit)
- **Địa chỉ Slave ID**: `ID = 1`
- **Tốc độ quét (Scan Rate - SR)**: `500 ms`

Hệ thống phân tách thành 2 bản tin đồng thời:

### 1. Bản tin đọc: `ModbusRead.mbp`
- **Mã hàm**: `F = 03` (Read Holding Registers)
- **Địa chỉ bắt đầu**: `00000`
- **Số lượng thanh ghi**: `11` thanh ghi 16-bit
- **Thống kê truyền thông**: `Tx = 682 : Err = 3 : ID = 1 : F = 03 : SR = 500ms`
- **Danh sách 11 thanh ghi**:
  | Địa chỉ | Tên thanh ghi | Giá trị mặc định | Đơn vị | Ý nghĩa kỹ thuật |
  | :---: | :--- | :---: | :---: | :--- |
  | `0` | **StateAct** | `0` | - | Trạng thái thực tế (0: Dừng/Idle, 1: Chạy/Run, 2: Lỗi/Fault) |
  | `1` | **SpeedRpm** | `0` | RPM | Tốc độ vòng quay thực tế của động cơ |
  | `2` | **DcBusVolt** | `0` | V | Điện áp nguồn DC Bus |
  | `3` | **D_Curr** | `9` | A | Dòng điện trục D (Id - Direct axis current) |
  | `4` | **Q_Curr** | `-1` | A | Dòng điện trục Q (Iq - Quadrature torque current) |
  | `5` | **Fault_H** | `0` | HEX | Thanh ghi mã lỗi Word cao (High word) |
  | `6` | **Fault_L** | `0` | HEX | Thanh ghi mã lỗi Word thấp (Low word) |
  | `7` | **MotorTemp** | `30` | °C | Nhiệt độ cuộn dây động cơ |
  | `8` | **TempA** | `24` | °C | Nhiệt độ cầu công suất Pha A (MOSFET/IGBT) |
  | `9` | **TempB** | `26` | °C | Nhiệt độ cầu công suất Pha B (MOSFET/IGBT) |
  | `10`| **TempC** | `26` | °C | Nhiệt độ cầu công suất Pha C (MOSFET/IGBT) |

### 2. Bản tin ghi: `ModbusWrite.mbp`
- **Mã hàm**: `F = 16` (0x10 - Write Multiple Registers)
- **Địa chỉ bắt đầu**: `00000`
- **Số lượng thanh ghi**: `2` thanh ghi 16-bit
- **Thống kê truyền thông**: `Tx = 406 : Err = 2 : ID = 1 : F = 16 : SR = 500ms`
- **Danh sách 2 thanh ghi điều khiển**:
  | Địa chỉ | Tên thanh ghi | Giá trị mặc định | Đơn vị | Ý nghĩa kỹ thuật |
  | :---: | :--- | :---: | :---: | :--- |
  | `0` | **ON/OFF** | `0` | 0 / 1 | Lệnh bật/tắt động cơ (0: Dừng OFF, 1: Chạy ON) |
  | `1` | **SpeedRpm** | `0` | RPM | Lệnh đặt tốc độ mục tiêu (Target RPM) |

---

## 🎨 Kiến trúc & Giao diện phần mềm Viettel

Phần mềm được thiết kế với chuẩn nhận diện **Viettel Red Theme (`#EE0033`)**, bao gồm 7 phân hệ chính:

1. **📡 Tab Bản tin Modbus (Read/Write)**:
   - Mô phỏng trực quan 2 cửa sổ con song song: `ModbusRead.mbp` (F=03) và `ModbusWrite.mbp` (F=16).
   - Hiển thị đầy đủ số liệu thống kê `Tx`, `Err`, `ID`, `F`, `SR` và dòng dữ liệu HEX trực tiếp kèm mã kiểm tra CRC-16.
   - Tích hợp **Bảng điều khiển động cơ BLDC** trực quan: nút BẬT/TẮT, thanh trượt Target RPM, các nút chọn nhanh tốc độ (500, 1000, 1500, 2000, 3000, 5000 RPM) và công tắc tự động gửi chu kỳ F=16.
2. **📊 Tab Giám sát & Đồ thị thời gian thực (Live)**:
   - 8 khối đồng hồ điện tử số lớn tương ứng 11 thanh ghi: `StateAct`, `SpeedRpm`, `DcBusVolt`, `D_Curr`, `Q_Curr`, `Fault_H/L`, `MotorTemp`, `TempA/B/C`.
   - Đồ thị sóng Matplotlib đa kênh thời gian thực: SpeedRpm/10, DcBusVolt, Id, Iq, Nhiệt độ động cơ và các pha.
   - Ghi dữ liệu thực địa ra file CSV (11 kênh).
3. **⚙️ Tab Cấu hình tham số (Device Settings)**:
   - Đọc/ghi cấu hình, quản lý hàng trăm tham số động cơ, bảo vệ quá dòng, quá áp, nạp/xuất file JSON/INI.
4. **📈 Tab Phân tích Datalogger (BlackBox)**:
   - Đọc dữ liệu lịch sử chuyến bay, tính toán Peak Current, Min Voltage, Max RPM, Max Temperature.
5. **⚠️ Tab Nhật ký sự kiện & Mã lỗi (Events & Diagnostics)**:
   - Tự động giải mã lỗi từ cặp thanh ghi `Fault_H` và `Fault_L`.
6. **ℹ️ Tab Thông tin phần cứng & Firmware**:
   - Quản lý phiên bản phần cứng, Serial Number, nạp Firmware an toàn.
7. **💻 Tab Terminal Modbus HEX**:
   - Gửi lệnh Modbus RTU thô, tích hợp tính và nối mã CRC16 tự động.

---

## 🛠 Khởi chạy ứng dụng trực tiếp từ mã nguồn

- **Khởi chạy từ tệp batch**:
  ```cmd
  run_app.bat
  ```
- **Khởi chạy qua Python**:
  ```bash
  python main.py
  ```
