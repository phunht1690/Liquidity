# Phạm vi triển khai LOPM SSI hiện hành

Cập nhật 09/11/2026. Làm trong C:\Users\ADMIN\Downloads\File CK. Nguồn vận hành duy nhất là SSI FastConnect v3; tài liệu hiện hành nằm trong docs/ssi_api_contract.md và README.md.

Giữ thiết kế ba HTML ROMER. Sản phẩm có ba phần: Tổng quan, Điều cần chú ý, Dữ liệu & cách dùng. Bộ lọc VN30/VN100, mã, nhóm ngành ICB SSI và quy mô giả định N tác động trực tiếp đến kết quả. Có bảng giá, CSV và phát lại riêng biểu đồ.

Đã đăng nhập và nhận quote/trade SSI thật qua WSS cho 100 mã. API thành phần VN30 có lúc trả chính chỉ số: chỉ dùng danh sách SSI hợp lệ đã lưu, ghi rõ nguồn dự phòng; không coi bản ghi chỉ số là cổ phiếu. Lỗi metadata không chặn luồng giá nếu còn danh sách hợp lệ. Đây mới là đoạn thu trong ngày, chưa phải bộ dữ liệu nghiên cứu đủ 5–10 phiên. Dữ liệu nguồn cũ không được trộn vào phép tính hoặc phát lại.

Key đọc từ .env ở máy chủ. Không đưa key/token/RSA vào mã, trình duyệt, URL, nhật ký, CSV, ảnh hoặc gói nộp. Không tự tạo OTP, không gọi tài khoản, danh mục hoặc API đặt/sửa/hủy lệnh. Token được giữ trong bộ nhớ và làm mới theo phản hồi SSI.

SSI WebSocket nhận toàn bộ quote/trade theo các mã đã xác nhận, lưu ảnh khoảng 5 giây trong giờ hoặc 30 giây ngoài giờ. Thời điểm nguồn SSI và thời điểm nhận/lưu ảnh là hai trường khác nhau. Sau reconnect, giữ cache để xem nhưng không dùng sổ của kết nối cũ để tính chỉ báo.

Chỉ dùng ba mức đầu của quote cổ phiếu HOSE. Kiểm tra dữ liệu thiếu, timestamp, trùng/đến muộn, sách chéo/khóa, phiên đấu giá và trạng thái kết nối. Khi thiếu cờ pha SSI, chỉ mô tả pha ước tính theo lịch giờ Việt Nam. Không suy diễn thời điểm matching engine hoặc lịch ngày nghỉ đã được xác minh.

Giao diện dùng /api/product: chênh giá, giá trị chờ mỗi phía, tỷ lệ tổng khối lượng chờ ba mức và ước tính phần N có lượng đối ứng/giá bình quân. Đây là ước tính trên sổ, không bảo đảm khớp thực tế. Quy tắc cần chú ý gồm thiếu lượng cho N và chênh giá vượt ngưỡng công khai. LQS, hồ sơ trọng số, Amihud, OFI/MLOFI, persistence, dự báo và các ô chưa triển khai đã bỏ khỏi luồng sản phẩm; mã phân tích cũ chỉ giữ để bảo toàn kiểm thử.

Trong phiên liên tục, chỉ tính trực tiếp khi sổ mới, hợp lệ và luồng kết nối. Ngoài giờ hoặc khi luồng ngắt, chọn ảnh sổ SSI hợp lệ đã lưu và ghi rõ thời điểm; giá khớp gần nhất có timestamp riêng. CSV giữ riêng dataset/thời điểm giá và sổ. Không có ảnh hợp lệ thì để trạng thái chờ có lý do; không tạo dữ liệu. Replay chỉ đổi biểu đồ.

Đối chiếu đề mới: đáp ứng chức năng theo dõi thanh khoản/áp lực và quy mô, nhưng đề vẫn giữ điều khoản NEO là nguồn cốt lõi. Chuyển hoàn toàn sang SSI theo yêu cầu người dùng không tự giải quyết điều khoản nguồn đó. Chi tiết ở docs/product_review.md.

Kiểm thử dùng đường dẫn cache/control tạm riêng, không điều khiển worker thật. Chạy tests và kiểm tra JavaScript khi có thay đổi tương ứng. Kiểm chứng dữ liệu thật và kiểm thử phần mềm là hai loại bằng chứng khác nhau.

Công cụ theo dõi và ước tính thanh khoản, không phải khuyến nghị đầu tư.
