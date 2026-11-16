# Kiểm chứng sản phẩm SSI

Ngày 09/11/2026, kiểm tra trên ứng dụng tại http://127.0.0.1:8765/ trong thư mục C:/Users/ADMIN/Downloads/File CK.

## Phần mềm

- 253 kiểm thử đạt, chạy trên chính bản đã triển khai; JavaScript app.js và chart-replay.js qua kiểm tra cú pháp Node.
- Kiểm tra công thức, điều kiện chất lượng/pha, tách giá và sổ, trạng thái trực tiếp/ảnh lưu/chờ, thay đổi N và bộ lọc, CSV, lỗi API, danh sách mã dự phòng và giữ bộ thu khi master data lỗi.
- Bộ kiểm thử dùng kho và điều khiển tạm riêng, không tác động bộ thu đang chạy.

## Dữ liệu thật

Lần kiểm tra HTTP cuối lúc 16:38:11 UTC+7:

| Mục | Kết quả |
|---|---|
| Nguồn | SSI FastConnect, WebSocket đang kết nối |
| Phạm vi | VN30 30 mã; VN100 100 mã |
| Đã nhận | Giá và sổ 100/100 mã |
| Sổ đủ điều kiện ở ảnh chung FPT/VN100 | 98/100 mã; giao diện ghi rõ BWE và SJS ở ảnh này |
| Ảnh sổ dùng so sánh mặc định | 14:29:53 ngày 09/11/2026, báo giá FPT từ SSI 14:29:56 |
| Giao dịch FPT gần nhất | 14:45:00 ngày 09/11/2026 |
| Chênh FPT / độ dày phía ít hơn | 100 đồng / 12.386.340.000 đồng |
| Quy mô PVT | N = 100 triệu: mua đủ 100%; N = 5 tỷ: mua đủ khoảng 18,28% |
| CSV | 100 dòng, tách dataset/thời điểm giá và sổ; không có cột nghiên cứu rỗng |
| Phát lại | Kho có 328 ảnh ở thời điểm kiểm tra; tiếp tục tăng khi bộ thu hoạt động |
| Giá trị bí mật trong phản hồi đã kiểm tra | Không xuất hiện |

Một lần đọc VN100 từ cache mất khoảng 0,625 giây trên máy hiện tại; đây là phép đo riêng lẻ, không phải cam kết tốc độ hoặc độ trễ sàn. REST và kết nối SSI do một worker dùng chung; đổi tab không tải lại SSI cho từng mã.

API danh sách VN30 từng trả chính chỉ số. Đã sửa kiểm tra hình dạng và dùng danh sách SSI hợp lệ đã lưu khi cần, có cảnh báo. Ở lần kiểm tra cuối, cả VN30/VN100 lại có nguồn ssi_api và không còn cảnh báo metadata. Không suy ra API sẽ luôn trả đúng cấu trúc.

## Thao tác giao diện

Đã xem trực quan cả ba trang theo thiết kế ROMER. Đã sửa lỗi CSS cũ che trang điều kiện/dữ liệu, liên kết dữ liệu trùng, trạng thái “đã kết nối”, vị trí đầu trang khi đổi tab và thông báo tạm bị ẩn.

- Chuyển VN30 sang VN100 và đổi mã/quy mô làm kết quả thay đổi.
- Lọc điều kiện còn 12 mã khi chỉ chọn thiếu khối lượng cho N = 1 tỷ trong VN30; chọn LPB rồi mở sổ hiển thị đúng LPB.
- Tìm FPT còn đúng một hàng; xóa từ khóa trả lại danh sách.
- Nút xuất giao diện tải được CSV VN30; endpoint xuất VN100 cũng đã kiểm tra 100 dòng và kiểm tra dataset.
- Phát lại đi từ bản 1 đến bản cuối; giá FPT ngoài biểu đồ vẫn 51.000 đồng và thời điểm sổ ngoài biểu đồ không đổi.
- Chọn riêng SJS tìm được ảnh sổ sớm hơn, thay vì coi mã hoàn toàn thiếu dữ liệu.
- Đã kiểm tra màn hình 1366 × 900 và 390 × 844; trang không tràn ngang. Bảng rộng cuộn trong khung. Đã trả kích thước trình duyệt về mặc định sau kiểm tra.
- Không có lỗi console ở lần kiểm tra cuối. Đã lưu ảnh LOPM_SSI_Product.png và LOPM_SSI_Data.png cùng bộ bàn giao.

## Giới hạn của kết quả

Lần xác nhận sản phẩm cuối diễn ra ngoài giờ giao dịch, nên các phép so sánh đang dùng ảnh sổ hợp lệ đã lưu, không phải sổ có thể giao dịch ngay. Việc chuyển sang tính trực tiếp, bảo vệ khi mất luồng và làm mới token có kiểm thử phần mềm; không coi lần kiểm tra ngoài giờ này là bằng chứng chạy liên tục nhiều phiên. Dữ liệu đang có chưa đủ nghiên cứu 5–10 phiên. Đề vẫn giữ điều khoản NEO cốt lõi, đã nêu trong product_review.md.
