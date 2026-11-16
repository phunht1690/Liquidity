# Kiến trúc SSI hiện hành

SSI HTTPS auth và danh sách mã → một worker WebSocket chỉ đọc → chuẩn hóa quote/trade → SQLite sự kiện và ảnh trạng thái → chỉ báo thanh khoản/áp lực → máy chủ cục bộ → HTML ROMER.

Máy chủ `src/app/server.py` khởi động supervisor `src/data/ssi_runtime.py`, tạo worker `ssi_worker.py`. Worker dùng `SSISession` trong `ssi_feed.py` để duy trì một kết nối market stream. Trình duyệt không biết key/token và không gọi SSI trực tiếp. Mọi tab chia sẻ bộ thu; SSE chỉ thông báo phiên bản cache cục bộ.

REST tải thành phần VN30/VN100, danh mục cổ phiếu HOSE/HNX/UPCoM và master data mỗi ngày. Cấu hình `universe_group=ALL` lấy toàn bộ cổ phiếu hợp lệ, bỏ giới hạn 15 mã của chế độ thử nghiệm. WebSocket nhận quote/trade theo mã, chỉ kênh DATA; đăng ký theo lô tối đa 100 topic. Ngày 15/11/2026 SSI chấp nhận 31/31 lô, tổng 3.035 topic cho 1.517 mã và market.flag. Đây là xác nhận đăng ký, chưa phải bằng chứng đã nhận giao dịch trong ngày nghỉ. Lưu ảnh khoảng 5 giây trong giờ hoặc 30 giây ngoài giờ. Bộ thu có heartbeat, watchdog, giãn nhịp sau lỗi, tự refresh token và nối lại. Lưu lại sau khởi động không làm timestamp nguồn mới lên.

Lớp tài chính giữ công thức độc lập nguồn. `live_analytics.py` kiểm tra chất lượng/pha/độ mới, kể cả timestamp nguồn đi vào đấu giá trước giờ nhận. `product.py` tạo payload `/api/product` cho giao diện: chênh giá, giá trị chờ, tỷ lệ tổng lượng chờ ba mức và quét sổ cho N. Không đưa điểm LQS hoặc mô hình chưa hiệu chuẩn vào giao diện. `/api/state` và các công thức cũ còn giữ cho tương thích nội bộ và kiểm thử.

Khi đủ điều kiện liên tục, sổ hiện hành dùng để phân tích. Ngoài giờ hoặc mất kết nối, `product.py` tìm ảnh sổ SSI hợp lệ đã lưu, giữ riêng thời điểm phân tích và thời điểm giao dịch gần nhất. Không gọi ảnh lưu là sổ có thể giao dịch ngay. CSV `/api/product/export.csv` giữ hai dataset/thời điểm và kiểm tra dataset trước khi xuất. `chart_archive.py` chỉ đọc các ảnh SSI để phát lại riêng biểu đồ; không thay toàn cục trạng thái sản phẩm.

Thành phần chỉ số được kiểm tra số mã, sàn và loại chứng khoán. Nếu REST trả sai hình dạng nhưng còn danh sách SSI đã xác nhận, dùng danh sách đó kèm cảnh báo nguồn; không tạo thành phần rổ. Master data lỗi có thể thử lại, không ngăn WebSocket cập nhật giá. Nguồn cũ không có đường gọi trong ứng dụng hiện hành.
