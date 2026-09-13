# Review guide — hackathon-chip-logic / pi-daemon

Repo này KHÔNG có `specs_dev/` hay `.claude/rules/` (không phải backend
NestJS+Drizzle). Nguồn convention chuẩn của dự án là chính các file tài liệu
đã có, đọc trước khi review:

- `README.md` — kiến trúc tổng quan, 3 loại tài khoản, lý do công bằng.
- `pi-daemon/README.md` — kiến trúc `carlogd`, lý do thiết kế.
- `pi-daemon/provision/README.md` — cách cài đặt/phân quyền OS trên Pi.
- `HUONG_DAN_TRIEN_KHAI_A_DEN_Z.md` — quy trình triển khai đầu-cuối.
- Comment trong chính code (`carlogd.py`, `config.py`) — mỗi chỗ "bỏ qua lỗi
  im lặng" đều có giải thích lý do, dùng làm mẫu khi review code mới.

## Bất biến cốt lõi (vi phạm bất kỳ điều nào bên dưới → CAO)

1. **4 trường thí sinh không được chạm vào**: `run_id`, `team_id`,
   `sequence_no`, `car_timestamp`. Chỉ được set trong `_start_run_locked()`
   (control_server/api_poll_loop) và `sender_loop()`. Dữ liệu từ
   `ai_submit_server()` (UDP thí sinh) chỉ được phép rơi vào các field AI
   (`speed_kmh`, `steering_deg`, `lane_offset_cm`, `obstacle`, `confidence`,
   `progress`).
2. **Socket điều khiển marshal** (`CONTROL_SOCKET`) phải giữ mode 0660 +
   group `carlog`. Không nới lỏng permission, không thêm đường tắt cho phép
   user khác gọi START/STOP.
3. **Không dùng JWT admin/viewer** để xe tự hỏi trạng thái — chỉ dùng header
   `X-Car-Api-Key` qua `/api/teams/{id}/car-status` (xem lý do trong
   `carlogd.py` mục 2b — cơ chế cũ `_api_login`/`_api_get_team_runs` bị bỏ vì
   lộ dữ liệu chéo đội).
4. **Thư mục/file mới dưới `/opt/carlogd`, `/var/lib/carlogd`** phải có
   `chmod` chặt (750 trở xuống) — mặc định `chown` không đủ, thư mục vẫn
   world-readable (bài học thật: từng thiếu `chmod 750` trong hướng dẫn A-Z).
5. **Nhịp gửi 10ms (`sender_loop`)** không được chèn I/O blocking không giới
   hạn thời gian (HTTP, DB, file lock chờ lâu...) — làm trôi nhịp là phá tính
   công bằng giữa các đội.
6. **Không viết lại schema `protocol.py`** — `carlogd` phải import thẳng từ
   `PROTOCOL_DIR`, không tự đoán lại format gói tin.

## Loại bug đã từng xảy ra thật trong repo (ưu tiên soi lại mỗi PR)

- **Exception từ dữ liệu thí sinh làm chết thread nền vĩnh viễn**: mọi chỗ ép
  kiểu (`float()`, `int()`, index dict) trên JSON thí sinh gửi qua UDP phải
  nằm trong try/except rõ ràng — không bắt được thì thread `ai_submit_server`
  chết âm thầm, service vẫn báo "active" nhưng ngừng nhận dữ liệu AI cho cả
  trận. (Đã sửa 1 lần ở `_coerce_ai_payload`/`_coerce_obstacle` — coi đây là
  mẫu chuẩn cho code tương tự.)
- **`bool(str)` luôn truthy**: không dùng `bool(value)` trực tiếp cho dữ liệu
  boolean thí sinh gửi dạng chuỗi (`"false"` → `bool("false") == True`).
- **Tài liệu lệch code**: đổi tên biến môi trường, port mặc định, đường dẫn
  file, hoặc bước cài đặt trong code mà không cập nhật đúng chỗ tương ứng
  trong 4 file tài liệu ở trên.

## Phạm vi review

- Repo nhỏ, không có noise "legacy lớn" như backend NestJS — nhưng vẫn chỉ
  báo vấn đề PR THÊM MỚI hoặc PR làm lộ ra (đừng báo lại pattern cũ không bị
  đụng tới).
- Thư mục `main/`, `test/`, `wokwi/` ở cấp gốc (nếu xuất hiện) là bản
  ESP32/FreeRTOS cũ, tự nhận trong README là "không phải kiến trúc chính
  thức" — không áp bất biến của `pi-daemon/` (Python/Pi) vào đó.
