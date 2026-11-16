# Kiểm chứng SSI

Kiểm tra đăng nhập và đọc thị trường thật; nhận ack và quote/trade qua WSS. Đối chiếu danh sách 30/100 mã, đơn vị giá/khối lượng, timestamp và giá tham chiếu. Không in key/token, phản hồi tài khoản hoặc thông tin cá nhân.

Kiểm thử ngoại tuyến gồm số liệu tính tay, sách lỗi/thiếu, ATO/ATC, mất kết nối, reset counter, phân trang, refresh token, loại dữ liệu cũ sau reconnect, dữ liệu trùng/đến muộn, giới hạn lưu trữ, bộ lọc, CSV và phát lại chỉ biểu đồ.

Cần làm tiếp cho nghiên cứu: đối chiếu trực quan với bảng giá SSI tại cùng thời điểm; thu 5–10 phiên với độ phủ rõ ràng; đánh giá độ nhạy, ngưỡng và sai số proxy. Không thay thế kiểm chứng thị trường bằng số lượng test phần mềm.
