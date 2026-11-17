# Làm rõ giao diện theo tham khảo VietQuant

Áp dụng nguyên tắc phân cấp nội dung và tính nhất quán từ các trang giới thiệu VietQuant vào giao diện ROMER đang có. Giữ các trang Tổng quan, Cảnh báo, Dữ liệu & cách dùng và nguồn SSI.

- Tăng chữ phụ, nhãn, thời điểm và chữ bảng; dùng cỡ chữ thống nhất cho tiêu đề, số chính và phần giải thích. Các điều khiển dùng chung màu theo chế độ sáng/tối, trạng thái chọn và focus bàn phím.
- Bốn thẻ tóm tắt có cùng nhịp bố cục, nhãn, số và mẫu số. Các chỉ tiêu tiếp tục có độ phủ riêng; không gộp mẫu số hoặc thay đổi phép tính.
- Khung doanh nghiệp gọn hơn, logo cạnh tên/mã, giữ ảnh và nguồn ảnh. Nút Thông tin doanh nghiệp mở phần hoạt động/website; ghi chú loại ảnh/trụ sở vẫn có trong phần nhận diện.
- Giá tham chiếu, trần, sàn thành ba cụm; mỗi giá giữ đơn vị đồng trên cùng dòng. Ngày của bộ tham chiếu vẫn ghi riêng, không đổi sang ngày giá đóng cửa khác.
- Chi tiết Cảnh báo có nhãn điều kiện và thời điểm, ưu tiên mức đáp ứng/số cổ phiếu còn thiếu hoặc chênh giá/ngưỡng. Thời gian ứng dụng quan sát được nằm trong phần thu gọn phía sau kết quả. Bảng giá và danh sách cảnh báo vẫn là bảng để so sánh nhiều mã.
- Hướng dẫn giữ ba bước có liên kết đến thao tác thực tế: Chọn cổ phiếu → Chỉnh số tiền → Đọc kết quả. Nội dung hướng dẫn không lặp thành một khối mới ở Tổng quan.
- Hiệu ứng ngắn chỉ dành cho hover/focus và thao tác điều hướng; tiếp tục tôn trọng tùy chọn giảm chuyển động. Cập nhật nguồn không được tự đóng phần người dùng đã mở.

CSS tập trung tại `src/app/static/product-polish.css`, được ghép sau các lớp cũ bằng `scripts/build_styles.py`. Các tệp nguồn khác chỉ thay đổi cách kết xuất nội dung. Không thêm yêu cầu SSI, trang đối tác, banner quảng bá hoặc mô hình dự báo.

Đã kiểm tra trực quan ở chế độ sáng/tối và khung nhìn điện thoại 390 px: không tràn ngang, ba cụm giá giữ liền đơn vị, nút thông tin doanh nghiệp mở/đóng đúng, thẻ tóm tắt cùng chiều cao. Chi tiết cảnh báo ưu tiên số liệu và thu gọn lịch sử quan sát. Kiểm tra hồi quy: 13 bộ kiểm tra JavaScript và 43 kiểm tra Python về sản phẩm/máy chủ đều đạt.

Tham khảo: [Trang chủ](https://vietquant.com/), [Luận điểm](https://vietquant.com/thesis), [Hợp tác](https://vietquant.com/partners), [Nghiên cứu](https://vietquant.com/research), [Góc nhìn](https://vietquant.com/insights).

Ngày 17/11/2026: Cổ phiếu, Sổ lệnh và Bảng giá chuyển thành ba tab chỉ hiện nội dung đang chọn. Giữ các bộ lọc, mã, tùy chọn biểu đồ và tab bên trong; liên kết `#chart`, `#cost` mở đúng tab trước khi đến vị trí chi tiết. Thanh điều hướng đánh dấu theo tab, không còn theo vị trí cuộn. Phát lại tạm dừng khi rời tab biểu đồ.

Các mục `details` và nút mở thông tin doanh nghiệp/Nâng cao dùng chung hiệu ứng chiều cao 220 ms. Có thể đảo chiều khi bấm liên tục, trả chiều cao về tự nhiên sau hiệu ứng để số liệu cập nhật không bị cắt. Tôn trọng `prefers-reduced-motion`; bàn phím và trạng thái đóng/mở vẫn hoạt động.

Kiểm tra cho thay đổi tab: 15 bộ JavaScript và 43 kiểm tra Python đạt. Trên trình duyệt đã kiểm tra các tab chỉ hiện một phần, giữ tìm kiếm và kiểu biểu đồ, phím trái/phải, lịch sử quay lại, hộp biểu đồ mở rộng, thu mở bằng Enter, nhập số tiền và mức chọn nhanh. Khung nhìn 390 px không tràn ngang; chế độ sáng/tối đều được kiểm tra.

Tiếp tục thu gọn tab Cổ phiếu: bỏ tiêu đề/mô tả lặp dưới thanh tab; thu khung doanh nghiệp, chuyển địa chỉ vào thông tin mở rộng và bỏ logo thứ hai trên ảnh trụ sở. Ảnh hoạt động vẫn giữ nhận diện doanh nghiệp theo quy ước có sẵn. Thống kê phiên và tỷ lệ khối lượng nằm chung một hàng; tỷ lệ dùng đúng nhãn so sánh cùng thời điểm hoặc cả phiên và giữ ngày riêng. Chi tiết mẫu so sánh, khối ngoại và nguồn thống kê chuyển vào Thông tin bổ sung dưới biểu đồ. Bốn thẻ thanh khoản chuyển nguyên sang Sổ lệnh, thêm mã đang xem ở tiêu đề. Bỏ sparkline trong tiêu đề đồ thị lớn, giữ các sparkline ở Bảng giá. Các chế độ biểu đồ, phát lại, công thức và dữ liệu không thay đổi.

Kiểm tra bản thu gọn: 15 bộ JavaScript và 43 kiểm tra Python đạt; đã xem sáng/tối và điện thoại 390 px. Giữ ngày khối ngoại riêng với ngày giá và mốc so sánh khối lượng, mở được toàn bộ chi tiết, bốn thẻ phản hồi ngay khi chọn lại số tiền. Ở khung nhìn máy tính 1265 px, ví dụ FPT có khung doanh nghiệp cao 281 px và biểu đồ bắt đầu khoảng 445 px từ đầu nội dung tab.

Điều chỉnh theo ngữ cảnh: tóm tắt toàn phạm vi chỉ nằm trong Bảng giá, phía trước lựa chọn cổ phiếu/theo ngành; rút lời giải thích thành số đếm/mẫu số riêng và ngưỡng. Thanh trạng thái chung giữ trạng thái kết nối và tự cập nhật; giá, sổ và tóm tắt tiếp tục ghi thời điểm tại từng phần. Khối lượng so sánh mở ngay tại tỷ lệ, cho xem hai lượng và mốc so sánh; phương pháp chi tiết/nguồn chuyển vào ví dụ trong Hướng dẫn. Khối ngoại thành thẻ riêng dưới biểu đồ, mặc định hiện mua ròng và phiên, mở rộng mới hiện mua/bán/room ngoại còn lại. Bỏ khung Thông tin bổ sung chung. Chỉ rút ngày tham chiếu trùng lặp khi ngày giá thực tế được xác nhận là cùng ngày; dữ liệu khác phiên luôn ghi rõ.

Kiểm tra cho bố cục theo ngữ cảnh: 15 bộ JavaScript và 43 kiểm tra Python đạt. Trình duyệt đã xác nhận thẻ tóm tắt lọc đúng Bảng giá từ cả chế độ Theo ngành, nút xuất HTML vẫn sẵn sàng khi có dữ liệu, cửa sổ khối lượng đóng bằng Esc/bấm ngoài và dẫn đúng Hướng dẫn, thẻ Khối ngoại mở bằng bàn phím. Kiểm tra sáng/tối và 390 px không tràn ngang; cửa sổ khối lượng nằm trong lề 16 px. Các mẫu số thay đổi theo từng chỉ tiêu khi dữ liệu SSI cập nhật, giữ được phiên khối ngoại cũ hơn ngày giá.
