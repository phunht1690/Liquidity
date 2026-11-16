# Rà soát mở rộng ba sàn · 15/11/2026

Đã áp dụng trong dự án tại `C:\Users\ADMIN\Downloads\File CK`; máy chủ cục bộ http://127.0.0.1:8765/.

SSI xác nhận danh mục: HOSE 409, HNX 299, UPCoM 809 cổ phiếu. VN30 30 và VN100 100 là tập con HOSE. Không gộp ETF, chứng quyền, trái phiếu hay phái sinh vào danh sách cổ phiếu. Bỏ giới hạn 15 mã HNX/UPCoM của cấu hình đang chạy. Ảnh Phát lại cũ vẫn giữ đúng phạm vi đã ghi.

Kiểm tra trực tiếp WebSocket SSI: 31/31 lô đăng ký được chấp nhận, tổng 3.035 topic quote/trade và market.flag. Ngày kiểm tra là Chủ nhật; xác nhận đăng ký không đồng nghĩa đã có bản tin giao dịch mới trong ngày nghỉ.

## Dữ liệu đã nhận và đang dùng

Thời điểm đối chiếu: 2026-11-15T20:44:54.181340+07:00. Giá có thể thuộc các ngày khác nhau; mỗi dòng giữ ngày/nguồn của chính nó. Các con số bên dưới không cam kết mọi mã đều có giao dịch trong phiên gần nhất.

| Phạm vi | Mã | Có giá | Có khối lượng | Sổ lưu dùng được | Đường giá đủ ít nhất hai điểm | Dòng CSV |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| VN30 | 30 | 30 | 30 | 30 | 30 | 30 |
| VN100 | 100 | 100 | 100 | 99 | 100 | 100 |
| HOSE | 409 | 405 | 405 | 276 | 365 | 409 |
| HNX | 299 | 275 | 275 | 14 | 183 | 299 |
| UPCOM | 809 | 635 | 635 | 15 | 326 | 809 |

Có 1,315/1.517 mã có giá hợp lệ từ dữ liệu đang nhận/đã lưu; 202 mã chưa có giá hợp lệ trong dữ liệu nhận được, giữ dấu “_”. Không suy diễn tình trạng ngừng giao dịch chỉ từ phản hồi rỗng. Các mã mới mở rộng chưa có lịch sử sổ đã ghi cần đợi bản tin SSI của phiên tiếp theo; không dựng sổ từ OHLC. Số sổ trong bảng trên được kiểm tra với mã mặc định của mỗi phạm vi. Khi chọn mã khác, ứng dụng có thể dùng ảnh đối chiếu khác và luôn ghi thời điểm riêng.

Các phép đối chiếu giá trị ba mức mua/bán, lượng đủ/chưa đủ, giá bình quân quét sổ và tổng dòng CSV đều qua kiểm tra. Chỉ tính khi đủ điều kiện dữ liệu; không lấp số thiếu bằng dữ liệu giả.

Lịch sử nến tải nền không phải chờ có giao dịch mới nếu khởi động chỉ có danh mục. Ưu tiên mã đang xem; giữ hàng đợi có giãn nhịp, dùng lại nến đã lưu. Dữ liệu giá 5 phút và ngày giữ 30 ngày lịch. Sổ lệnh và giao dịch chi tiết chỉ có trong khoảng bộ thu thực sự hoạt động.

## Nhận diện và hình doanh nghiệp

Đủ nền cho 1.517 mã; 1.512 mã có logo/nhận diện đã xác minh. Có 771 hình trụ sở, hoạt động, sản phẩm/cơ sở hoặc đồ họa/phối cảnh chính thức; 746 nền minh họa ngành được ghi rõ. Ảnh có nhận diện ở góc và nguồn, giữ tỷ lệ, chuyển mờ vào khung. Không lấy ảnh doanh nghiệp khác để lấp chỗ trống.

Năm mã chưa xác minh được logo riêng: SVH, MQB, HGI, XMP, DKC. MPT có nhận diện lịch sử của cùng doanh nghiệp; GLC là dải tên chính thức. Xem [đối chiếu từng mã](company_media_coverage.md).

## Xác minh

- 406 bài kiểm thử Python đạt; 8 nhóm JavaScript đạt.
- Lượt tải bù đã kiểm tra 1.517/1.517 mã, không còn mục chờ; 1.315 mã thực sự có nến trong kho. Kiểm tra đủ danh mục không đồng nghĩa mọi mã đều có giao dịch.
- 3.029 tài nguyên logo/nền được kiểm tra tệp, mã băm, giải mã và an toàn SVG.
- Các API phạm vi và CSV trả 200, số mã/dòng đúng từng sàn; VN30 ⊆ VN100 ⊆ HOSE, ba sàn không trùng mã.
- Kiểm tra trực tiếp ba tab, HNX/HMR và UPCoM/CMM; logo, ảnh, nguồn và dữ liệu đổi đúng mã. Kiểm tra bố cục hai cột, màn hình hẹp và sáng/tối: ảnh tải được, logo trong ảnh hiện đúng, không tràn ngang.
- Ngoài giờ, API biểu đồ đọc kho cục bộ: FPT 46 nến ngày 13/11, HMR 2 nến ngày 13/11, CMM 2 nến ngày 12/11; mỗi yêu cầu đã kiểm tra mất khoảng 0,06–0,08 giây. Không đổi ngày do người dùng chủ động chọn.
- Có ảnh chụp giao diện, bảng duyệt mẫu và bản JSON thống kê chi tiết trong thư mục outputs của phiên làm việc.

Nguồn kỹ thuật: [SSI danh mục theo sàn](https://developers.ssi.com.vn/en/docs/api-reference/data-securitiesByBoard), [SSI OHLC](https://developers.ssi.com.vn/en/docs/api-reference/data-ohlc).
