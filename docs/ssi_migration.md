# Kết quả chuyển nguồn sang SSI

Ngày 09/11/2026: đã chuyển bộ kết nối, worker, cache, API cục bộ, nhãn giao diện, CSV và phát lại sang SSI FastConnect v3. Giữ nguyên thiết kế ROMER và phạm vi chỉ đọc thị trường.

Đăng nhập v3 thành công. Danh sách VN30 trả 30 mã, VN100 trả 100 mã. Kết nối WSS chấp nhận subscription DATA và đã nhận quote/trade FPT, HPG, sau đó mở bộ thu toàn rổ. Giá/khối lượng/sổ lệnh đã được lưu tại data/ssi và API dashboard trả HTTP 200. Không gọi tài khoản, danh mục hoặc giao dịch.

Trong giai đoạn chạy thật đã thu đủ sổ của 100 mã; giá khớp chỉ có khi nhận giao dịch kể từ lúc kết nối hoặc có cache SSI trước đó. Các mã chưa có giao dịch mới vẫn được ghi rõ thiếu giá, không bịa dữ liệu. Các chỉ số liên tục bị tạm ngừng khi sang ATC/ngoài giờ; giá và cache phát lại vẫn sử dụng được.

Kiểm thử tự động và xác minh cuối cùng được cập nhật sau khi triển khai. Trình duyệt xem thử bị cổng cấp quyền từ chối, chưa kiểm tra hình ảnh giao diện trong lần chuyển nguồn này. Kiểm tra máy chủ, cấu trúc giao diện, cú pháp JavaScript, bộ lọc, CSV và cache được thực hiện riêng.

Khóa đã xuất hiện trong chat; nên thay bộ key trên SSI và cập nhật .env cục bộ, không gửi lại key mới vào chat.

## Xác minh sau triển khai

- 230 kiểm thử tự động đạt; cú pháp app.js và chart-replay.js hợp lệ.
- API dashboard, bộ lọc VN30/VN100, mã/ngành, xuất CSV và chart-cache trả dữ liệu SSI thật.
- Đã nhận sổ, giá khớp và khối lượng của 100/100 mã. BWE và SJS đã có giao dịch cuối ngày sau ATC.
- Có 214 điểm phát lại và 47.916 sự kiện SSI gốc đã lưu tại lần kiểm tra 14:46 ngày 09/11/2026. Các con số này tiếp tục tăng khi bộ thu chạy.
- Chuỗi trước 14:30 có 51 ảnh quan sát thật, trải từ 14:25:32 đến 14:29:58. Tính được spread/OFI, nhưng chưa đủ 5 phút nên LQS để trống. Không coi đó là phiên nghiên cứu đầy đủ.
- Thị trường đã đóng khi kiểm tra cuối: các chỉ báo dành cho phiên liên tục tạm ngừng đúng điều kiện. Giá và kho phát lại vẫn truy cập được.
- Kiểm tra các phản hồi công khai không chứa key, secret hoặc RSA; .env và đường API của nguồn cũ không truy cập được. Chặn yêu cầu refresh từ trang khác.
- Không còn tiến trình thu nguồn cũ; bộ thu SSI đang chạy tại dashboard cục bộ.

Tệp nén bàn giao chỉ gồm mã nguồn, tài liệu, thiết kế và kiểm thử; không kèm .env, cache hoặc dữ liệu tài khoản. Dữ liệu SSI đã thu vẫn được giữ cục bộ trong File CK/data/ssi.
