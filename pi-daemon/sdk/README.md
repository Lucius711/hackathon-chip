# SDK gửi kết quả AI — cho thí sinh

Xe của bạn đã có sẵn một dịch vụ nền (`carlogd`) lo toàn bộ phần kết nối mạng
thi đấu, `run_id`, `team_id`, số thứ tự gói, đồng bộ giờ, gửi log về đúng
database. **Bạn không cần và không được đụng vào phần đó.**

Việc duy nhất code của bạn cần làm: mỗi khi có một kết quả suy luận AI mới
(dò làn, tránh vật cản...), gửi nó dưới dạng **JSON qua UDP tới cổng nội bộ
`127.0.0.1:8765`** (đổi số cổng nếu ban tổ chức thông báo khác). Không cần bắt
tay, không cần chờ phản hồi, không cần xử lý lỗi phức tạp — bắn UDP là xong,
gửi càng đều càng tốt nhưng gửi không đều/gửi chậm cũng không sao (dịch vụ nền
sẽ tự lặp lại giá trị cũ nếu bạn gửi chưa kịp).

Định dạng JSON — bắt buộc đủ 5 trường, `progress` tuỳ chọn:

```json
{
  "speed_kmh": 25.0,
  "steering_deg": -8.5,
  "lane_offset_cm": 3.2,
  "obstacle": false,
  "confidence": 0.92
}
```

Không gửi `run_id`, `team_id`, `sequence_no`, timestamp — những trường đó do
`carlogd` tự điền, gửi vào JSON của bạn (nếu có) sẽ bị bỏ qua.

Có sẵn ví dụ bằng Python và C trong thư mục này — copy đoạn gửi vào code lái
xe của bạn, ngôn ngữ khác cứ theo đúng nguyên tắc "UDP tới 127.0.0.1:8765,
nội dung là JSON như trên" là chạy được, không phụ thuộc ngôn ngữ nào cả.
