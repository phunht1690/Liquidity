# Kiểm tra số tiền trên sổ lệnh

Phần **Số tiền muốn kiểm tra** nằm ngay trên bảng kết quả mua/bán và biểu đồ chênh giá theo quy mô, trong **Tổng quan → Sổ lệnh & quy mô**. Trang Cảnh báo dùng cùng điều khiển phía trên các thẻ thống kê; số tiền được giữ khi chuyển trang. Thẻ đáp ứng ở đầu Tổng quan ghi số tiền đang dùng và có liên kết Điều chỉnh.

Người dùng kéo thanh, nhập số tiền theo triệu đồng, hoặc chọn nhanh 100 triệu / 500 triệu / 1 tỷ / 2 tỷ / 5 tỷ. Khoảng được hỗ trợ vẫn là 100 triệu đến 5 tỷ đồng, theo từng triệu đồng. Không có bước bấm Áp dụng.

Kết quả mua/bán, tỷ lệ đáp ứng, số cổ phiếu, đường đánh dấu trên biểu đồ quy mô và điều kiện Cảnh báo được tính ngay từ chính sổ đã xác nhận trên màn hình. Giá, lượng đã khớp và các thời điểm nguồn giữ nguyên. Yêu cầu máy chủ được gộp sau khi người dùng ngừng điều chỉnh 170 ms để cập nhật bản mới và lịch sử điều kiện đúng số tiền. Bản phản hồi cũ bị bỏ qua khi người dùng thay đổi tiếp. Xuất CSV chờ phản hồi tương ứng từ máy chủ để tránh dùng mã bộ dữ liệu của số tiền trước.

Quy đổi số tiền theo giá giữa (hoặc giá khớp/tham chiếu đã được máy chủ xác nhận khi sổ một phía), làm tròn xuống theo lô. Nếu mua, đối chiếu tối đa ba mức chờ bán; nếu bán, đối chiếu ba mức chờ mua. Giá bình quân chỉ tính trên phần có đối ứng, không ngoại suy phần còn thiếu. Số tiền có đối ứng có thể khác số tiền kiểm tra.

Khi chưa có sổ đủ dữ liệu, điều khiển bị vô hiệu hóa. Mã không có sổ hợp lệ không được suy thành đáp ứng 0%. Lịch sử ghi nhận của số tiền cũ không được mang sang số tiền mới; ảnh sổ đã lưu vẫn ghi rõ thời điểm và không được đổi nhãn thành dữ liệu trực tiếp.
