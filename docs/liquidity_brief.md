# Tóm tắt thanh khoản, ngành và bản xuất HTML

Bản cập nhật giữ thiết kế ROMER và nguồn SSI hiện có, bổ sung bốn chức năng:

1. Tóm tắt trong Tổng quan: số mã có sổ đối chiếu, số mã chênh giá vượt ngưỡng, số mã chưa đủ lượng chờ và chênh giá trung vị.
2. Hai lựa chọn Bảng giá / Theo ngành, mỗi lần hiện một bảng. So sánh ngành gồm độ phủ sổ, trung vị chênh giá/độ dày, tỷ lệ đáp ứng quy mô ở hai phía và giá trị khớp thật của các mã cùng phiên tổng hợp. Mỗi chỉ tiêu có mẫu số riêng; giá trị khớp ghi ngày riêng và có cách sắp xếp riêng. Mặc định hiện sáu ngành; có thể mở toàn bộ, đổi cách sắp xếp, bấm ngành để chuyển sang bảng giá đã lọc.
3. Danh sách lọc thanh khoản có số lượng từng lựa chọn, kết hợp tìm kiếm, danh sách theo dõi, phân trang và CSV. CSV giữ đúng các mã phù hợp trên mọi trang.
4. Xuất bản tóm tắt HTML ở Tổng quan. File chứa toàn bộ ngành, mã cần kiểm tra và bảng số liệu đầy đủ trong phần mở rộng. File độc lập, không có JavaScript hoặc tài nguyên ngoài, không gọi API khi mở. Dữ liệu & cách dùng chỉ hướng dẫn cách xuất, không lặp khung xuất.

Các thống kê dùng phạm vi và ngành đang chọn. Bộ lọc nhanh, tìm kiếm và theo dõi áp dụng riêng cho Bảng giá; bản tóm tắt HTML ghi toàn bộ phạm vi/ngành. Thay đổi số tiền tính lại tóm tắt, tỷ lệ theo ngành và bộ lọc ngay từ sổ đã được máy chủ xác nhận, sau đó đồng bộ với máy chủ. Chờ đồng bộ xong mới xuất HTML.

Mỗi chỉ tiêu có mẫu số riêng. Chỉ dùng sổ hợp lệ thuộc cùng ảnh đối chiếu; chỉ tính trung vị trên giá trị xác định. Giá trị 0 đã biết được giữ, dữ liệu thiếu không chuyển thành 0. Sổ một phía có thể xác định thiếu lượng chờ nhưng không có chênh mua–bán. Hai tỷ lệ đáp ứng phải xác định mới đánh giá đủ quy mô ở hai phía. Trung vị là mức ở giữa các mã có dữ liệu, mỗi mã có trọng số như nhau.

File HTML giữ riêng thời điểm tạo báo cáo, thời điểm ảnh sổ và ngày của giá từng mã. Xuất lúc thị trường nghỉ không làm mới thời điểm sổ. Những mã chưa có dữ liệu vẫn giữ dấu `_`. Bản tin không suy luận danh tính người giao dịch, đưa điểm mua/bán hay dự báo xác suất.

Bản 16/11 bổ sung mục thu gọn khớp lệnh/thỏa thuận toàn sàn và chỉ số trong Tổng quan, cùng bảng tương ứng trong bản xuất HTML. Các dòng ghi đúng phiên SSI cung cấp, không cộng chỉ số với sàn. Tất cả chỉ tiêu sổ dùng tối đa 10 mức thực nhận; ảnh cũ 3 mức giữ đúng phạm vi cũ. Xem `liquidity_extensions.md`.

Đã kiểm tra chéo với Cảnh báo trên dữ liệu SSI thật của VN30, HOSE, HNX và UPCoM, gồm thay đổi số tiền. Kiểm thử mô hình bao phủ mẫu số theo chỉ tiêu, sổ một phía, dữ liệu thiếu/0, sổ khác thời điểm, tính theo ngành, tính lại quy mô và HTML an toàn. Đã thử tải HTML 30 mã và CSV đúng một mã sau khi kết hợp bộ lọc nhanh với tìm kiếm.

Lần kiểm tra ngày 15/11/2026: 406 kiểm thử Python và 9 nhóm JavaScript đạt. Trình xem trước chặn giao thức `file://`; file HTML tải xuống được kiểm tra cấu trúc/số liệu trực tiếp trên máy, dashboard được kiểm tra trực quan qua HTTP cục bộ.

Lần kiểm tra trên xác minh bố cục máy tính sáng/tối của bản ngày 15/11; chưa xác minh trực quan các thay đổi bố cục sau đó hoặc màn hình hẹp. Bản tách Dữ liệu / Hướng dẫn có kiểm tra cấu trúc HTML, kết xuất và liên kết panel; xem `data_and_guide.md`.
