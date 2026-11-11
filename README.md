# VIETTEL PROPULSION SUITE - ESC / BMU / POWER CONTROLLER

Phần mềm điều khiển, giám sát và cấu hình hệ sinh thái truyền lực công nghệ cao do **Viettel Aerospace & Defense** phát triển, tương thích chuẩn giao thức **Modbus RTU** (Port 11, Baudrate 921600-8-N-1, Slave ID = 1, Scan Rate = 500ms theo đặc tả thực tế từ `bantin.jpeg`).

---

## 🏗️ Kiến trúc Module GUI tách rời (3 Files Độc Lập)

Để thuận tiện cho việc phát triển, bảo trì và chỉnh sửa giao diện mà không ảnh hưởng lẫn nhau, giao diện phần mềm được phân tách thành **3 file GUI riêng biệt** tương ứng với 3 phân hệ cốt lõi:

```
MGM_Viettel/
├── main.py                  # Điểm khởi chạy chính ứng dụng
├── mgm_gui.py               # Cửa sổ chính, Header bar, quản lý kết nối & phân phối dữ liệu
├── gui_esc.py               # [MODULE 1] Quản lý bộ điều tốc ESC & Động cơ BLDC
├── gui_bmu.py               # [MODULE 2] Quản lý hệ thống Pin & Cân bằng Cell (BMU / BMS)
├── gui_power.py             # [MODULE 3] Quản lý phân phối nguồn cao áp, Contactor & E-Stop (PDU)
├── mgm_comm.py              # Lớp truyền thông Modbus RTU & Động học mô phỏng (Physics Engine)
├── mgm_data.py              # Bộ nạp thông số thiết bị và giải mã cơ sở dữ liệu
└── Viettel_BLDC_Controller.spec # Cấu hình đóng gói file .exe độc lập
```

### 1. Module 1: `gui_esc.py` — Quản lý ESC & Động cơ BLDC
* **Tái hiện 2 cửa sổ Modbus Poll từ `bantin.jpeg`**:
  * `ModbusRead.mbp` (F=03, 11 thanh ghi: `StateAct`, `SpeedRpm`, `DcBusVolt`, `D_Curr`, `Q_Curr`, `Fault_H/L`, `MotorTemp`, `TempA/B/C`).
  * `ModbusWrite.mbp` (F=16, 2 thanh ghi: `ON/OFF`, `SpeedRpm`).
* **Bảng điều khiển động cơ trực quan**: Nút Bật `ON=1` / Dừng `OFF=0`, thanh trượt tốc độ 0–6000 RPM, các mức đặt nhanh 500, 1000, 1500, 2000, 3000, 5000 RPM.
* **8 khối đồng hồ điện tử số lớn**: Giám sát dòng điện $I_d, I_q$, điện áp DC Bus, tốc độ RPM, nhiệt độ động cơ và các pha.
* **Đồ thị thời gian thực Matplotlib**: Cập nhật sóng 10–20Hz, hỗ trợ bật/tắt từng kênh đo và xuất log CSV.

### 2. Module 2: `gui_bmu.py` — Quản lý Pin & BMS (Battery Management Unit)
* **Tổng quan Pack pin**: Pack Voltage (V), Pack Current (A), State of Charge (SoC %), State of Health (SoH %), Năng lượng còn lại (Wh), Số chu kỳ sạc (Cycles).
* **Ma trận 16 Cell pin (16S Pack)**: Thanh tiến trình điện áp từng cell, đổi màu theo dải điện áp an toàn, cờ chỉ báo cell đang xả cân bằng (`⚡ BAL`).
* **Thống kê chênh lệch cell**: Cell Max (V), Cell Min (V), Độ lệch $\Delta V$ (mV).
* **Cảm biến nhiệt độ**: 4 cảm biến nhiệt độ phân bố các module cell (T1..T4) + nhiệt độ bo mạch BMS.
* **Cài đặt ngưỡng an toàn BMU**: Quá áp Cell (OV Cutoff), Tụt áp Cell (UV Cutoff), Quá nhiệt (OT Cutoff), Dòng xả tối đa, công tắc Bật/Tắt Cân bằng động (Active Cell Balancing).

### 3. Module 3: `gui_power.py` — Quản lý Nguồn & Phân phối Điện (Power & PDU)
* **Tuyến nguồn cao áp (High-Voltage DC Propulsion Bus)**:
  * Điện áp DC Bus (V), Dòng tải tổng (A), Công suất tức thời (kW), Năng lượng tiêu thụ (kWh), Dung lượng xả (Ah).
* **Điều khiển Contactor chính & Mạch nạp đệm (Pre-charge Relay)**:
  * Đóng Contactor kèm quy trình nạp đệm tự động an toàn tránh phóng tia lửa điện hồ quang.
  * Ngắt Contactor chính.
* **Hệ thống ngắt khẩn cấp E-Stop**:
  * Nút DỪNG KHẨN CẤP lớn màu đỏ nổi bật (ngay lập tức triệt tiêu lệnh điều khiển ga, ngắt động cơ).
  * Nút Reset khẩn cấp đưa hệ thống về trạng thái bình thường.
* **Quản lý 3 nhánh nguồn hạ áp phụ trợ (Auxiliary DC Rails)**:
  * Nhánh 28VDC (Avionics / Flight Controller).
  * Nhánh 12VDC (Payload / Video Link / Radar).
  * Nhánh 5.2VDC (Sensors / Servos / BEC).
* **Đo kiểm an toàn điện**: Điện trở cách điện DC Bus Insulation ($M\Omega$), phát hiện rò điện vỏ (Ground Leakage), Hiệu suất chuyển đổi PDU (%).

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

## 🛠 Khởi chạy ứng dụng trực tiếp từ mã nguồn

- **Khởi chạy từ tệp batch**:
  ```cmd
  run_app.bat
  ```
- **Khởi chạy qua Python**:
  ```bash
  python main.py
  ```
# POWER_ESC
