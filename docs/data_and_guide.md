# Dữ liệu & cách dùng

Trang giữ thiết kế ROMER, có hai lựa chọn nội bộ:

- **Dữ liệu** (`#data`): bộ chọn Phạm vi đặt ngay tại Độ phủ dữ liệu, ba chỉ tiêu độ phủ, tóm tắt kho trên máy và năm nhóm nguồn. Các mốc thời gian, ngày đã lưu, chi tiết bộ thu và bảng nguồn đầy đủ mặc định thu gọn.
- **Hướng dẫn** (`#how-it-works`): giới thiệu một câu, ba bước có liên kết thao tác và bốn chỉ tiêu đọc nhanh. Ví dụ theo mã/số tiền, trạng thái, Cảnh báo, biểu đồ và xuất file nằm trong các mục mở rộng.

Trang Dữ liệu không hiển thị bộ lọc Ngành, Cổ phiếu hoặc CSV của Tổng quan. Phạm vi riêng được lưu trong trình duyệt, không đổi ngành, mã hay số tiền đang theo dõi. Độ phủ luôn tính cho toàn bộ ngành của phạm vi đó. Hướng dẫn không có bộ chọn dữ liệu. Chọn hai tab cập nhật hash, hỗ trợ bàn phím; mở liên kết trực tiếp hoặc quay lại lịch sử phải hiện đúng panel trước khi cuộn. `#data-fields` mở phần Nguồn dữ liệu; `#data-off-hours` còn mở sẵn chi tiết lưu trữ.

Xuất tóm tắt HTML chỉ còn ở Tổng quan; thông báo tải thành công cũng ở đó. Bỏ khung xuất trùng và nút in khỏi trang Dữ liệu. Các phép tính, giới hạn lưu trữ và nguồn SSI không đổi. `/api/data-coverage` chỉ nhận `universe`, dùng ảnh SSI và các kho giá sẵn có, không xếp thêm yêu cầu SSI cho thống kê/ngày/đường giá. Khi phần Dữ liệu đang mở, trình duyệt tự đồng bộ với máy chủ cục bộ khoảng 5 giây/lần; một yêu cầu mỗi lần, bỏ phản hồi cũ khi đổi phạm vi và dừng khi panel/tab ẩn. Không mở thêm kết nối nguồn thị trường.

Thanh trạng thái riêng ghi nguồn SSI, thời điểm ảnh sổ và bản thị trường đã ghi nhận; không đưa thời điểm giá của một cổ phiếu vào số liệu toàn phạm vi. Ví dụ ở Hướng dẫn vẫn lấy mã, số tiền và ảnh sổ của Tổng quan, có ghi rõ ngữ cảnh đó.

Ba thẻ độ phủ vẫn có vai trò riêng: số mã đã có giá, đã có bản tin sổ lệnh, và đủ điều kiện tính trên ảnh đang đối chiếu. Trạng thái kết nối không được dùng thay cho thời điểm thị trường. Dữ liệu chưa biết giữ `_`, số 0 xác nhận được giữ nguyên. Hướng dẫn phân biệt rõ tải bù nến với sổ lệnh/giao dịch chỉ được thu khi bộ thu chạy.

Bảng nguồn mở rộng ghi thêm tối đa 10 mức thực nhận, bình quân phiên SSI đã ghi, so sánh khối lượng cùng giờ 20 phiên, khối ngoại theo số cổ phiếu, trần/sàn và tổng hợp khớp lệnh/thỏa thuận theo đúng ngày. Chỉ mô tả nơi xem trong Tổng quan, không lặp các bảng kết quả. `/api/data-coverage` tiếp tục không khởi động bộ lấy tổng hợp thị trường hoặc yêu cầu thống kê ngày mới.
