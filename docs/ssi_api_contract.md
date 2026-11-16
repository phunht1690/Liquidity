# Hợp đồng dữ liệu SSI FastConnect v3

Đối chiếu ngày 09/11/2026 với tài liệu SSI Developer Portal, SDK chính thức và thông điệp thị trường nhận thực tế. Các URL được cố định trong mã, không nhận địa chỉ tùy ý từ trình duyệt.

## Kết nối đã kiểm tra

- Auth: `POST https://api.ssi.com.vn/api/v3/auth/token`, body `apiKey`, `apiSecret`. HTTP 200, trả `accessToken`, `refreshToken`, `expiresAt`, `refreshExpiresAt`. Token không được lưu vào cache/log.
- Refresh: `POST /api/v3/auth/refresh`, body chỉ chứa refreshToken hiện hành. Được kiểm thử ngoại tuyến; thời hạn dùng từ phản hồi, không cố định số giờ. Refresh token đã dùng không được tái sử dụng.
- Thành phần chỉ số: `GET /api/v3/data/securitiesByBoard?index=VN30` và `index=VN100`. Lần xác nhận đầu trả list trực tiếp 30/100 mã, HOSE, stockType=Stock, VN30 là tập con VN100. Lần rà soát sau trong ngày, VN100 vẫn trả 100 cổ phiếu nhưng VN30 trả một bản ghi chỉ số (stockType null). Collector kiểm tra cấu trúc và dùng danh sách SSI hợp lệ đã lưu, có cảnh báo nguồn dự phòng; không biến bản ghi chỉ số thành cổ phiếu và không chặn luồng giá chỉ vì metadata lỗi.
- Master data: `GET /api/v3/data/masterdata`, tham số `from`, `to` dạng YYYY/MM/DD, `pageIndex`, `pageSize`. Phân trang `pagesCount`; chuẩn hóa giá trần/sàn/tham chiếu theo mã.
- Stream: `wss://stream.ssi.com.vn/ws/v3`, Bearer token trong header HTTPS handshake. Đăng ký `method=subscribe`, `channel=DATA`, topics theo các mã cụ thể và `market.flag`. Có heartbeat ping_pong và nối lại với giãn nhịp.

Tài liệu SDK nói streaming cần OTP, nhưng phép thử tài khoản này ngày 09/11/2026 đã nhận ack `ok` và thông điệp quote/trade bằng token Market Data không OTP. Đây là kết quả quan sát của bộ key hiện hành, không khẳng định mọi gói SSI có cùng quyền. Không gọi requestOtp, không cấp thêm quyền giao dịch.

REST chỉ cho phép danh sách thị trường đã ghi trong mã. Mọi API tài khoản, giao dịch, URL tùy ý bị từ chối trước khi gửi. Tần suất REST tối đa khoảng 4 lượt/giây; nhận giá qua WebSocket, không gọi REST cho từng lần cập nhật màn hình.

## Ánh xạ thông điệp đã nhận

| Topic/trường | Ý nghĩa và ánh xạ |
|---|---|
| quote: s, t | Mã, thời điểm báo giá SSI dạng YYYY/MM/DD HH:mm:ss; lưu nguyên gốc và quy đổi UTC+7 |
| quote: bids, asks | Mảng [giá, khối lượng], lấy ba mức đầu; thay toàn bộ mảng khi có frame mới, không kế thừa mức thiếu |
| trade: s, t, p | Mã, thời điểm giao dịch, giá khớp gần nhất |
| trade: q | Khối lượng của giao dịch; không nhầm với khối lượng lũy kế |
| trade: v | Tổng khối lượng lũy kế dùng cho bảng giá |
| trade: a | Giá khớp bình quân; a × v là proxy giá trị giao dịch, không gọi là tổng giá trị chính xác |
| master: refPrice, ceiling, floor | Giá tham chiếu, trần, sàn, đơn vị đồng |
| membership: lotSize, icbName | Lô giao dịch và tên ngành SSI; sản phẩm hiện giả định lô 100 CP |
| market.flag: b, f, t | Sàn, cờ phiên, thời điểm theo SDK; khi chưa nhận thì không tự gán cờ LO |

Các frame quote thực nhận có thể chứa 10 mức, trong đó mức 4–10 bằng 0; dashboard HOSE chỉ phân tích ba mức đầu. Thiếu giá/khối lượng được giữ null. ATO/ATC dạng chữ, sách chéo/khóa, mức sai thứ tự, dữ liệu cũ, lệch ngày hoặc mất kết nối không được đưa vào chỉ báo liên tục.

## Giới hạn cần giữ rõ

Timestamp trong bảng và OFI là thời điểm lưu ảnh. Timestamp SSI của báo giá/khớp được lưu riêng, chưa chứng minh là thời điểm sự kiện trực tiếp tại matching engine. Không tuyên bố độ trễ sàn. Sự kiện quote/trade đến muộn bị loại riêng từng loại; frame trùng liên tiếp được đếm và bỏ. Sau nối lại, sổ cũ không được tính cho tới khi có quote của kết nối mới.

REST securitiesSummary thử theo chỉ số trả bản ghi của chính chỉ số, không phải bảng giá 100 cổ phiếu. Thử theo FPT trả dữ liệu tổng hợp ngày; OHLC FPT trả 226 nến một phút. Các dữ liệu này không thay được lịch sử sổ lệnh nên dashboard không dùng chúng để giả lập sổ quá khứ hoặc realtime. Tài liệu SSI lưu ý dữ liệu summary/master có thể được cache phía dịch vụ.

Nguồn: https://developers.ssi.com.vn/docs/getting-started/api-keys ; https://developers.ssi.com.vn/docs/sdk/python/service-classes ; https://github.com/SSI-Securities-Inc/ssi-sdk-python
