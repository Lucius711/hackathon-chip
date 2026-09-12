# pi-daemon — phần "kết nối mạng + gửi log" cho xe chạy Raspberry Pi

**Đây là bản đúng với yêu cầu thật**: xe dùng Raspberry Pi (không phải ESP32),
thí sinh SSH vào chip để tự viết code lái/AI. Ban tổ chức (bạn) chỉ cần chuẩn
bị đúng phần: kết nối vào mạng thi đấu (WiFi WPA2-Enterprise) + gửi log về
đúng định dạng database — thí sinh không đụng vào phần này.

(Thư mục `main/`, `test/`, `wokwi/` ở cấp trên là bản làm cho ESP32/FreeRTOS
trước khi biết rõ yêu cầu — giữ lại làm tài liệu tham khảo phòng khi có đội
nào tự dùng thêm ESP32 làm module phụ, nhưng **không phải** kiến trúc chính
thức cho Raspberry Pi.)

## Kiến trúc

```
[code thi sinh - bat ky ngon ngu]
        |  UDP JSON toi 127.0.0.1:8765 (chi ai_result: speed/steering/lane/obstacle/confidence)
        v
   carlogd.py  <-- chay nhu systemd service, user rieng "carlog"
        |            (thi sinh KHONG co quyen doc/sua/tat)
        |  tu dien: run_id, team_id, sequence_no, car_timestamp (dong bo NTP)
        |  nhip CO DINH 10ms, dung THANG protocol.py that cua du an
        v
  ingest_server.py (that, khong doi gi)  ->  Postgres  ->  backend  ->  frontend
        ^
        |  marshal go qua carlogctl.py (Unix socket rieng, thi sinh khong goi duoc)
   [trong tai mo/dong luot chay tren web admin]
```

Điểm mấu chốt cho **công bằng**: dù thí sinh có SSH/shell đầy đủ trên Pi, họ
không thể — vì bị chặn ở quyền file hệ điều hành (xem `provision/README.md`),
không phải chỉ "quy định miệng":

- Đổi `team_id` để gửi log dưới danh nghĩa đội khác (giá trị này nằm trong
  `config.py` thuộc sở hữu user `carlog`, thí sinh không có quyền ghi).
- Tự ý mở/đóng lượt chạy (`carlogctl.py start/stop` cần vào group `carlog`
  qua Unix socket 0660 — chỉ marshal có).
- Làm sai `sequence_no` hay gửi nhanh hơn/chậm hơn nhịp chuẩn — nhịp 10ms và
  bộ đếm này hoàn toàn nằm trong `carlogd.py`, thí sinh chỉ gửi "ý kiến" AI
  vào, không tự tay ghép gói tin.
- Giả timestamp — `car_timestamp` lấy từ đồng hồ hệ thống Pi (đã đồng bộ NTP
  qua `systemd-timesyncd`, cấu hình chuẩn của Linux), không phải giá trị
  thí sinh gửi lên.

## Bắt đầu từ đâu

1. **Lắp ráp/cấu hình 1 xe**: làm theo `provision/README.md` (tách user Linux,
   cài `carlogd` làm systemd service, cấu hình WiFi Enterprise bằng
   `provision/wpa_supplicant-example.conf`, bật NTP).
2. **Đưa cho thí sinh**: chỉ cần thư mục `sdk/` (hoặc copy đúng đoạn code gửi
   UDP vào code của họ) — xem `sdk/README.md`.
3. **Test không cần Pi/mạng thi đấu thật**: `test/run_local_test.py` tự dựng
   một "ingest giả" (decode bằng chính `protocol.py` thật của dự án), tự chạy
   `carlogd.py` thật, tự giả lập thí sinh gửi dữ liệu cà giật (không đúng
   nhịp) — đã chạy thử ngay khi viết bộ này: 256 gói trong ~4s, `sequence_no`
   liên tục tuyệt đối 0..255, `team_id`/`run_id` đúng 100%, JSON decode được
   bằng đúng hàm `protocol.decode()` của dự án.

   ```bash
   cd test
   python3 run_local_test.py --protocol-dir /duong/dan/toi/Car/simulator
   ```

## Vì sao chọn nhịp "server tự lấy giá trị mới nhất" thay vì bắt thí sinh gửi đúng 10ms

Thí sinh viết code bằng ngôn ngữ/tốc độ suy luận AI khác nhau (camera + CV có
thể chỉ suy luận được 15-30 lần/giây, không thể ép 100Hz). Nếu bắt thí sinh
tự đảm bảo đúng nhịp 10ms thì đội có AI nặng bị thiệt (mất gói, trông giống
"mạng yếu" trên dashboard dù mạng không hề yếu). Thiết kế ở đây tách hẳn hai
việc: thí sinh gửi kết quả AI *bất kỳ lúc nào họ có*, còn `carlogd` mới là
bên chịu trách nhiệm giữ nhịp 10ms gửi về server — lặp lại giá trị AI mới
nhất nếu thí sinh chưa kịp gửi cái mới. Nhờ vậy **mọi đội đều có cùng một
tần suất gói tin về server bất kể tốc độ AI nhanh/chậm** — chỉ tiêu chí công
bằng (thời gian hoàn thành, có phát hiện vật cản đúng lúc không...) mới phân
biệt được đội giỏi/dở, không phải do sai khác kỹ thuật gửi gói.
