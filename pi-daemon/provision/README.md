# Cài đặt carlogd lên Raspberry Pi (làm 1 lần khi lắp ráp xe)

Thứ tự các bước dưới đây **quan trọng**: tách user Linux trước, rồi mới cài
dịch vụ — làm ngược lại thì thí sinh có thể đã có quyền truy cập trước khi bị
khoá lại.

## 1. Tách 2 tài khoản Linux: `pilot` (thí sinh) và `carlog` (dịch vụ)

```bash
sudo useradd -m -s /bin/bash pilot          # tai khoan SSH cho thi sinh
sudo passwd pilot                            # dat mat khau/hoac cau hinh SSH key rieng
sudo useradd -r -s /usr/sbin/nologin carlog  # tai khoan he thong, KHONG login duoc, chi de chay dich vu
```

`pilot` là tài khoản duy nhất bạn đưa cho thí sinh. Thí sinh **không** có mật
khẩu/quyền của `carlog`, và `carlog` không nhận đăng nhập trực tiếp (`nologin`) —
kể cả khi thí sinh có `sudo` trên tài khoản của họ (nếu bạn cho phép, để họ tự
cài thư viện Python/OpenCV...), họ vẫn không tự nhiên đọc được socket điều
khiển vì quyền file (mục 3), trừ khi họ leo thang bằng chính `sudo` đó — nếu lo
ngại, **không cấp `sudo`** cho `pilot`, chỉ cài sẵn mọi thư viện thí sinh cần
trước khi giao xe.

## 2. Cài carlogd

```bash
sudo mkdir -p /opt/carlogd /opt/hackathon
sudo cp carlogd.py carlogctl.py config.py /opt/carlogd/
# Car/simulator/protocol.py phai co that tren Pi de carlogd import - copy nguyen
# thu muc Car/ tu repo (hoac chi can protocol.py) vao day:
sudo cp -r /path/to/hackathon-server/Car /opt/hackathon/Car
sudo chown -R carlog:carlog /opt/carlogd /opt/hackathon
sudo chmod 750 /opt/carlogd
```

**`chmod 750` là bước bắt buộc, không phải tuỳ chọn** — chỉ `chown` thì thư
mục vẫn ở quyền mặc định `rwxr-xr-x`, nghĩa là `pilot` (thí sinh) tuy không
sửa/xoá được nhưng vẫn **đọc được** `carlogd.py`/`config.py` (kể cả
`CARLOGD_API_KEY`). `chmod 750` mới thật sự chặn cả việc đọc, đúng như cam
kết "thí sinh không có quyền đọc/sửa/tắt" ở README chính.

Sửa `/opt/carlogd/config.py` (hoặc đặt biến môi trường trong service file) —
ít nhất `CARLOGD_TEAM_ID` (số, trùng `teams.id` của đội) và `CARLOGD_INGEST_HOST`
(IP máy chạy `ingest_server.py` thật trên mạng thi đấu).

```bash
sudo cp carlogd.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now carlogd
sudo systemctl status carlogd   # phai thay "active (running)"
```

## 3. Cho phép marshal (không phải thí sinh) điều khiển start/stop

`carlogd.service` chạy dưới `User=carlog`, socket điều khiển
`/run/carlogd/control.sock` chỉ user/group `carlog` đọc-ghi được (0660, xem
`carlogd.service` mục `RuntimeDirectoryMode`). Thêm tài khoản của **marshal**
(người vận hành, không phải thí sinh) vào group `carlog`:

```bash
sudo usermod -aG carlog ten_tai_khoan_marshal
```

Marshal SSH vào bằng tài khoản riêng đó (không phải `pilot`), chạy:

```bash
python3 /opt/carlogd/carlogctl.py start 42   # run_id lay tu POST /api/runs tren web admin
python3 /opt/carlogd/carlogctl.py stop
python3 /opt/carlogd/carlogctl.py status
```

Thí sinh (`pilot`) chạy đúng 2 lệnh trên sẽ bị từ chối kết nối vì không thuộc
group `carlog` — chỉ có thể `sendto()` vào cổng nhận kết quả AI (mở, đúng ý
đồ) chứ không mở/đóng được lượt chạy.

## 4. Cấu hình mạng + đồng bộ giờ (không cần code, chỉ cần cấu hình chuẩn của Linux)

- WiFi WPA2-Enterprise: xem `wpa_supplicant-example.conf` trong thư mục này.
- Đồng bộ giờ (bắt buộc để độ trễ mạng hiển thị đúng cho giám khảo — xem
  `init_basic_int.txt`: "hiệu số ÂM nghĩa là đồng hồ xe chưa đồng bộ NTP"):
  ```bash
  sudo timedatectl set-ntp true
  timedatectl status    # kiem tra dong "System clock synchronized: yes"
  ```
  Nếu mạng thi đấu không có Internet, trỏ về 1 máy NTP nội bộ của ban tổ chức:
  ```bash
  sudo sed -i 's/^#NTP=.*/NTP=10.0.0.1/' /etc/systemd/timesyncd.conf
  sudo systemctl restart systemd-timesyncd
  ```

## 5. Kiểm tra nhanh (không cần mạng thi đấu thật)

```bash
# gia lap ingest_server.py bang script co san (chay tren PC khac, hoac ngay tren Pi):
python3 /path/to/Car/simulator/ingest_server.py --port 9999

# tren Pi: doi CARLOGD_INGEST_HOST tro ve may dang chay ingest_server.py o tren,
# roi khoi dong lai carlogd, sau do:
python3 /opt/carlogd/carlogctl.py start 1
python3 /path/to/pi-daemon/sdk/send_result_example.py   # dong vai thi sinh, gui 1 goi
python3 /opt/carlogd/carlogctl.py status
```
Cửa sổ `ingest_server.py` phải thấy `nhan=` tăng lên.

## Vì sao thiết kế 2 tài khoản + Unix socket, không phải "để thí sinh tự cẩn thận"

Đề bài cho thí sinh SSH vào chip nghĩa là họ **có shell**, khả năng cao cũng
có thể đọc được toàn bộ mã nguồn `carlogd.py` nếu không chặn quyền đọc thư
mục `/opt/carlogd` — đây chính là lý do bước `chmod 750 /opt/carlogd` ở mục 2
là bắt buộc (chỉ `chown carlog:carlog` không đủ, mặc định thư mục vẫn
world-readable).
Việc tách quyền ở tầng hệ điều hành (không phải "quy định miệng: đừng đụng
vào") là hàng rào kỹ thuật thật sự tương đương vai trò `fairness_guard.c` bên
bản ESP32 trước đó — chỉ khác là ở đây hàng rào nằm ở quyền file Linux thay
vì ở logic C chạy trên vi điều khiển không có hệ điều hành.
