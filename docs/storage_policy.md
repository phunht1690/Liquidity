# Lưu dữ liệu và Phát lại

| Kho | Thời hạn | Ngân sách |
| --- | --- | --- |
| Giá và sổ lệnh Phát lại | 30 ngày lịch, gồm cuối tuần/ngày lễ | Tùy số mã và mức độ thay đổi |
| Bản tin gốc quote/trade | Tối đa 7 ngày lịch | 2.048 MB; có thể dọn ngày cũ sớm hơn khi đầy |
| Lịch sử điều kiện thanh khoản | Theo cùng cửa sổ 30 ngày | Lưu riêng với bản tin gốc |
| Nến giá tải bù 5 phút và ngày | 30 ngày lịch | Một nến/mã/thời điểm; kho riêng, nhẹ hơn ảnh sổ |

Hai kho độc lập: dọn bản tin gốc không xóa ảnh sổ Phát lại. Ảnh mỗi ngày có điểm khởi đầu riêng, nên dữ liệu còn trong hạn không phụ thuộc vào ngày đã hết hạn. Khi xóa ngày Phát lại cũ, phần mô tả không còn tham chiếu cũng được dọn. Bản tin gốc được kiểm tra hết hạn định kỳ khi bộ thu còn chạy, kể cả lúc không có bản tin mới. Không tự xóa bản tin đầu ngày đang ghi để tiếp tục nhét thêm dữ liệu; trạng thái tạm dừng ghi được thể hiện trong trang Dữ liệu.

Ngày mặc định của Phát lại là ngày gần nhất có giá thực sự được ghi nhận cho mã đang xem. Ảnh kiểm tra kết nối vào cuối tuần hoặc ngày chưa có giá không thay thế phiên này. Không suy luận ngày nghỉ chỉ theo thứ trong tuần: ngày trong tuần chưa có giá cũng được bỏ qua khi tự chọn. Yêu cầu chọn ngày cụ thể vẫn được tôn trọng; giao diện ghi rõ khi ngày đó chưa có dữ liệu cho nội dung đang xem.

Các khóa cấu hình nằm trong `config/config.json`, mục `ssi`: `history_retention_days=30`, `raw_archive_retention_days=7`, `raw_archive_max_mb=2048`. `/api/health` và `/api/product` cung cấp chính sách hiện hành cho giao diện. Mọi thời hạn dùng ngày lịch tại Việt Nam, không phải số phiên giao dịch.

Phép đo dữ liệu đã thu ngày 13/11/2026 cho 439 mã cho kết quả khoảng 246 MB ảnh giá/sổ và 306 MB bản tin gốc, gồm chỉ mục lưu trữ. Đây là mẫu của phạm vi cũ. Từ 15/11/2026 theo dõi 1.517 mã: ngoại suy tuyến tính ảnh giá/sổ khoảng 850 MB/phiên, tương đương 17–19 GB cho 20–22 phiên, cộng kho gốc tối đa 2 GB, kho nến và dự phòng. Có thể dự trù 20–30 GB cho 30 ngày lịch; đây là ước lượng, cần đo lại sau phiên thật với đủ ba sàn. Không nhân ngân sách bản tin gốc theo số mã: giới hạn 2.048 MB vẫn áp dụng chung, nên kho gốc có thể giữ ít ngày hơn khi nhiều bản tin.

Kho được lưu trên máy. Để có Phát lại sổ lệnh chi tiết, bộ thu phải chạy trong khoảng giao dịch muốn lưu. Nến giá lịch sử không tái tạo được toàn bộ trạng thái sổ lệnh chưa từng thu. SQLite có thể tái sử dụng phần trống sau khi dọn dữ liệu; dung lượng tệp không nhất thiết giảm ngay. Không tự chạy VACUUM hoặc chuyển đổi kho cũ trong lần thay đổi này.

Bộ chạy nền và tự khởi động sau đăng nhập giúp tiếp tục thu khi đóng tab dashboard. Tác vụ tải bù tự kiểm tra phần giá còn thiếu, ghi vào `price_bars.sqlite3`; không đưa nến vào kho ảnh sổ. Dung lượng kho nến thực tế hiển thị tại Dữ liệu & cách dùng. Xem [cách chạy nền và tải bù](background_collection.md).
