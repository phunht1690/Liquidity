# Chạy nền và tải bù giá

Mở `start.bat` hoặc `start.ps1` để mở dashboard. Máy chủ và bộ thu được chạy ẩn, độc lập với cửa sổ khởi động và tab trình duyệt. Mở nhiều lần vẫn dùng một bộ chạy nền cho thư mục này. Host dùng khóa hệ điều hành, kiểm tra máy chủ và khởi động lại máy chủ do nó quản lý nếu tiến trình bị ngắt. Kết nối WebSocket vẫn do một bộ thu SSI phụ trách.

Tự khởi động Windows được đăng ký cho tài khoản người dùng hiện tại tại `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`, tên `LOPM SSI Collector`. Chạy sau khi đăng nhập; không cần mật khẩu, quyền quản trị hoặc mở trình duyệt. Đường dẫn chỉ chứa Python, script và cổng. Token và key tiếp tục chỉ đọc từ `.env` tại máy chủ. Không có dịch vụ giao dịch hay tài khoản được gọi.

Có thể quản lý từ PowerShell tại thư mục dự án:

```powershell
.\manage_background.ps1 -Action Status
.\manage_background.ps1 -Action Start
.\manage_background.ps1 -Action Stop
.\manage_background.ps1 -Action DisableAutostart
.\manage_background.ps1 -Action EnableAutostart
```

`Stop` dừng host và máy chủ do host khởi tạo; không tự gỡ đăng ký khởi động sau lần đăng nhập tiếp theo. `DisableAutostart` chỉ gỡ cấu hình của đúng thư mục này, không dừng phiên đang thu. Một máy chủ đã được chạy riêng trong terminal không bị kết thúc qua PID lưu cũ. Để kiểm tra trực tiếp trong terminal, dùng `python -m src.app.launcher --foreground` khi bộ chạy nền đã dừng.

## Khi máy chủ chạy

1. Máy chủ phục vụ dữ liệu đã lưu ngay, khởi động bộ thu và kết nối luồng SSI hiện tại.
2. Sau khoảng 10 giây, tác vụ lịch sử đọc danh mục và kiểm tra khoảng 30 ngày lịch tính từ hôm nay. Ngày kết thúc ưu tiên ngày giao dịch SSI đã ghi nhận. Nếu mới có danh mục và chưa nhận bản tin giao dịch, vẫn yêu cầu OHLC đến ngày trong tuần gần nhất, không phải chờ thị trường mở lại. Ngày yêu cầu không được coi là bằng chứng đã giao dịch; chỉ nến thực sự nhận được mới được lưu thành dữ liệu giá.
3. Tải bù nến 5 phút và nến ngày qua API OHLC, cho toàn bộ mã bộ thu đang theo dõi. FPT/mã đang xem và VN30 được ưu tiên trước các mã còn lại. Một lượt đầu cho cả danh mục cần thời gian; giao diện và bảng giá không chờ tải xong.
4. Lưu vào `data/ssi/price_bars.sqlite3` theo khóa `(symbol, timeframe, timestamp)`. Cập nhật nến cùng khóa thay vì nhân bản. Lần mở sau đọc các ngày đã kiểm tra và chỉ bổ sung khoảng còn thiếu. Ngày hiện tại được kiểm tra lại; ngày rỗng còn gần được thử lại sau 6 giờ để tránh bỏ lỡ dữ liệu công bố muộn. Khi ngày đã cách hiện tại ít nhất 3 ngày và có phản hồi rỗng đầy đủ, giữ kết quả này để không tải lại hàng nghìn ngày nghỉ trong mỗi lượt.
5. Kho nến tự dọn ngoài 30 ngày lịch. Phản hồi thiếu trang hoặc có bản ghi không hợp lệ không được đánh dấu đủ cả ngày. Không tự nội suy nến bị thiếu.

Các yêu cầu OHLC chia sẻ một khách hàng và một lượt gọi tại một thời điểm, giãn ít nhất 1 giây giữa các lượt. Yêu cầu biểu đồ người dùng được ưu tiên trước trang tải bù tiếp theo. HTTP 429 và lỗi quyền truy cập áp dụng thời gian chờ chung, không đổi key để vượt giới hạn. Luồng giá hiện tại ở tiến trình thu riêng, không chờ hàng đợi lịch sử.

Khi chọn nến 5 phút hoặc ngày trong khoảng đã có, biểu đồ đọc kho nến ngay. Các đơn vị nến khác hoặc khoảng dài hơn được lấy khi chọn và vẫn dùng cache bộ lọc hiện có (tối đa 128 bộ lọc). Kho không cam kết mọi mã đều giao dịch mỗi ngày. Trang Dữ liệu & cách dùng cho biết số nến, số mã có nến, số mã đã kiểm tra, khoảng ngày, dung lượng và trạng thái chạy nền.

Giá/khối lượng và mở/cao/thấp từ nến ngày hoàn tất còn được dùng làm dữ liệu dự phòng cho Tổng quan và Bảng giá. Không dùng nến đang hình thành làm giá đóng cửa, không ghi đè giao dịch của ngày mới hơn và không dùng `value` của OHLC như giá trị khớp thực. Giá trị khớp vẫn lấy từ SSI tổng hợp ngày.

Các khóa `ssi` trong cấu hình: `auto_price_backfill=true`, `price_history_retention_days=30`, `history_request_interval_seconds=1`.

## Điều kiện và giới hạn

Máy cần bật, không ngủ và có mạng để ghi trực tiếp sổ lệnh/giao dịch. Tắt hoặc ngủ máy làm ngừng thu. Khi bật lại, giá/khối lượng theo nến có thể được lấy bù từ SSI; lịch sử sổ lệnh, các giao dịch chi tiết và cảnh báo trong lúc không thu không được dựng lại từ nến.

Kho nến, kho Phát lại sổ lệnh (30 ngày) và kho bản tin gốc (tối đa 7 ngày, 2.048 MB) độc lập. Nến tải bù không được chèn thành ảnh sổ lệnh hoặc lịch sử cảnh báo. Ngoài giờ hoặc sau nhiều ngày nghỉ, Tổng quan tìm một ảnh sổ hợp lệ của phiên gần nhất đã thu, với ngày giờ rõ ràng.

Log host và máy chủ ở `data/logs`, mỗi loại tối đa ba tệp 1 MB, không lưu nội dung xác thực. Không đổi thiết lập ngủ máy hoặc mở cổng ra Internet. Nếu muốn ghi trong lúc máy cá nhân tắt, cần triển khai bộ thu trên máy chủ luôn bật riêng.

Nguồn: [SSI OHLC](https://developers.ssi.com.vn/en/docs/api-reference/data-ohlc), [SSI WebSocket](https://developers.ssi.com.vn/docs/faq/websocket).
