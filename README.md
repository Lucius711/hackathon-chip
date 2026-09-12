# hackathon-chip-logic — firmware xe thi đấu

> ⚠️ **CẬP NHẬT**: phần cứng thật là **Raspberry Pi** (không phải ESP32), và
> **thí sinh SSH vào chip để tự viết code lái/AI** — ban tổ chức chỉ cần chuẩn
> bị đúng phần "kết nối mạng + gửi log đúng định dạng DB". Kiến trúc đúng cho
> trường hợp này nằm ở **[`pi-daemon/`](pi-daemon/README.md) — đọc từ đó
> trước**. Toàn bộ nội dung bên dưới (`main/`, `test/`, `wokwi/`) là bản làm
> cho ESP32/FreeRTOS trước khi biết rõ yêu cầu, giữ lại làm tài liệu tham
> khảo (phòng khi có đội tự dùng thêm ESP32 làm module phụ), không phải thứ
> cần dùng cho Raspberry Pi.

Logic chạy trên **con chip gắn trên xe** (không phải server). Đây là phần còn thiếu
trong bộ ba `Car/simulator` (mô phỏng UDP, dùng khi chưa có xe thật) → `hackathon-backend`
(quản trị, JWT, RADIUS) → `hackathon-frontend` (dashboard). Thư mục này thay thế
`car_simulator.py` bằng firmware thật, phải **tương thích 100% giao thức** mà
`Car/simulator/protocol.py` và `ingest_server.py` đã định nghĩa, đồng thời **không được
làm sai lệch kết quả cuộc thi**.

## 1. Vì sao chọn C/C++ trên ESP-IDF (FreeRTOS), không phải Python/Node/Arduino thuần

| Yêu cầu thực tế | Vì sao cần | Hệ quả cho lựa chọn ngôn ngữ |
|---|---|---|
| Gửi đúng nhịp **10ms** (100Hz), sai lệch càng nhỏ càng công bằng | `StatsService.runStats()` tính "gói mất" từ `max(seq)-min(seq)+1-count`, và tần suất gói ảnh hưởng trực tiếp tới độ mượt của dashboard live | Cần vòng lặp **thời gian thực xác định** — không có GC dừng bất chợt (loại Python/Node/JVM) làm trôi nhịp gửi |
| `car_timestamp` phải là **giờ tường thực** đã đồng bộ NTP, vì `received_at - car_timestamp` = độ trễ mạng hiển thị cho giám khảo | `init_basic_int.txt` ghi rõ: "hiệu số ÂM nghĩa là đồng hồ xe chưa đồng bộ NTP" | Cần SNTP client chuẩn, chạy sớm trước khi gửi gói đầu tiên |
| Xe xác thực WiFi bằng **WPA2-Enterprise (PEAP/MSCHAPv2)** qua FreeRADIUS đọc thẳng từ bảng `teams` | README backend + báo cáo triển khai RADIUS đã chốt kiến trúc này | ESP-IDF có `esp_eap_client` hỗ trợ PEAP/MSCHAPv2 **có sẵn, native** — không phải tự cài thư viện |
| Xe chạy pin, tài nguyên hạn chế, vẫn phải chạy AI nhận diện làn/vật cản **song song** với việc gửi log đúng giờ | Một tác vụ AI chậm không được phép làm trễ tác vụ gửi UDP | FreeRTOS tách 2 task độc lập, task gửi log có độ ưu tiên cao hơn, không phụ thuộc thời gian suy luận AI |
| Gói tin phải khớp **chính xác từng byte JSON key** với `protocol.py` (`run_id, team_id, sequence_no, car_timestamp, ai_result`) | `protocol.decode()` phía server raise lỗi nếu thiếu field → gói bị đếm vào `parse_errors` và **mất luôn**, không thể sửa sau | cJSON (có sẵn trong ESP-IDF) tạo JSON gọn (`cJSON_PrintUnformatted`) giống hệt `json.dumps(..., separators=(",", ":"))` |

Kết luận: **C (ESP-IDF, target ESP32), FreeRTOS**, không dùng Arduino-core (Arduino
vẫn chạy được EAP nhưng lịch chạy task kém chủ động hơn, khó khống chế jitter <2ms
mà `car_simulator.py` gốc từng đo bằng `late_count_gt2ms`). Nếu đội đã quen Arduino,
kiến trúc/luồng dưới đây vẫn áp dụng được, chỉ thay lớp WiFi/socket bằng API Arduino
tương ứng.

## 2. Cấu trúc

```
main/
  car_config.h / .c        đọc "danh tính" xe (car_id, team_id, WiFi Enterprise, IP server) từ NVS
  wifi_enterprise.h / .c    kết nối WiFi WPA2-Enterprise (PEAP-MSCHAPv2)
  time_sync.h / .c          đồng bộ SNTP — BẮT BUỘC xong trước khi gửi gói đầu tiên
  run_session.h / .c        nhận lệnh "bắt đầu/dừng luot chạy" (run_id) qua console UART
  fairness_guard.h / .c     ép nhịp gửi, số thứ tự gói KHÔNG được lặp/nhảy/giật lùi
  telemetry_protocol.h / .c mã hoá gói UDP đúng schema protocol.py
  telemetry_task.h / .c     task FreeRTOS nhịp 10ms: đọc AI -> đóng gói -> gửi UDP
  ai_perception.h           HỢP ĐỒNG (interface) cho module AI dò làn/vật cản của đội
  ai_perception_stub.c      bản mặc định AN TOÀN (obstacle=true, speed=0) khi chưa cắm AI thật
  main.c                    app_main(): khởi động theo đúng thứ tự ở trên
sdkconfig.defaults          CONFIG_FREERTOS_HZ=1000 (tick 1ms) — bắt buộc để nhịp 10ms chính xác
```

## 3. Vòng đời một lượt chạy (run)

1. Xe cấp nguồn → nạp danh tính từ NVS (`car_config_load`) → kết nối WiFi Enterprise
   bằng đúng `username` khớp với dòng trong bảng `teams` (mật khẩu = mật khẩu gốc dùng
   để sinh `nt_hash`, KHÔNG phải nt_hash — PEAP cần mật khẩu gốc để tính challenge-response).
   Nếu `teams.is_active=false` (bị thu hồi), FreeRADIUS từ chối ngay từ bước này —
   đúng thiết kế "revoke có hiệu lực từ lần xác thực kế tiếp" ghi trong README backend.
2. Đồng bộ SNTP (`time_sync_wait`) — chặn tối đa N giây, log cảnh báo to nếu không xong
   nhưng **vẫn cho phép chạy tiếp** (fail-open, giống triết lý `RunValidator` bên
   `ingest_server.py`): thà gửi log với đồng hồ hơi lệch còn hơn xe đứng im giữa cuộc thi.
   Ban tổ chức nên chạy một NTP server nội bộ trên mạng thi đấu (không phụ thuộc Internet).
3. Trọng tài mở lượt chạy trên trang quản trị (`POST /api/runs`) → có `run_id` → gõ lệnh
   `startrun <run_id>` qua console UART của xe (xem mục 4) → `run_session` kích hoạt.
4. `telemetry_task` bắt đầu vòng lặp 10ms: gọi `ai_perception_read()` (đội tự cắm AI thật
   vào đây), lấy số thứ tự kế tiếp từ `fairness_guard`, đóng gói, gửi UDP tới
   `ingest_server.py`.
5. Khi trọng tài gọi `POST /api/runs/{id}/finish` (hoặc `/void`) trên web, xe **không cần
   biết** — `ingest_server.py` (không dùng `--validate-run`) vẫn nhận gói bình thường,
   log dư sau khi finish chỉ đơn giản không ảnh hưởng điểm vì tính điểm dựa trên
   `started_at`/`ended_at` của run, không dựa trên gói cuối cùng. Vẫn nên gõ `stoprun`
   trên xe ngay khi có hiệu lệnh dừng để không tốn băng thông/pin.

## 4. Vì sao `run_id` được nhập tay qua console, không tự dò qua REST

Đã cân nhắc phương án xe tự gọi `GET /api/teams/{id}/runs` để tự phát hiện run đang
`running`. Bỏ phương án đó vì: (1) mọi endpoint trừ `/api/auth/login` đều cần JWT — muốn
xe tự dò được phải nhúng một tài khoản `app_users` (dù chỉ role viewer) vào **firmware
của tất cả các xe**, tức là một bí mật dùng chung, rò rỉ một xe là lộ hết; (2) xe nằm
trên VLAN WiFi của FreeRADIUS, không chắc luôn có đường mạng tới cổng HTTP của backend
Java, trong khi cổng UDP ingest thì chắc chắn phải thông. Nhập `run_id` qua console UART
(dây đã cắm sẵn khi nạp firmware/debug tại vạch xuất phát) không cần thêm bí mật nào,
không phụ thuộc topology mạng, và khớp với việc trọng tài vốn đã phải thao tác trên web
để mở run — chỉ thêm một thao tác gõ lệnh tại chỗ.

Nếu ban tổ chức muốn tự động hoá, có thể thay `run_session.c` bằng bản gọi REST, dùng
một tài khoản `app_users` role viewer **riêng cho xe** (khác tài khoản viewer của màn
hình giám khảo) để có thể thu hồi độc lập — không đổi bất cứ gì ở `telemetry_task`/`fairness_guard`.

## 5. Các cơ chế đảm bảo CÔNG BẰNG (fairness_guard.c)

Mọi đội chạy chung một bản firmware (chỉ khác `car_config` nạp riêng từng xe), nên các
ràng buộc dưới đây áp dụng như nhau cho tất cả:

- **Số thứ tự gói (`sequence_no`) không bao giờ lặp lại, nhảy cóc do chủ ý, hay giật lùi**
  trong một run: bộ đếm tăng dần 1 đơn vị mỗi gói, được lưu xuống NVS mỗi
  `SEQ_PERSIST_EVERY` gói để nếu xe khởi động lại giữa lượt (rớt nguồn, treo) thì **tiếp
  tục** từ số cũ thay vì gửi lại từ 0 — tránh việc `logs` bị hiểu nhầm là "mất một đoạn
  lớn rồi lại có gói trùng khoá chính (run_id, sequence_no)" bị `ON CONFLICT DO NOTHING`
  âm thầm loại bỏ.
- **Ép trần tốc độ gửi**: `fairness_guard` từ chối gửi gói nếu chưa đủ
  `TELEMETRY_INTERVAL_MS * (1 - JITTER_TOLERANCE)` kể từ gói trước — không đội nào có thể
  (dù vô tình hay cố ý sửa firmware) gửi dồn dập nhanh hơn 100Hz để "làm đẹp" số liệu độ
  trễ trung bình hay làm nghẽn hàng đợi `ingest_server.py` (vốn có giới hạn `queue-max`
  dùng chung cho mọi xe).
- **Không cho đổi danh tính giữa chừng gói tin**: `run_id`/`team_id` chỉ được gán qua
  `run_session_start()`, mọi module khác (kể cả `ai_perception`) không có quyền ghi hai
  trường này — một lỗi trong code AI của đội không thể vô tình (hay cố ý) làm gói tin đi
  ra dưới `team_id` của đội khác.
- **Kiểm tra kích thước gói**: khớp đúng `MAX_PACKET_BYTES=1400` của `protocol.py`, từ
  chối gửi (đếm cảnh báo) thay vì để hệ điều hành phân mảnh UDP âm thầm.
- **Không gửi khi chưa xác thực xong / chưa có run_id hợp lệ**: loại bỏ khả năng gói
  "rác" trước khi vào vạch xuất phát làm nhiễu observability, dù `ingest_server.py --validate-run`
  đã lọc ở phía server, chặn sớm ở xe vẫn tốt hơn cho băng thông chung.
- **`car_timestamp` luôn lấy từ đồng hồ đã đồng bộ NTP** (`time_sync_now_ms()`), không
  bao giờ dùng tick nội bộ (`esp_timer_get_time()` từ lúc boot) — nếu không, độ trễ mạng
  tính ra ở `logs.car_timestamp` sẽ sai một cách hệ thống và có thể khiến một đội trông
  "mạng tệ hơn" hoặc "tốt hơn" thực tế trên bảng theo dõi.

## 6. Nơi đội cắm AI thật vào (`ai_perception.h`)

File này **chỉ là hợp đồng interface**, không đoán thay phần cứng cảm biến/thuật toán dò
làn — mỗi đội một cấu hình camera/IR khác nhau. Yêu cầu bắt buộc để không phá nhịp 10ms:

```c
esp_err_t ai_perception_read(ai_perception_result_t *out, TickType_t timeout_ticks);
```

phải trả về trong ngân sách **< 8ms** (còn lại dành cho đóng gói + gửi UDP trong chu kỳ
10ms). Nếu mô hình AI chậm hơn, chạy nó ở **task riêng** với tần suất thấp hơn (vd 30Hz),
`ai_perception_read()` chỉ đọc kết quả **mới nhất đã tính sẵn** từ một biến dùng chung
(mutex/atomic), không gọi suy luận đồng bộ ngay trong task gửi log. `ai_perception_stub.c`
minh hoạ đúng mẫu này (biến `static` được một task giả lập cập nhật).

Các trường `ai_result` gửi đi khớp với `car_simulator.py._fake_ai_result` (trừ `x`, `y`
— toạ độ đó chỉ là DEMO khi không có GPS/encoder thật, xe thật không gửi, bản đồ live sẽ
trống — đúng thiết kế ghi trong `car_simulator.py`):

| field | kiểu | ý nghĩa |
|---|---|---|
| `speed_kmh` | float | tốc độ ước lượng |
| `steering_deg` | float | góc lái, âm/dương = trái/phải |
| `lane_offset_cm` | float | lệch khỏi tim làn, âm/dương = trái/phải |
| `obstacle` | bool | có phát hiện vật cản ngay phía trước |
| `confidence` | float 0..1 | độ tin cậy của khung suy luận này |
| `progress` | float 0..1, **tuỳ chọn** | % quãng đường/mê cung đã hoàn thành nếu đội có cách đo (đếm checkpoint...); để trống nếu không có — dashboard mặc định coi là 0, không bắt buộc |

## 7. Build & nạp firmware

```bash
idf.py set-target esp32
idf.py menuconfig     # điền SSID/host/port mặc định trong "Car Config" (có thể để trống, ghi đè qua NVS)
idf.py build flash monitor
```

Sau khi nạp, qua cổng UART console:

```
carcfg set-car car01 team01 <mat_khau_wifi> 3
carcfg show
startrun 42
...
stoprun
```

`carcfg set-car` ghi danh tính xuống NVS (chỉ cần làm 1 lần/xe khi lắp ráp/đăng ký, không
mất khi mất điện). `<mat_khau_wifi>` là mật khẩu gốc dùng để `NtHashGen` sinh `nt_hash`
lưu trong bảng `teams` — PHẢI khớp, vì PEAP xác thực bằng mật khẩu gốc chứ không phải hash.

## 8. Test KHÔNG cần chip ESP32 thật

Không có trang web nào "dán code ESP-IDF vào là chạy giả lập nguyên con xe" — WiFi
WPA2-Enterprise thật và stack mạng thật của chip không mô phỏng được trên web. Có
2 cách test thực tế, cả hai đều dùng ĐÚNG code trong `main/` (không viết lại logic):

### 8.1. Test logic/giao thức trên máy tính (`test/`) — khuyên dùng trước tiên

Biên dịch thẳng `fairness_guard.c` và `telemetry_protocol.c` (file gốc, không sửa)
thành một chương trình chạy trên PC, dùng vài "shim" thay cho API của ESP-IDF
(`esp_log.h` → in ra màn hình, `nvs.h` → lưu xuống 1 file thay vì flash, `cJSON.h` →
bản rút gọn chỉ đủ API cần dùng). Nhờ đó test được **chính xác code sẽ chạy trên chip**,
không phải một bản viết lại riêng để test.

Chạy được trên **cả Windows lẫn Linux/macOS/WSL** — `native_sim.c` tự chọn Winsock hay
socket POSIX bằng `#ifdef _WIN32`, không cần sửa gì giữa hai hệ.

**Linux / macOS / WSL** (đã có sẵn `gcc` và `make`):

```bash
cd test
make -f build.mk
./native_sim --run-id 42 --team-id 3 --host 127.0.0.1 --port 9999 --duration 5 --interval-ms 10
```

**Windows (PowerShell thuần, không cần mở terminal khác mỗi lần)** — Windows không có
sẵn `gcc`. Cài **một lần duy nhất**, sau đó dùng PowerShell bình thường mãi mãi:

1. Cài MSYS2 (chỉ 1 lần): `winget install -e --id MSYS2.MSYS2`
2. Mở **"MSYS2 UCRT64"** từ Start Menu — CHỈ để cài gói compiler, xong thì đóng cửa
   sổ này luôn, không cần mở lại nữa:
   ```bash
   pacman -S --needed mingw-w64-ucrt-x86_64-gcc
   ```
3. Thêm `C:\msys64\ucrt64\bin` vào PATH của Windows để PowerShell tìm thấy `gcc.exe`:
   mở PowerShell (không cần quyền admin) và chạy:
   ```powershell
   [Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\msys64\ucrt64\bin", "User")
   ```
   rồi **đóng và mở lại PowerShell** để PATH mới có hiệu lực (kiểm tra bằng `gcc --version`).
4. Từ giờ về sau, chỉ cần PowerShell bình thường, không cần `make` (Windows không có
   sẵn, khỏi cài thêm) — biên dịch thẳng bằng 1 lệnh `gcc`:
   ```powershell
   cd D:\Hackathon\hackathon-chip-logic\test
   gcc -Wall -O2 -std=gnu11 -I../main -Ishim -Ivendor -o native_sim.exe native_sim.c ../main/fairness_guard.c ../main/telemetry_protocol.c shim/nvs_shim.c vendor/cJSON.c -lm -lws2_32
   .\native_sim.exe --run-id 42 --team-id 3 --host 127.0.0.1 --port 9999 --duration 5 --interval-ms 10
   ```

**Ubuntu / WSL / macOS** (đã có sẵn `gcc`): dùng `make -f build.mk` như mục Linux ở
trên — cùng một bộ file `test/`, không cần sửa gì để chạy được ở cả hai hệ. Nếu chạy
trong WSL, project trên ổ D đã sẵn ở `/mnt/d/Hackathon/hackathon-chip-logic/test`,
không cần copy.

Đối chiếu gói tin bằng **chính hàm `protocol.decode()`** của dự án (không tự đoán lại
schema) — chạy song song ở cửa sổ khác trước khi chạy `native_sim`:

```bash
# mặc định tự tìm Car/simulator/protocol.py ở thư mục cha (../../hackathon-server/Car/simulator);
# nếu đặt project ở chỗ khác, trỏ tay bằng biến môi trường:
HACKATHON_PROTOCOL_DIR=/duong/dan/toi/Car/simulator python3 test/verify_wire_format.py
```

Script in ra: có đủ 5 field gốc + field `ai_result` không, `sequence_no` có liên tục
(không thủng khoảng) không, gói có vượt 1400 byte không — kết luận `PASS`/`FAIL`. Đã
chạy thử ngay khi viết bộ này và xác nhận: 100% gói decode được, `sequence_no` liên
tục tuyệt đối, và khi khởi động lại `native_sim` với CÙNG `run_id`, `fairness_guard`
tự tiếp tục đúng từ số thứ tự cũ (test "xe reset giữa lượt") — kể cả khi cố tình gọi
với `--interval-ms 2` (nhanh gấp 5 lần cho phép), `fairness_guard` chặn đúng phần vượt
mức, chỉ để lọt qua đúng nhịp 10ms.

Muốn test full pipeline (kể cả ghi DB + hiện lên dashboard thật), chỉ cần đổi
`--host`/`--port` trỏ tới `ingest_server.py` thật đang chạy (`python
Car/simulator/ingest_server.py --port 9999`) rồi mở `hackathon-frontend` lên xem —
`native_sim` đóng vai trò y hệt `car_simulator.py` nhưng chạy code C thật của chip.

### 8.2. Xem trực quan bằng Wokwi (mô phỏng bo mạch ESP32 trong VS Code)

[Wokwi](https://wokwi.com) mô phỏng được phần cứng ESP32 và chạy được firmware ESP-IDF
thật (không phải chỉ Arduino), nhưng WiFi ảo của Wokwi **không hỗ trợ WPA2-Enterprise
thật** — nên không test được bước xác thực RADIUS ở đây, chỉ test được: FreeRTOS chạy
đúng nhịp 10ms, console UART nhận lệnh, nội dung gói JSON đúng schema.

1. Cài extension **"Wokwi for VS Code"** (miễn phí, cần tài khoản Wokwi).
2. `idf.py set-target esp32 && idf.py menuconfig` → vào **"Hackathon Chip Config"** →
   bật **"Che do mo phong (Wokwi / khong co WiFi Enterprise that)"** (`CONFIG_CHIP_SIM_MODE`).
   Cờ này khiến firmware **bỏ qua** bước xác thực WiFi/SNTP thật và tự `startrun 1` ngay
   khi khởi động — **không bao giờ bật cờ này khi build firmware nạp thật lên xe thi đấu**.
3. `idf.py build`.
4. Copy `wokwi/wokwi.toml` và `wokwi/diagram.json` ra thư mục gốc project (ngang hàng
   `CMakeLists.txt`).
5. Mở Command Palette (F1) → **"Wokwi: Start Simulator"**.
6. Xem Serial Monitor: mỗi ~1 giây có 1 dòng `sim_packet seq=... bytes=... {...}` —
   chính là gói JSON mà chip sẽ gửi, kèm số thứ tự tăng đều đúng nhịp — xem bằng mắt
   không cần máy chủ nào ở đầu nhận.
