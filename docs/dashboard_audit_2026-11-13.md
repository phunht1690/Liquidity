# Rà soát dashboard ngày 13/11/2026

## Cập nhật tự động

Đã bỏ nút Cập nhật trong thanh trạng thái, thay bằng nhãn Tự cập nhật. Dashboard nhận thông báo thay đổi và định kỳ đọc lại bộ dữ liệu cục bộ. Khi kênh thông báo ngắt, cơ chế định kỳ tiếp tục hoạt động; bản thân lỗi kênh thông báo không còn bị coi là mất dữ liệu. Kết nối được thử lại tự động.

Nhãn trạng thái phân biệt sổ trong phiên, dữ liệu phiên gần nhất và lỗi kết nối thật. Đồng hồ tạm dừng của tab nền không làm dữ liệu phiên đã lưu bị đổi thành thông báo Chưa nhận bản mới. Khi quay lại tab, ứng dụng đồng bộ ngay nếu không có yêu cầu đang chạy.

## Các sửa đổi chức năng

- Bộ lọc ngành giới hạn cả danh sách chọn cổ phiếu và bảng giá. Nếu mã đang xem nằm ngoài ngành mới, ứng dụng chuyển sang mã phù hợp; không giữ biểu đồ của ngành cũ.
- Khi đổi phạm vi, các bộ chọn phụ chờ danh mục tương ứng, thay vì cho chọn nhầm mã của sàn/rổ trước.
- Phát lại: đổi ngày sẽ tải lại danh mục đúng ngày đó; không mang mã hoặc phạm vi chưa tồn tại sang kho cũ. Khi đọc kho lỗi, các bộ chọn vẫn có thể sử dụng để khôi phục.
- Biểu đồ khoảng ngắn: dùng cuối phiên 14:45 cho HOSE và 15:00 cho HNX/UPCoM, tránh cắt 15 phút cuối của hai sàn này. Kho khoảng ngắn cũ của HNX/UPCoM được tách khóa; dữ liệu cả phiên đã lưu được giữ để tránh tải lại không cần thiết. Đối chiếu [quy định SSI](https://www.ssi.com.vn/khach-hang-ca-nhan/quy-dinh-giao-dich/quy-dinh-giao-dich-co-phieu).
- Cách dùng giá trị nến trong bản ngày 13/11 đã được thay thế sau đối chiếu ngày 14/11: OHLC `value` trong dữ liệu nhận được bằng close × volume, không phải giá trị khớp thực. Sản phẩm chỉ dùng `totalMatchValue` từ tổng hợp ngày cho giá trị khớp; xem bản rà soát 14/11.
- Tên nhóm thử nghiệm trong trang Dữ liệu dùng nhãn người dùng đọc được.
- Xuất CSV có phản hồi khi thất bại; bộ lọc, quy mô và mã bộ dữ liệu vẫn được đối chiếu trước khi xuất.

## Phạm vi được giữ

SSI là nguồn thị trường duy nhất. Phát lại chỉ thay đổi biểu đồ, không thay sổ lệnh và Cảnh báo bên ngoài. Trường chưa có dữ liệu vẫn là dấu _. Điều khiển số tiền tính ngay trên sổ hợp lệ đang xem rồi đồng bộ với máy chủ. Không thêm thao tác đặt, sửa hoặc hủy lệnh.

## Xác minh

- 348 kiểm thử Python và 6 nhóm kiểm thử JavaScript đã qua.
- Đã gọi API cho VN30, VN100, HOSE, HNX thử nghiệm và UPCoM thử nghiệm; kiểm tra phạm vi, trường dữ liệu, tỷ lệ đáp ứng và CSV theo mã lọc.
- Trên trình duyệt: thử chọn ngành/mã; tìm kiếm, theo dõi, sắp xếp và phân trang; bốn kiểu biểu đồ; khối lượng, tham chiếu, MA20 và trạng thái khóa MA50 khi thiếu điểm; khoảng một tuần; đổi ngày phát lại, tiến/lùi, tốc độ và tạm dừng; lọc, sắp xếp, tìm kiếm, ngưỡng và chi tiết Cảnh báo; điều hướng trang Dữ liệu.
- CSV Tổng quan đã xuất đúng một mã ACB theo bộ lọc; CSV Cảnh báo đã xuất đúng một mã LPB với ngưỡng 0,50% và số tiền 1 tỷ đồng.
- Sau khi nạp lại dịch vụ, SSI kết nối thành công. API biểu đồ ACV/PVS trả khoảng 14:00–15:00. Không thay ảnh sổ bên ngoài khi phát lại ngày cũ.
- Kiểm tra ba tab ở chiều rộng điện thoại 375 px, không có tràn ngang; đã thử cả sáng và tối.

Kiểm tra thực tế được thực hiện sau giờ giao dịch: dùng dữ liệu SSI đã lưu và xác minh kết nối bộ thu. Những tình huống trong phiên và lỗi kết nối còn được kiểm tra bằng bộ kiểm thử; không coi dữ liệu đã lưu là giao dịch trực tiếp mới.
