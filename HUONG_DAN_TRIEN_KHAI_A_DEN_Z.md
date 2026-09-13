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

## PHẦN B — Server (máy chủ Windows, dùng bản đóng gói .exe)

Bản Electron đóng gói (`Pit Wall Console.exe`) tự chạy ngầm cả backend (Java) lẫn `ingest_server.py` (Python) ngay khi mở app — **không cần tự gõ `mvn spring-boot:run` hay `python ingest_server.py` tay nữa**, chỉ build 1 lần rồi mở file `.exe` là xong. Postgres vẫn phải tự cài/chạy sẵn như 1 dịch vụ Windows bình thường (app không quản lý Postgres).

**B1. Tìm IP LAN của máy này** (bạn của bạn sẽ nối vào đúng IP này) — mở PowerShell:
```
ipconfig
```
Lấy dòng **IPv4 Address** (dạng `192.168.x.x`). Khuyến nghị đặt **IP tĩnh** cho máy này (Network Settings → đổi từ DHCP) để IP không đổi mỗi lần khởi động lại, tránh phải build lại `.exe`.

**B2. Điền IP đó vào `.env`** (`hackathon-frontend/.env`, sửa dòng cuối):
```
VITE_DEFAULT_API=http://<IP vừa lấy ở B1>:8080
```

**B3. (Nếu bạn đã đổi mật khẩu DB role / JWT secret khác mặc định trong `init_basic_int.txt`)** — đặt các biến dưới đây làm **Windows System Environment Variables** (Control Panel → System → Advanced → Environment Variables), **không phải chỉ ghi trong file `.env`** — vì bản `.exe` mở trực tiếp bằng double-click, không đi qua bước `export` như chạy tay:
```
HACKATHON_ADMIN_PASSWORD=...
HACKATHON_VIEWER_PASSWORD=...
HACKATHON_INGEST_PASSWORD=...
APP_JWT_SECRET=...
```
Riêng biến dưới đây **bắt buộc phải đặt** dù không đổi mật khẩu gì (mặc định `ingest_server.py` chỉ nhận gói từ chính máy nó, không nhận được từ xe qua mạng):
```
HACKATHON_UDP_HOST=0.0.0.0
```

**B4. Build (chỉ 1 lần, hoặc mỗi khi sửa code/IP):**
```
cd hackathon-server\hackathon-frontend
npm run electron:build
```
File cài đặt nằm ở `release\Pit Wall Console Setup 1.0.0.exe`. Cài xong, **mở app từ Start Menu** — nó tự chạy ngầm backend + ingest + mở luôn dashboard, không cần mở terminal/gõ lệnh gì thêm từ lần sau.

> Vừa mở app, backend (Java) mất vài giây để khởi động xong — app tự hiện màn hình **"Đang khởi động backend..."** và tự thử lại ngầm, **không cần đăng xuất/đăng nhập lại** như trước nữa. Nếu màn hình này giữ nguyên quá lâu (báo gợi ý kiểm tra Java/Postgres), kiểm tra máy đã cài Java 21+ và Postgres đang chạy chưa.

**B5. Mở firewall** (Windows Defender Firewall → New Inbound Rule, hoặc PowerShell chạy với quyền Admin):
```powershell
New-NetFirewallRule -DisplayName "PitWall Backend" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow
New-NetFirewallRule -DisplayName "PitWall Ingest" -Direction Inbound -Protocol UDP -LocalPort 9999 -Action Allow
```

> Nếu bạn triển khai backend/ingest tách riêng trên 1 máy chủ Linux (không dùng bản `.exe` all-in-one này) thì vẫn chạy tay như trước: `mvn spring-boot:run`, `python3 ingest_server.py --port 9999` (nhớ `HACKATHON_UDP_HOST=0.0.0.0`), và build frontend bằng `npm run build` + phục vụ qua web server, hoặc `npm run dev -- --host 0.0.0.0` để test nhanh.

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
ping -c 3 <IP máy chủ ở B1>
```
Lỗi thì xem `journalctl -u wpa_supplicant@wlan0 -f` (Pi) và `sudo tail -f /var/log/freeradius/radius.log` (FreeRADIUS).

---

## PHẦN F — Đồng bộ giờ trên Pi

```bash
sudo timedatectl set-ntp true
# nếu mạng thi đấu không Internet, trỏ NTP nội bộ (vd chính máy chủ):
sudo sed -i 's/^#NTP=.*/NTP=<IP máy chủ ở B1>/' /etc/systemd/timesyncd.conf
sudo systemctl restart systemd-timesyncd
timedatectl status                   # "System clock synchronized: yes"
```
Bắt buộc — nếu lệch giờ, cột "độ trễ mạng" trên dashboard hiển thị sai (có thể ra số âm).

---

## PHẦN G — Cài carlogd trên Pi

**Làm bước này LẶP LẠI cho TỪNG xe** — mỗi đội có 1 Raspberry Pi VẬT LÝ RIÊNG (thẻ SD riêng, hệ điều hành riêng), không phải 1 file cấu hình chung liệt kê nhiều đội. Có N đội thì SSH lần lượt vào N con Pi khác nhau, chạy Y HỆT bộ lệnh dưới đây trên từng con — chỉ 2 dòng đổi khác theo từng xe: `CARLOGD_TEAM_ID` và `CARLOGD_API_KEY` (lấy đúng giá trị của đội đó từ bước A4).

Ví dụ 3 đội = 3 con Pi = làm bộ lệnh dưới đây **3 lần** (SSH vào IP khác nhau mỗi lần):

| | Pi đội A | Pi đội B | Pi đội C |
|---|---|---|---|
| `CARLOGD_TEAM_ID` | `1` | `2` | `3` |
| `CARLOGD_API_KEY` | khoá đội A | khoá đội B | khoá đội C |

Việc này chỉ làm **1 lần khi lắp ráp xe** (trước ngày thi), không phải làm lại mỗi lần thi đấu — `carlogd` tự chạy nền vĩnh viễn trên xe (nhờ `systemctl enable`), thi đấu thật chỉ còn thao tác ở Phần H.

```bash
sudo useradd -m -s /bin/bash pilot                 # tài khoản thí sinh
sudo useradd -r -s /usr/sbin/nologin carlog         # tài khoản chạy dịch vụ

sudo mkdir -p /opt/carlogd /opt/hackathon
sudo cp carlogd.py carlogctl.py config.py /opt/carlogd/
sudo cp -r hackathon-server/Car /opt/hackathon/Car   # cần protocol.py thật
sudo chown -R carlog:carlog /opt/carlogd /opt/hackathon
sudo chmod 750 /opt/carlogd
```

**Bắt buộc — không được bỏ qua `chmod 750` ở trên.** Chỉ `chown` thôi thì thư
mục vẫn có quyền mặc định `rwxr-xr-x` (world-readable) — nghĩa là user `pilot`
(thí sinh, không thuộc group `carlog`) vẫn `cd`/`cat` đọc được toàn bộ
`carlogd.py`, `carlogctl.py`, và **`config.py` (chứa `CARLOGD_API_KEY` của
đội)** dù không sửa/xoá được. `chmod 750` (rwx cho `carlog`, r-x cho group
`carlog`, không quyền gì cho người khác) mới thật sự khớp với cam kết "thí
sinh không có quyền đọc" ghi trong README chính — thiếu bước này thì lời cam
kết đó chỉ đúng một nửa (chặn được sửa/tắt, chưa chặn được đọc).

```bash
sudo nano /opt/carlogd/config.py
```
Sửa trong `config.py`:
```python
CARLOGD_TEAM_ID = <id đội, khớp teams.id>
CARLOGD_INGEST_HOST = "<IP máy chủ ở B1>"

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

## Phụ lục — Cho máy khác (bạn của bạn) mở được dashboard

Bản `.exe` đóng gói **tự chạy backend + ingest + Postgres cục bộ trên chính máy đang mở app**, và địa chỉ API (`VITE_DEFAULT_API` trong `.env`) bị ghi cứng ngay lúc build (Phần B2) — nên chỉ cần:

1. Máy bạn (máy chạy `npm run electron:build`) đã điền đúng IP LAN của chính nó vào `.env` (Phần B1-B2) trước khi build.
2. Gửi nguyên file `release\Pit Wall Console Setup 1.0.0.exe` cho bạn của bạn — họ cài lên máy họ, mở lên là vào thẳng đúng dữ liệu đua trên máy bạn, **không cần cấu hình gì thêm ở máy họ**.

Lưu ý: máy họ cài bản này cũng sẽ tự thử chạy 1 backend/ingest riêng trên máy họ (vô hại — chỉ lãng phí chút tài nguyên nếu máy họ không có Postgres/Java, app vẫn hiển thị đúng vì đã trỏ thẳng IP máy bạn) — không ảnh hưởng gì tới dữ liệu thật. Nếu IP máy bạn đổi (xem lưu ý đặt IP tĩnh ở B1), phải sửa lại `.env` và `npm run electron:build` lại, gửi file `.exe` mới.

---

## PHẦN H — Chạy thật + kiểm tra

Làm được đồng thời cho nhiều đội (nhiều xe chạy song song ở nhiều khu đua) — các bước dưới đây độc lập theo từng đội, không cần chờ đội này xong mới làm đội khác.

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

---

## Phụ lục — Kiểm tra carlogd chịu được dữ liệu AI "cẩu thả" từ thí sinh

Thí sinh viết code tự do (Python/C/Node/Go...) nên **chắc chắn** sẽ có đội gửi
dữ liệu sai kiểu (chuỗi thay vì số, `null` khi chưa kịp gán giá trị, boolean
serialize thành chuỗi `"false"`...). `carlogd.py` phải bỏ qua đúng gói lỗi đó
và **tiếp tục nhận các gói hợp lệ sau đó** — không được để 1 gói lỗi làm dịch
vụ ngừng nhận dữ liệu AI cho cả trận (dù `systemctl status` vẫn báo
`active`). Test tự động việc này (không cần Pi/mạng thật):

```bash
cd pi-daemon/test
python3 run_local_test.py --protocol-dir /duong/dan/toi/Car/simulator
```

Test này giờ tự chèn một loạt gói sai kiểu vào giữa luồng dữ liệu và kiểm tra
`carlogd` còn sống + vẫn nhận được gói hợp lệ ngay sau đó mới báo `PASS`.
Muốn tự tay gửi từng trường hợp lỗi để xem log `carlogd` phản ứng thế nào,
chạy `carlogd.py` thật (vd qua `run_carlogd_demo.ps1`) rồi ở cửa sổ khác:

```bash
python3 pi-daemon/test/send_bad_ai_examples.py
```
