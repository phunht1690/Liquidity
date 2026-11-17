# Khôi phục kết nối SSI — 17/11/2026

Sự cố nằm ở tiến trình web chạy trên máy. Bộ thu đã dừng sau một lần nhận HTTP 200; không ghi nhận lỗi xác thực. Tiến trình web tăng từ khoảng 1,8 GB lên hơn 5 GB bộ nhớ và có hơn 110 luồng. Thử riêng bằng bộ xác thực trong `.env` vẫn đăng nhập thành công và nhận đủ 30 mã VN30 từ SSI. Không thay khóa hoặc quyền API.

Các đường đọc lịch sử trước đây có thể chạy chồng khi mở nhiều tab hoặc tải lại. Nhiều đoạn dùng `with sqlite3.connect(...)` để kết thúc giao dịch, nhưng cách này không đóng kết nối; tài nguyên native chỉ được giải phóng khi kết nối được thu dọn. Đã sửa hai giới hạn tài nguyên này:

- Dùng một lớp giao dịch SQLite tự commit/rollback và luôn đóng kết nối ở phần kết thúc, cho các kho SSI/cache đang hoạt động. Không đổi lược đồ, phép tính hoặc nội dung dữ liệu đã lưu.
- Gộp các lượt đọc giống nhau và giới hạn hai truy vấn nặng đồng thời cho sản phẩm, độ phủ và phát lại. Bộ đệm tối đa sáu kết quả, tối đa hai giây; bản SSI mới đổi dấu nhận diện tệp và làm mất hiệu lực kết quả cũ. Health, SSE và nến giá có đường xử lý riêng.
- Nếu ứng dụng đang hết chỗ xử lý, trả trạng thái chờ cục bộ có giới hạn; không tạo thêm một truy vấn nặng và không coi đó là lỗi quyền SSI.

Đã dừng đúng bộ chạy nền đang sở hữu máy chủ, triển khai bản sửa và mở lại bằng launcher nền. Bộ thu mới xác thực, kết nối WebSocket và tiếp tục ghi các bản dữ liệu mới. Giao diện và khóa trong `.env` được giữ nguyên; không xóa kho dữ liệu.

Kiểm tra:

- Toàn bộ **429 kiểm tra Python đạt**, gồm kiểm tra gộp truy vấn, giới hạn đồng thời, hết hạn/đổi bản dữ liệu và đóng kết nối khi commit hoặc rollback.
- Tám lượt HTTP đồng thời tới sản phẩm đều trả 200, thời gian cao nhất khoảng 2,25 giây trong lần kiểm tra. Dữ liệu nguồn `ssi_fastconnect`, sổ ở chế độ `live` và thời điểm nhận mới sau khi khởi động lại.
- Sau khi chạy lại và phục vụ yêu cầu thực tế, bộ nhớ web khoảng 190–200 MB trong các lần đo, thay cho hơn 5 GB trước đó. Đây là số đo tại thời điểm kiểm tra; mức dùng còn phụ thuộc phạm vi và truy vấn đang chạy.

Chẩn đoán không ghi khóa, token, nội dung xác thực hoặc dữ liệu tài khoản vào tài liệu này. Chỉ dùng API dữ liệu thị trường.
