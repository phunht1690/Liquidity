# Phương pháp nghiên cứu LOPM SSI

Vấn đề: nhà đầu tư cần biết khả năng hấp thụ một quy mô giao dịch và áp lực mua–bán trong ảnh sổ lệnh ba mức, thay vì chỉ xem giá khớp cuối.

Spread = ask1 − bid1; spread_bps = spread/mid × 10.000. Độ sâu mỗi phía là tổng giá × khối lượng tại ba mức. Depth min là phía nhỏ hơn. OBI có trọng số [1, 1/2, 1/3]. Weighted mid dùng khối lượng ở mức tốt nhất.

Hấp thụ giả định quy mô N từ 100 triệu đến 5 tỷ đồng, quy đổi lô 100 CP và quét tối đa ba mức. VWAP/slippage chỉ trên phần được hấp thụ, không ngoại suy phần thiếu; không tính phí, thuế hoặc phản ứng thị trường.

OFI hiện là xấp xỉ giữa các ảnh sổ đã lưu. Dù đã lưu sự kiện gốc SSI, chưa triển khai OFI toàn bộ sự kiện hoặc ghép trước/sau giao dịch. Không nối qua mất mẫu, đổi nguồn/ngày/pha, sách không hợp lệ hoặc kết nối cũ.

Amihud ~5 phút = |log(P_end/P_start)| / (chênh proxy giá trị giao dịch / 1 tỷ). Proxy là giá khớp bình quân × tổng khối lượng SSI, có sai số làm tròn; counter giảm thì loại cửa sổ. Cần đủ thời gian, không thay bằng số mẫu hoặc bổ sung dữ liệu giả.

LQS xếp hạng tương đối trong rổ đang chọn, đủ cả năm thành phần: spread 25%, depth min 25%, chi phí có phạt thiếu fill 25%, Amihud 15%, tỷ lệ hai phía 10%. Có hồ sơ trọng số để xem độ nhạy nhưng chưa chứng minh hồ sơ nào tốt hơn. Ngưỡng cảnh báo là thăm dò, không phải xác suất rủi ro hoặc bằng chứng dự báo.

Khi không có cờ pha SSI, pha chỉ ước tính theo lịch giờ Việt Nam. Không coi giờ máy là bằng chứng đầy đủ về ngày nghỉ hoặc tạm ngừng. Không tính chỉ báo liên tục trong ATO/ATC. Nên thu và đối chiếu 5–10 phiên đầy đủ trước khi trình bày kết quả nghiên cứu; một đoạn chạy trong ngày không đáp ứng điều đó.

Effective spread, hồi phục và dự báo chưa triển khai/kiểm chứng. Công cụ phân tích học thuật, không phải khuyến nghị đầu tư.
