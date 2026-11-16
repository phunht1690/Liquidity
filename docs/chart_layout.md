# Cách dùng biểu đồ sau khi thu gọn tùy chọn nâng cao

Giữ thiết kế ROMER, nguồn SSI và tương tác biểu đồ hiện có. Bản thường và Mở rộng dùng một bộ điều khiển, một lựa chọn khoảng và một tập đường đang hiển thị.

- Hàng thao tác nhanh giữ Theo dõi/Phát lại, Nội dung và Khoảng xem. Với lượng chờ, hiện Phiên sổ lệnh và khoảng chọn nhanh tương ứng. Chọn ngày tùy ý hiện ô Từ/Đến ngay bên ngoài Nâng cao; các trường này vẫn dùng được khi tùy chọn nâng cao đóng.
- Nút **Nâng cao** đặt ngay cạnh Khoảng xem ở cả hai chế độ, mặc định đóng. Bên trong gồm Kiểu biểu đồ, Mỗi nến/điểm, Chọn đoạn/Kéo ngang và các đường bổ trợ. Bấm Mở rộng hoặc Thu nhỏ giữ nguyên trạng thái tùy chọn nâng cao, giá trị đã chọn và khoảng đang phóng to. Thay đổi kích thước không tải lại dữ liệu. Đóng bằng nút Thu nhỏ hoặc Esc đều giấu đồ thị tổng trở lại; đoạn đã chọn vẫn áp dụng cho biểu đồ thường.
- Biểu đồ giá mặc định có giá, khối lượng và tham chiếu khi có dữ liệu. BQ phiên SSI, MA20 và MA50 mặc định tắt; người dùng vẫn có thể bật tất cả. MA có tooltip ghi số nến và độ chia đang dùng. Biểu đồ lượng chờ giữ mặc định chênh giá và độ dày, có thể thêm mua/bán trong Nâng cao.
- Gộp mã, đường nhỏ, tỷ lệ thay đổi và thông tin nến trong cùng vùng tiêu đề. Khoảng đang xem ghi ngày một lần; số điểm/tổng chỉ hiện thêm khi đang cắt đoạn. Đồ thị tổng chỉ hiện trong Mở rộng để kéo chọn; khoảng nhiều ngày hiện ngày ở hai đầu, nến ngày không dùng nhãn 00:00.
- Giữ nhóm +/− nhỏ và nút Toàn khoảng chỉ khi đã thu phóng. Chọn đoạn/Kéo ngang chuyển vào Nâng cao; thao tác kéo chọn trên đồ thị tổng, con trỏ, ghim, cuộn Ctrl và bàn phím tiếp tục hoạt động.
- Bỏ đoạn mô tả dài dưới đồ thị tổng và hướng dẫn thường trực cạnh công cụ. Dòng trạng thái ngắn vẫn ghi lần đồng bộ/ảnh sổ, có ghi “Một phần khoảng chọn” nếu nguồn xác nhận chưa đủ khoảng. Chi tiết nguồn, phiên, lần đồng bộ, số mốc BQ và giới hạn Phát lại nằm trong **Nâng cao → Nguồn & tình trạng dữ liệu**. Khoảng thiếu mẫu tiếp tục để trống.

Kiểm tra chức năng bằng các nhóm JavaScript, gồm chọn đoạn/đặt lại, trạng thái thu gọn và Mở rộng, thay đổi nội dung, chọn ngày và Phát lại. Kiểm tra cấu trúc HTML để xác nhận điều khiển không trùng và ngày tùy chọn không bị giấu trong Nâng cao. Bố cục mới chưa được xác minh trực quan trong trình duyệt.

Ô chọn, nút chuyển chế độ, Nâng cao và checkbox dùng màu nền/chữ/viền theo giao diện sáng/tối của app. MA chưa đủ số nến bị vô hiệu hóa và có tooltip ghi rõ số nến đang có.
