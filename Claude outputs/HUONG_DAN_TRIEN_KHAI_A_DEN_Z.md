# Hướng dẫn triển khai từ A đến Z — Cuộc thi đua xe

Tài liệu này đi từ database trống tới 1 lượt xe chạy thật, log hiện lên dashboard. Làm đúng thứ tự, không bỏ bước.

## Kiến trúc tóm tắt

- **Xe (Raspberry Pi)**: thí sinh SSH vào để viết code AI. Chương trình `carlogd` (do BTC cài, thí sinh không đụng được) lo toàn bộ việc kết nối mạng đúng chuẩn + gửi log đúng định dạng — thí sinh chỉ cần gửi UDP tới `127.0.0.1:8765`.
- **Mạng**: router WiFi WPA2-Enterprise, xác thực qua FreeRADIUS (đọc thẳng từ bảng `teams` trong Postgres).
- **Server**: `ingest_server.py` (Python, nhận UDP ghi vào Postgres) + backend Spring Boot (API + WebSocket) + frontend React (dashboard "Pit Wall" cho giám khảo).
- **3 loại tài khoản khác nhau, không dùng lẫn**:
  | Tài khoản | Ai/cái gì dùng | Dùng để làm gì |
  |---|---|---|
  | `teams.username` + `nt_hash` | Xe (qua `wpa_supplicant`, hệ điều hành) | Lên WiFi WPA2-Enterprise |
  | `app_users` (role `admin`) | Giám khảo/marshal, đăng nhập web | Mở/kết thúc/hủy lượt, bấm "Bắt đầu ghi log" |
  | `teams.car_api_key` | Chương trình `carlogd` trên xe (không phải người) | Tự hỏi web "lượt của đội tôi đã duyệt bắt đầu chưa" — **chỉ đọc được đúng đội mình**, dù bị lộ cũng không xem được dữ liệu đội khác |

---

## PHẦN A — Database (máy chủ)

**A1. Tạo schema (chạy 1 lần):**
```bash
sudo -u postgres psql -f init_basic_int.txt
```

**A2. Mật khẩu thật cho tài khoản `admin` (web):**
```bash
cd hackathon-backend
mvn -q compile exec:java -Dexec.mainClass="com.hackathon.backend.tool.HashGen" -Dexec.args="mat_khau_admin_that"
```
```sql
UPDATE app_users SET password_hash = '<hash vừa in ra>' WHERE username = 'admin';
```

**A3. `nt_hash` cho từng đội (để lên WiFi) — dùng `NtHashGen`, KHÔNG dùng `HashGen`:**
```bash
mvn -q compile exec:java -Dexec.mainClass="com.hackathon.backend.tool.NtHashGen" -Dexec.args="mat_khau_doi_1"
```
```sql
UPDATE teams SET nt_hash = '<hash vừa in ra>' WHERE username = 'team01';
-- lặp lại cho từng đội thật
```

**A4. `car_api_key` cho từng đội (để xe tự hỏi trạng thái lượt chạy) — dùng nút trên web, không cần biết SQL:**

Trong Admin Console, ở dòng của từng đội, bấm **"Sinh chìa khoá xe"**. Hệ thống tự sinh 1 chìa khoá ngẫu nhiên thật sự an toàn (không phải sinh bằng SQL `random()`), lưu vào DB, và hiện ra **đúng 1 lần duy nhất** để copy — lưu lại ngay để điền vào `config.py` của đúng xe đội đó (bước G). Bấm lại sẽ sinh khoá mới, khoá cũ mất hiệu lực ngay.

(Chỉ dùng SQL tay nếu chưa build lại backend hoặc muốn thao tác thẳng trên DB:
```sql
UPDATE teams SET car_api_key = md5(random()::text || clock_timestamp()::text) WHERE id = 1;
```
)

---

## PHẦN B — Backend + ingest_server + frontend (máy chủ)

**B1. Cấu hình backend:**
```bash
cd hackathon-backend
cp .env.example .env
# sửa .env: mật khẩu app_admin/app_viewer khớp A1, APP_JWT_SECRET tối thiểu 32 ký tự
```

**B2. Build + chạy backend:**
```bash
mvn clean package
export $(cat .env | xargs)
mvn spring-boot:run &
```

**B3. Chạy `ingest_server.py`** — bắt buộc `UDP_HOST=0.0.0.0` để nhận gói từ Pi qua mạng (mặc định chỉ nhận từ localhost):
```bash
export HACKATHON_UDP_HOST=0.0.0.0
export HACKATHON_UDP_PORT=9999
export HACKATHON_DB_HOST=localhost
export HACKATHON_INGEST_PASSWORD=doi_mat_khau_2
python3 Car/simulator/ingest_server.py --port 9999 &
```

**B4. Chạy frontend** — bắt buộc `--host` để máy khác trong mạng mở được dashboard (mặc định Vite chỉ bind localhost):
```bash
cd hackathon-frontend
npm install
npm run dev -- --host 0.0.0.0 &
```

**B5. Mở firewall:**
```bash
sudo ufw allow 8080/tcp     # backend
sudo ufw allow 9999/udp     # ingest_server
sudo ufw allow 5173/tcp     # frontend
```

**B6. Lấy IP LAN máy chủ** (Pi sẽ trỏ vào đây): `ip addr show`

---

## PHẦN C — FreeRADIUS

**C1.** Khai router là 1 "client" trong `/etc/freeradius/3.0/clients.conf`:
```
client router_thi_dau {
    ipaddr = <IP router>
    secret = <tự đặt, khai lại y hệt ở router>
}
```

**C2.** Xác nhận `mods-enabled/sql` trỏ đúng role `radius_reader` + `queries.conf` đọc `(username, nt_hash, is_active)` từ bảng `teams` (chi tiết: `hackathon-backend/README.md` mục 6).

**C3.**
```bash
sudo systemctl restart freeradius
```

**(Tùy chọn) Test không cần router thật, dùng `eapol_test`** — giả lập vai trò access point, nói chuyện thẳng với FreeRADIUS qua mạng:
```bash
sudo apt install build-essential libssl-dev libnl-3-dev libnl-genl-3-dev libnl-route-3-dev pkg-config
git clone https://w1.fi/wpa_supplicant.git
cd wpa_supplicant/wpa_supplicant
cp defconfig .config && echo "CONFIG_EAPOL_TEST=y" >> .config
make eapol_test
./eapol_test -c test.conf -a <IP FreeRADIUS> -s <shared_secret> -p 1812   # in "SUCCESS" là đúng
```

---

## PHẦN D — Router

Bật **WPA2-Enterprise** (không phải PSK) cho SSID thi đấu, khai IP FreeRADIUS + port 1812 (+1813 nếu có) + secret khớp C1.

---

## PHẦN E — Raspberry Pi lên WiFi

Không cần viết code — Linux có sẵn dịch vụ `wpa_supplicant` lo việc này (khác ESP32 phải tự gọi hàm C).

**E1.**
```bash
sudo cp wpa_supplicant-example.conf /etc/wpa_supplicant/wpa_supplicant-wlan0.conf
sudo nano /etc/wpa_supplicant/wpa_supplicant-wlan0.conf
# sửa: ssid = SSID ở D, identity/password = khớp đội đã tạo nt_hash ở A3
sudo chmod 600 /etc/wpa_supplicant/wpa_supplicant-wlan0.conf
```

**E2.**
```bash
sudo systemctl enable --now wpa_supplicant@wlan0
sudo systemctl restart wpa_supplicant@wlan0
wpa_cli -i wlan0 status              # phải thấy wpa_state=COMPLETED
iwconfig wlan0
ip addr show wlan0
ping -c 3 <IP máy chủ ở B6>
```
Lỗi thì xem `journalctl -u wpa_supplicant@wlan0 -f` (Pi) và `sudo tail -f /var/log/freeradius/radius.log` (FreeRADIUS).

---

## PHẦN F — Đồng bộ giờ trên Pi

```bash
sudo timedatectl set-ntp true
# nếu mạng thi đấu không Internet, trỏ NTP nội bộ (vd chính máy chủ):
sudo sed -i 's/^#NTP=.*/NTP=<IP máy chủ ở B6>/' /etc/systemd/timesyncd.conf
sudo systemctl restart systemd-timesyncd
timedatectl status                   # "System clock synchronized: yes"
```
Bắt buộc — nếu lệch giờ, cột "độ trễ mạng" trên dashboard hiển thị sai (có thể ra số âm).

---

## PHẦN G — Cài carlogd trên Pi

```bash
sudo useradd -m -s /bin/bash pilot                 # tài khoản thí sinh
sudo useradd -r -s /usr/sbin/nologin carlog         # tài khoản chạy dịch vụ

sudo mkdir -p /opt/carlogd /opt/hackathon
sudo cp carlogd.py carlogctl.py config.py /opt/carlogd/
sudo cp -r hackathon-server/Car /opt/hackathon/Car   # cần protocol.py thật
sudo chown -R carlog:carlog /opt/carlogd /opt/hackathon
sudo chmod 750 /opt/carlogd

sudo nano /opt/carlogd/config.py
```
Sửa trong `config.py`:
```python
CARLOGD_TEAM_ID = <id đội, khớp teams.id>
CARLOGD_INGEST_HOST = "<IP máy chủ ở B6>"

# Để dùng nút "Bắt đầu ghi log" trên web (khuyến nghị — không cần SSH mỗi lượt):
CARLOGD_API_BASE = "http://<IP máy chủ>:8080"
CARLOGD_API_KEY = "<car_api_key của ĐÚNG đội này, lấy từ bước A4>"
```

```bash
sudo cp carlogd.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now carlogd
sudo systemctl status carlogd        # phải "active (running)"

# Nếu KHÔNG dùng nút web, cho marshal quyền gõ lệnh start/stop:
sudo usermod -aG carlog ten_tai_khoan_marshal
```

**Vì sao an toàn dù thí sinh SSH vào cùng con Pi:**
- `carlogd` chạy dưới user `carlog`, thí sinh dùng user `pilot` — không cùng quyền, không sửa/tắt được `carlogd`, không tự gọi được lệnh start/stop (chặn ở quyền socket Unix 0660).
- `CARLOGD_API_KEY` trong `config.py` dù bị thí sinh đọc được cũng chỉ dùng để hỏi đúng trạng thái đội mình (`GET /api/teams/{id}/car-status`) — không đọc được log/tốc độ của đội khác, không mở/sửa/xóa được gì.

---

## PHẦN H — Chạy thật + kiểm tra

1. Marshal đăng nhập web bằng `admin` → mở lượt chạy mới cho đội đó.
2. Marshal bấm **"Bắt đầu ghi log"** trên dashboard (carlogd tự nhận trong ~1 giây) — hoặc nếu không dùng nút web, SSH bằng tài khoản marshal và gõ:
   ```bash
   python3 /opt/carlogd/carlogctl.py start <run_id>
   ```
3. Thí sinh chạy code AI (tài khoản `pilot`), gửi UDP tới `127.0.0.1:8765` theo schema `protocol.py` (tham khảo `pi-daemon/sdk/`).
4. Kiểm tra:
   - Cửa sổ `ingest_server.py` (B3): số gói `nhan=` tăng liên tục.
   - Dashboard FE (Live Timing / Nhật ký log): dữ liệu lượt đó chạy theo thời gian thực.
5. Marshal bấm "Kết thúc" (hoặc "Hủy" nếu sự cố) để đóng lượt.

---

## Phụ lục — Test nhanh không cần router/Pi thật (demo trên 1 máy Windows/Linux)

```bash
python3 Car/simulator/ingest_server.py --port 9999   # server giả lập
# trên "xe" (có thể cùng máy):
python3 carlogd.py           # dùng run_carlogd_demo.ps1 trên Windows để tự set biến môi trường
python3 sdk/send_result_example.py     # gửi 1 gói, giả lập thí sinh
# hoặc: python3 demo_drive_loop.py     # gửi liên tục, số liệu biến thiên như xe thật
```
