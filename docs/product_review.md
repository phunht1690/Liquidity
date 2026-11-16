# Rà soát dữ liệu và sản phẩm LOPM

Cập nhật ngày 09/11/2026. Phạm vi: theo dõi thanh khoản và áp lực mua–bán cổ phiếu HOSE, dùng SSI theo yêu cầu người dùng. Giữ thiết kế ba HTML ROMER.

## Dữ liệu có thể lấy và cách sử dụng

Đã kiểm tra tài liệu SSI và gọi API thị trường bằng bộ key hiện có; không gọi tài khoản hoặc giao dịch. Key và token không nằm trong báo cáo.

| Dữ liệu | Bằng chứng | Quyết định |
|---|---|---|
| Giá khớp, khối lượng lũy kế, thời điểm khớp | Đã nhận trade cho 100 mã | Giữ bảng giá và diễn biến |
| Giá/KL chờ mua–bán | Đã nhận quote 100 mã | Giữ ba mức đầu; tính chênh giá, lượng chờ và quy mô |
| Tham chiếu, trần, sàn | Master data đã trả HTTP 200 | Giữ tham chiếu để tính % thay đổi; không tạo thêm ô không cần thiết |
| Tên mã, ngành, thành phần chỉ số | VN100 trả 100 mã; VN30 từng trả 30 mã nhưng lần rà soát trả chính chỉ số | Kiểm tra cấu trúc; dùng danh sách SSI hợp lệ đã lưu và ghi rõ nguồn dự phòng; không chặn luồng giá |
| OHLCV nội ngày | HTTP 200, 226 nến 1 phút của FPT | Có thể mở rộng lịch sử; chưa ghép vào chuỗi sổ lệnh đã tự thu để tránh giả tạo dữ liệu sổ quá khứ |
| Tổng hợp theo ngày, khối ngoại, giá trị khớp | HTTP 200, có dữ liệu FPT | Có thể dùng cho hướng dòng tiền; không thêm trang riêng vì không cần cho bài toán hiện tại |
| Chỉ số và tổng hợp chỉ số | Danh sách 35 chỉ số, tổng hợp VN30 HTTP 200 | Ngoài trọng tâm theo dõi sổ cổ phiếu; không thêm ô trang trí |
| Room ngoại, thỏa thuận, lô lẻ, chỉ số realtime | SSI mô tả các topic tương ứng | Không cần cho quy mô lô chuẩn và áp lực chờ; không coi chưa đăng ký topic là API không có dữ liệu |
| Tài khoản, sức mua, đặt/sửa/hủy lệnh | Không gọi; ngoài phạm vi đã cho phép | Loại khỏi sản phẩm |

Sự kiện quyền doanh nghiệp không cần cho sản phẩm này. Một yêu cầu thử trả 400 không đủ chứng minh SSI không hỗ trợ, nên không gắn nhãn “không có API”.

## Các yếu tố đã bỏ khỏi giao diện

- LQS, thanh chọn trọng số, bảng phân vị và cửa sổ Amihud: không phải dữ liệu SSI trả trực tiếp; điểm ghép chưa hiệu chuẩn và tạo nhiều trạng thái chờ. Không dùng điểm này để gọi mã tốt/xấu.
- OFI/MLOFI, persistence và weighted mid chuyên sâu: chuyển khỏi luồng sử dụng chính; áp lực mua–bán được biểu diễn trực tiếp bằng lượng chờ và tỷ lệ tổng lượng chờ ba mức.
- Effective spread, độ hồi phục, dự báo và H1/H2/H3: chưa có mô hình đã triển khai/kiểm chứng, nên không để các ô “chưa làm” trong sản phẩm.
- Các cảnh báo chất lượng và giải thích baseline trùng lặp: thay bằng trạng thái dữ liệu cụ thể, thời điểm và lý do ngắn.
- Công thức học thuật dài, bộ đếm “phiên thật”, hướng phát triển và kiểm định nghiên cứu: giữ ở tài liệu, không dùng như nội dung chính trên màn hình.

Các phép tính này không phải loại dữ liệu thô mà SSI bị thiếu. Quyết định bỏ dựa trên mức cần thiết, chất lượng triển khai và khả năng giải thích cho người dùng.

## Sản phẩm hiện hành

Ba phần: Tổng quan; Điều cần chú ý; Dữ liệu & cách dùng. Chọn cổ phiếu và quy mô, xem giá, ba mức chờ, chênh mua–bán, giá trị chờ mỗi phía, tỷ lệ mua/bán và phần quy mô có lượng đối ứng. Bảng giá sắp xếp theo lượng chờ, chênh giá, khối lượng hoặc tên mã; không dùng điểm tổng hợp khó giải thích.

Ngoài giờ hoặc khi luồng ngắt, giá khớp gần nhất vẫn giữ timestamp riêng. Phép so sánh dùng một ảnh sổ SSI hợp lệ đã lưu trong phiên, hiển thị rõ thời điểm và không gọi đó là giá có thể giao dịch ngay. Không có ảnh hợp lệ thì không tự điền số. Cả thời điểm giá và thời điểm sổ đều có trong CSV.

Độ phủ được tách rõ: số mã đã nhận giá/sổ và số mã có sổ đủ điều kiện tính ở ảnh đang xem. Trong lần kiểm tra FPT/VN100, đã nhận 100/100 mã nhưng ảnh đối chiếu chung có 98/100 sổ hợp lệ; BWE và SJS chưa đủ điều kiện ở ảnh đó. Chọn riêng một mã sẽ tìm ảnh hợp lệ gần nhất của mã, có thể sớm hơn ảnh chung (SJS đã mở được sổ có báo giá 14:27:00). Không kết luận hai mã này hoàn toàn không có dữ liệu. Khi không tìm được ảnh hợp lệ, giao diện nêu lý do thay vì tạo số; thanh tỷ lệ mua/bán cũng được ẩn.

Phát lại chỉ tác động biểu đồ. Giá, khối lượng và sổ hiện tại bên ngoài không bị biến thành quá khứ. Các điều kiện cần chú ý được mô tả trực tiếp: thiếu lượng chờ cho N hoặc chênh mua–bán vượt mức theo dõi nêu rõ. Khi dùng ảnh lưu, trang điều kiện được ghi là đối chiếu ảnh đã lưu, không phải cảnh báo đang xảy ra.

## Đối chiếu đề bài

Đối chiếu bản 261BFF401101_261BFF401102_GPMUD1_DETHICUOIKY_DOAN (1).docx người dùng gửi:

| Yêu cầu liên quan | Cách đáp ứng chức năng |
|---|---|
| Vấn đề và người dùng rõ | Kiểm tra thanh khoản và quy mô mua/bán cho người theo dõi cổ phiếu |
| Có logic tài chính | Chênh mua–bán, giá trị chờ, tỷ lệ chờ, quét ba mức để tính phần đối ứng và giá bình quân |
| Ít nhất 3 trường có ý nghĩa | Giá, KL chờ, KL khớp, thời điểm, tham chiếu, thành phần rổ |
| Ít nhất 3 kết quả tổng hợp | Chênh giá, độ dày phía ít hơn, tỷ lệ chờ, tỷ lệ đủ lượng cho N |
| Ít nhất 2 trực quan phù hợp | Đồ thị giá/KL, thanh độ sâu mua–bán, đường chênh giá theo quy mô và bảng so sánh |
| Bộ lọc và giải thích | Mã, rổ, ngành, quy mô; giải thích ngắn ngay cạnh kết quả |
| Kết nối, thời điểm, thiếu dữ liệu | Trạng thái riêng, timestamp giá/sổ, chế độ ảnh đã lưu và thông báo rõ |
| Lưu luồng và kiểm thử | WebSocket đã lưu sự kiện/ảnh; kiểm thử công thức, lỗi, export và luồng dùng ảnh lưu |

Không cần có dự báo, học máy, LQS, effective spread hoặc độ hồi phục để đáp ứng các yêu cầu chức năng trên. Chỉ hiển thị bảng giá sẽ không đủ, vì vậy giữ lớp ước tính quy mô và so sánh sổ lệnh.

Lưu ý về nguồn: bản đề mới ghi SSI được dùng “bổ sung” nhưng vẫn còn điều khoản NEO là cốt lõi và giới hạn điểm nếu thiếu NEO. Chuyển hoàn toàn sang SSI là lựa chọn người dùng đã yêu cầu; bản rà soát này không tự xác nhận đã đáp ứng điều khoản nguồn đó. Chưa đủ nhiều phiên để đưa ra kết luận nghiên cứu dài hạn.

## Kiểm chứng bản cập nhật

253/253 kiểm thử phần mềm đạt; JavaScript đã kiểm tra cú pháp. Đã kiểm tra trực quan trên màn hình 1366 × 900 và 390 × 844: ba tab, đổi rổ/mã/quy mô, mở sổ từ điều kiện cần chú ý, lọc điều kiện, tìm mã, sắp xếp, phát lại biểu đồ và tải CSV từ nút giao diện. Không có lỗi console trong lần kiểm tra cuối. Chi tiết và giới hạn bằng chứng ở [product_validation.md](product_validation.md).

## Nguồn đối chiếu

- https://developers.ssi.com.vn/docs/api-reference/data-securitiesByBoard
- https://developers.ssi.com.vn/docs/api-reference/data-securitiesSummary
- https://developers.ssi.com.vn/docs/api-reference/data-ohlc
- https://developers.ssi.com.vn/docs/api-reference/subscribeUnsubscribeMarketData
- Đề cập nhật tại C:/Users/ADMIN/Downloads/261BFF401101_261BFF401102_GPMUD1_DETHICUOIKY_DOAN (1).docx
