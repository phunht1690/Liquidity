# Cập nhật biểu đồ ngày 15/11/2026

## Phần đã bổ sung

- Mở rộng biểu đồ thành cửa sổ gần toàn màn hình; thu gọn bộ thiết lập để dành chỗ cho đồ thị chính và đồ thị tổng. Có nút Thiết lập để mở lại các bộ chọn. Đóng bằng Thu nhỏ hoặc Esc và trở về vị trí cũ.
- Kéo chọn đoạn trên đồ thị tổng hoặc biểu đồ chính; kéo hai mép vùng chọn; di chuyển vùng chọn; chế độ Kéo ngang; +/−, Toàn khoảng, bấm đúp đặt lại, Ctrl + cuộn thu phóng quanh con trỏ.
- Hiện chính xác đầu/cuối khoảng xem và số điểm đang hiển thị trên tổng số điểm. Bản ghi sổ dùng thời gian thực tế; kéo ngang và thu phóng theo thời gian để không làm dài cửa sổ khi mật độ bản ghi thay đổi.
- Tooltip ghim bằng chuột, các phím ←/→ xem từng điểm; Shift + ←/→ dịch khoảng; Home đặt lại. Esc bỏ ghim trước, Esc lần nữa đóng cửa sổ mở rộng.
- Theo yêu cầu tinh gọn, bỏ hai thanh kéo nhỏ Từ điểm / Đến điểm. Chọn khoảng trực tiếp trên đồ thị tổng; hai mép vùng sáng hỗ trợ chuột/chạm và bàn phím. Giữ giao diện ROMER, sáng/tối và các phần ngoài biểu đồ.
- Bỏ hoàn toàn khối Cách dùng chuột và bàn phím bên dưới đồ thị tổng.
- Animation mới chỉ tác động nhóm đường/cột, giữ trục số cố định: mở đường 380 ms, cột 300 ms, thu phóng rời rạc 115 ms, tooltip 105 ms và cửa sổ mở rộng 170 ms. Giá, thanh khoản, độ sâu và đường chi phí dùng chung bộ điều phối. Giữ nguyên hình học, nét đứt và khoảng ngắt dữ liệu. Kéo trực tiếp, các khung Phát lại, thay đổi quy mô và các lần cập nhật nền không phát lại hiệu ứng mở biểu đồ. Bảng giá thu nhỏ giữ tĩnh. Tự bỏ hiệu ứng và hủy chuyển động đang chạy nếu hệ điều hành yêu cầu giảm chuyển động.

## Giá & lượng khớp

Giữ Đường, Vùng, Nến, Bậc thang và các đơn vị/khoảng thời gian đã có. Tooltip có thời điểm, mở/cao/thấp/đóng, khối lượng, tham chiếu và MA khi bật. Khối lượng nến tách riêng khỏi giá; chỉ rõ thang khối lượng. MA tính từ toàn bộ nến đã tải trước khi cắt khoảng xem, tránh mất 19/49 giá trị đầu khi zoom. Giá và màu thay đổi của phiên cũ không nhận tỷ lệ từ phiên hiện tại.

## Chênh giá & lượng chờ

Có thể bật riêng chênh giá, độ dày phía ít hơn, chờ mua và chờ bán. Phía ít hơn dùng màu vàng/nét đứt để phân biệt với hai phía. Trục trái dùng bps (100 bps = 1%), trục phải dùng tỷ đồng. Các giá trị chờ là tổng giá nhân khối lượng tại tối đa ba mức công khai, chưa phải lượng đã khớp.

Nguồn chuỗi đã lưu bổ sung `spread_vnd`, `depth_bid_vnd`, `depth_ask_vnd` từ chính bộ tính sổ lệnh hiện có. Chuỗi hiện tại có cờ ngắt khi thiếu bản ghi hoặc đổi pha. Sổ hợp lệ chỉ có một phía vẫn có thể vẽ phía có dữ liệu; không thay spread chưa biết bằng 0.

Ngoài giờ, đọc phiên có sổ gần nhất dựa trên mốc ảnh sổ đang dùng, hoặc ngày được chọn trong kho; không lấy nến để tạo sổ giả. Chọn nhanh 15 phút/1 giờ tính lùi từ bản sổ hợp lệ cuối. Khi người dùng kéo chọn thủ công, bộ chọn hiện Đoạn đang chọn. Đồ thị tổng vẫn giữ toàn phiên để có thể mở rộng trở lại.

## Phát lại và giới hạn

Phát lại chạy trong đoạn được chọn. Đồ thị tổng cho thấy toàn bộ phiên lịch sử đã lưu; đồ thị chính hiện dần đến vị trí phát. Bảng giá, sổ lệnh, quy mô và cảnh báo bên ngoài không bị ghi đè. Không gọi API theo từng chuyển động chuột; mọi thao tác thu phóng dùng dữ liệu đang có tại trình duyệt.

Kho sổ chỉ có những lúc bộ thu thực sự chạy. Ngày nghỉ có thể có bản kiểm tra kết nối nhưng không có sổ hợp lệ. Những đoạn thiếu/không hợp lệ được giữ trống; các nến không cung cấp được sổ lệnh quá khứ.

## Kiểm tra

- 396 kiểm thử Python đạt ở vòng kiểm tra dữ liệu; 8 bộ kiểm thử JavaScript đạt sau cập nhật animation. Có kiểm tra khoảng chọn, giới hạn thu phóng/kéo ngang, thời gian bản ghi thưa, MA khi zoom, sổ một phía, danh tính tổng độ dày và cờ ngắt chuỗi. Bộ kiểm tra animation xác nhận 5.000 cột chỉ dùng hai hiệu ứng theo nhóm, giữ nguyên đường và khoảng ngắt, trục/crosshair tách khỏi nhóm, không lặp khi polling/phát lại/kéo và tôn trọng chế độ giảm chuyển động.
- Không trùng ID; các đích DOM và đường dẫn tài nguyên của biểu đồ tồn tại; các tệp JavaScript thay đổi qua kiểm tra cú pháp.
- API thực tại máy: FPT ngày 13/11/2026 có 46 nến 5 phút; 2.644 bản ghi sổ, trong đó 2.153 bản hợp lệ. Mọi bản hợp lệ thỏa độ dày phía ít hơn bằng min(chờ mua, chờ bán).
- Trình duyệt: kéo chọn bằng chuột trên cả hai đồ thị, nến/tham chiếu/MA, ghim và bỏ ghim, phím điều hướng, mở rộng/thu nhỏ, chọn phiên, cửa sổ 15 phút, bốn đường thanh khoản và ngày 14/11 không có sổ hợp lệ.
- Phát lại ngày 10/11: 98 bản; tua và phát trong khoảng đã chọn. Giá bên ngoài vẫn 50.100 đồng và sổ vẫn 14:29:56 ngày 13/11, không đổi theo phiên phát lại.
- Màn hình 375×812: một biểu đồ duy nhất, không tràn ngang cửa sổ; giao diện sáng/tối đọc được. Khôi phục kích thước và giao diện tối sau kiểm tra.

Ứng dụng tiếp tục chạy nền tại `http://127.0.0.1:8765/`. Thay đổi không ghi đè `.env`, khóa SSI hoặc kho lịch sử thật.
