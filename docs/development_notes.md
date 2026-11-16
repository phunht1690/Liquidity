# LOPM — Theo dõi thanh khoản với SSI

Sản phẩm giúp xem giá, so sánh lượng chờ mua–bán và kiểm tra một quy mô tham chiếu trên các mức giá SSI thực sự cấp, tối đa 10 mỗi phía. Giữ thiết kế HTML ROMER, chỉ đọc thị trường SSI. Có bộ lọc VN30/VN100 và toàn bộ cổ phiếu trong danh mục SSI của HOSE, HNX, UPCoM. Ngày 15/11/2026 xác nhận 409 HOSE, 299 HNX và 809 UPCoM: 1.517 mã riêng biệt. VN30/VN100 là các tập con của HOSE, không cộng thêm vào tổng.

Dashboard tự cập nhật và tự thử lại khi kết nối gián đoạn; thanh trạng thái không cần nút cập nhật thủ công. Dữ liệu phiên đã lưu được ghi rõ thời điểm. Bộ lọc ngành áp dụng đồng thời cho mã đang xem và danh sách cổ phiếu.

## Bản cập nhật phạm vi và dữ liệu

Bản 16/11 bổ sung khối lượng so với 20 phiên trước tại cùng các nến đã hoàn tất, khối ngoại theo số cổ phiếu và room còn lại, giá trần/sàn, tổng hợp khớp lệnh/thỏa thuận theo đúng phiên SSI trả và giá trị khớp thật theo ngành. Các phần chi tiết mặc định thu gọn. Tổng hợp phiên trước giữ ngày riêng, không ghi đè số liệu trong phiên hiện tại. Xem [phạm vi và cách tính các phần bổ sung](liquidity_extensions.md).

- WebSocket vẫn nhận quote/trade; giao diện nhận thông báo SSE từ một bộ thu chung. Giá và sổ có thời điểm riêng. API tổng hợp ngày SSI chạy nền, ưu tiên mã đang xem, đối chiếu giá đóng cửa sau phiên và bổ sung giá trị khớp thực từ `totalMatchValue`. Không cộng `value` của OHLC để gọi là giá trị khớp: dữ liệu đã kiểm tra cho thấy trường này bằng giá đóng nến nhân khối lượng. Nến ngày đã tải bù có thể bổ sung giá, khối lượng và mở/cao/thấp khi chưa có tổng hợp ngày, nhưng không thay bằng giá trị giao dịch ước tính. Tổng hợp ngày và nến cũ không ghi đè một lần khớp có ngày mới hơn. Nến và sổ lệnh tiếp tục dùng nguồn/thời điểm riêng.
- Quy mô tham chiếu được đổi theo giá giữa và lô của mã; số tiền mua/bán ước tính có thể khác số tiền tham chiếu. Sổ một phía dùng giá khớp/tham chiếu để quy đổi và ghi rõ; thiếu hai giá thì không xuất chênh giá. Sổ ít mức hoặc mức [0,0] được phân biệt với trường bị thiếu; dấu “_” giữ nguyên cho điều chưa biết.
- Bước giá và lịch phiên theo sàn, đối chiếu tài liệu SSI. Phép tính cần giá trần/sàn và lô cùng ngày xác nhận đơn vị. Lịch ngày nghỉ, tạm ngừng và mọi hạn chế riêng từng mã chưa được chứng nhận chỉ bằng đồng hồ; cờ SSI có thể làm phép tính ngừng sử dụng. Ảnh Phát lại cũ của nhóm thử nghiệm giữ nguyên phạm vi thực tế; không đổi nhãn 15 mã thành toàn sàn.
- Bảng giá có tìm mã/tên/sàn, đánh dấu theo dõi cục bộ và phân trang 25/50/100 mã. CSV xuất mọi mã khớp bộ lọc tìm kiếm/theo dõi trên tất cả trang. CSV Cảnh báo theo bộ lọc riêng của trang đó.
- Khi cập nhật lỗi, giữ số liệu và tự đổi nhãn sang dữ liệu đã lưu; nối lại thành công mới phục hồi trạng thái cập nhật. Không phát sinh điều kiện Cảnh báo thanh khoản chỉ vì API lỗi.
- Nhật ký Cảnh báo ghi thời điểm ứng dụng bắt đầu quan sát, cập nhật và kết thúc điều kiện trong phiên. Khi mất đoạn thu thì bắt đầu lượt quan sát mới; không suy ra thời điểm điều kiện thực sự phát sinh. Ảnh lưu ngoài phiên không tạo lịch sử cảnh báo giả.
- Bản mới lưu một lần phần quote thay đổi, có nén, metadata dùng chung và mốc kiểm tra. Giữ theo ngày, không cắt còn 2.500 ảnh/ngày. Phát lại đọc riêng mã, vẫn đọc kho cũ và chỉ tác động biểu đồ. Không nội suy qua khoảng thiếu.
- Đường giá nhỏ ở Bảng giá dùng nến 5 phút SSI của một phiên, lấy cho toàn bộ mã bộ thu đang theo dõi qua một hàng đợi chung. Cache `data/ssi/intraday_trends.sqlite3` giữ phiên thực gần nhất của từng mã; điểm cuối dùng giao dịch thật mới hơn lần đồng bộ. Ngoài giờ giữ phiên có dữ liệu; đổi ngày không nối hai phiên thành một đường. Lần đầu cần thời gian lần lượt tải danh mục; yêu cầu bảng giá không chờ từng API. Màu dùng tham chiếu cùng ngày; ngày và thời điểm có trong tooltip. Nguồn: [SSI OHLC](https://developers.ssi.com.vn/en/docs/api-reference/data-ohlc).
- Phát lại giữ 30 ngày lịch. Kho bản tin gốc giữ tối đa 7 ngày, ngân sách mặc định 2.048 MB; khi đầy sẽ dọn ngày cũ trước, khi chỉ còn dữ liệu ngày hiện tại thì tạm dừng ghi bản tin, vẫn nhận giá và lưu ảnh Phát lại. Chính sách hai kho hiển thị trong Dữ liệu & cách dùng. Những bản tin cũ đã bị giới hạn 50.000/ngày trước bản cập nhật không thể khôi phục từ OHLC.
- `/api/state` và `/api/export.csv` nghiên cứu cũ trả 410. Giao diện và CSV sản phẩm dùng `/api/product` và `/api/product/export.csv`.

Quy tắc tham khảo: [SSI — quy định cổ phiếu](https://www.ssi.com.vn/khach-hang-ca-nhan/quy-dinh-giao-dich/quy-dinh-giao-dich-co-phieu), [tổng hợp ngày](https://developers.ssi.com.vn/en/docs/api-reference/data-securitiesSummary). Có danh mục không đồng nghĩa mọi mã đều có bản tin dùng được. Số mã đã nhận giá, nhận sổ và có phép tính được trình bày riêng. Cần để bộ thu chạy qua các phiên thật để tích lũy bằng chứng, không coi số ảnh hoặc unit test là số phiên đủ dữ liệu.

Về đối chiếu đề bài: sản phẩm hiện dùng SSI theo yêu cầu triển khai. Tài liệu đề bài cập nhật vẫn ghi NEO là thành phần cốt lõi và SSI bổ sung; việc chấp nhận thay nguồn cần được làm rõ trong phạm vi đồ án, không tự coi là đã đạt điều kiện này.

Bộ nhận diện ánh xạ theo mã; ảnh và logo đổi theo lựa chọn cổ phiếu. Ảnh lưu cục bộ trong `src/app/static/assets/companies`, tải độc lập với luồng giá. `manifest.json` ánh xạ đủ 1.517 doanh nghiệp; `sources.json` lưu nguồn, loại hình, mã băm và bằng chứng đối chiếu. Các nhãn phân biệt ảnh trụ sở, hoạt động/sản phẩm, phối cảnh và nền minh họa ngành. Phần giá và phép tính tiếp tục dùng SSI.

## Tóm tắt thanh khoản và so sánh ngành

Tổng quan có khung tóm tắt theo phạm vi/ngành và số tiền đang chọn. Hai lựa chọn Bảng giá / Theo ngành chỉ hiện một bảng tại mỗi thời điểm; bảng ngành có sáu ngành ban đầu và nút mở toàn bộ. Bấm ngành để mở bảng giá đã lọc; danh sách lọc thanh khoản có số lượng, kết hợp tìm kiếm/theo dõi và xuất CSV đúng kết quả. Khi đổi số tiền, các tỷ lệ và bộ lọc tính lại ngay từ sổ đã xác nhận.

Có thể xuất bản tóm tắt HTML ở Tổng quan. File mở độc lập, gồm toàn bộ ngành, mã cần kiểm tra và bảng số liệu của phạm vi/ngành, giữ rõ thời điểm ảnh sổ và ngày giá từng mã. Mỗi chỉ tiêu có độ phủ riêng; dữ liệu thiếu giữ `_`. Xem [quy tắc và kiểm tra](liquidity_brief.md).

Dữ liệu & cách dùng có hai lựa chọn Dữ liệu / Hướng dẫn. Dữ liệu có bộ chọn Phạm vi riêng ngay tại Độ phủ, luôn tính toàn bộ ngành và không đổi mã/ngành/số tiền ở Tổng quan. Phần này tập trung độ phủ, kho lưu và năm nhóm nguồn; chi tiết được thu gọn. Hướng dẫn có ba bước thao tác, bốn chỉ tiêu đọc nhanh và các mục mở rộng. Không lặp khung xuất tóm tắt hoặc kết quả quy mô của Tổng quan; ví dụ nằm trong phần mở rộng. Xem [bố cục và điều hướng](data_and_guide.md).

## Chạy

Mở `start.bat` hoặc `start.ps1`. Dashboard tại http://127.0.0.1:8765/. Máy chủ và bộ thu chạy nền; đóng cửa sổ khởi động hoặc tab web vẫn tiếp tục thu khi máy bật, không ngủ và có mạng. Mở nhiều lần không tạo thêm bộ thu. Bộ thu có thể tự chạy sau khi đăng nhập Windows, không mở trình duyệt.

Khi khởi động, dữ liệu hiện tại được ưu tiên; lịch sử nến 5 phút và ngày của 30 ngày lịch được tải bù ở nền cho toàn bộ mã theo dõi. Ngày đã có được dùng lại, mỗi mã/thời điểm chỉ lưu một nến trong `data/ssi/price_bars.sqlite3`. Lượt đầu cho toàn bộ danh mục cần thời gian và không chặn bảng giá. Dữ liệu giá có thể tải bù cả những phiên máy chưa chạy; sổ lệnh và giao dịch chi tiết chỉ có trong khoảng đã thu thật. Trạng thái và dung lượng nằm trong Dữ liệu & cách dùng.

Quản lý bằng `manage_background.ps1 -Action Status|Start|Stop|EnableAutostart|DisableAutostart` (chọn một hành động). Tự khởi động dùng mục Run của tài khoản Windows hiện tại, không cần mật khẩu. Xem [hướng dẫn chạy nền](background_collection.md) để dừng hoặc gỡ tự khởi động. Chạy trực tiếp để kiểm tra bằng `python -m src.app.launcher --foreground` sau khi dừng bộ nền.

Python 3.10 trở lên, thư viện trong requirements.txt. Máy hiện dùng môi trường `%USERPROFILE%\.venv`. `.env` chứa SSI_API_KEY và SSI_API_SECRET; cấu hình mẫu là `.env.example`. Không đưa .env vào mã nguồn hoặc gói nộp. Không gọi tài khoản, giao dịch hoặc OTP.

Trên máy Windows mới, mở PowerShell tại thư mục dự án và chạy:

```powershell
if (-not (Test-Path -LiteralPath "$env:USERPROFILE\.venv\Scripts\python.exe")) {
    py -m venv "$env:USERPROFILE\.venv"
}
& "$env:USERPROFILE\.venv\Scripts\python.exe" -m pip install -r requirements.txt
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
```

Điền API Key/Secret vào `.env` tại máy, sau đó mở `start.bat`. Không ghi đè `.env` đã có. Nếu chưa cài Python, cài bản từ 3.10 trở lên trước các lệnh trên. Tự khởi động Windows là tùy chọn, bật bằng `manage_background.ps1 -Action EnableAutostart` sau khi app chạy được.

Một API Key và một API Secret tạo thành một bộ xác thực. Có thể thêm bộ SSI độc lập thứ hai qua SSI_API_KEY_2 và SSI_API_SECRET_2. Bộ thu giữ một luồng đang hoạt động, chỉ chuyển sang bộ dự phòng khi xác thực/quyền truy cập bị từ chối; không đổi key theo từng yêu cầu hoặc chỉ vì một trường trống. Mỗi lần lỗi chỉ thử chuyển một lần, bộ vừa lỗi được nghỉ ít nhất 5 phút. HTTP 429 tuân thủ thời gian chờ của SSI và không kích hoạt đổi key. Cấu hình hiện có một bộ hoạt động; chưa có bộ thứ hai để xác nhận chuyển đổi thực tế.

## Cách dùng

1. Chọn rổ, cổ phiếu và ngành.
2. Mở “Sổ lệnh & quy mô”, chỉnh “Số tiền muốn kiểm tra” ngay trên bảng kết quả: kéo thanh, nhập triệu đồng hoặc chọn mức nhanh từ 100 triệu đến 5 tỷ. Kết quả tự tính lại trên sổ đang xem, không cần bấm Áp dụng.
3. Xem chênh mua–bán, giá trị chờ mỗi phía, bên chờ nhiều hơn và ước tính mua/bán.
4. Mở “Điều cần chú ý” để xem mã thiếu lượng chờ cho quy mô hoặc chênh mua–bán lớn.
5. Chọn “Phát lại” ngay trong biểu đồ để đọc các lần đã lưu. CSV ghi rõ thời điểm giá và thời điểm sổ dùng để tính.
6. Bấm nút “Sáng” hoặc “Tối” ở đầu trang để đổi giao diện. Lựa chọn được lưu trên trình duyệt; các tab đang mở cùng địa chỉ cũng đổi theo. Khi chưa chọn, giao diện theo cài đặt sáng/tối của thiết bị.

Khung doanh nghiệp có nền cho đủ 1.517 mã và nhận diện đã xác minh cho 1.512 mã; MPT dùng nhận diện từng công bố của cùng doanh nghiệp và có nhãn riêng. Giữ 138 hình trụ sở/văn phòng (134 ảnh chụp, 4 phối cảnh), bổ sung 633 hình hoạt động/sản phẩm/cơ sở hoặc đồ họa chính thức. Còn 746 nền minh họa ngành được ghi rõ; logo thật xuất hiện trong nền khi có. SVH, MQB, HGI, XMP và DKC chưa xác minh được logo riêng nên giữ mã/tên dự phòng. Ảnh doanh nghiệp có thêm nhận diện ở góc; hình phủ khít khung, chuyển mờ sang phần nội dung, giữ tỷ lệ và có nguồn. Xem [đối chiếu đủ 1.517 mã](company_media_coverage.md).

Bộ ảnh ban đầu có ảnh chụp và phối cảnh được ghi rõ loại nguồn trong manifest. VJC dùng phối cảnh Vietjet Plaza, có nhãn phân biệt với ảnh chụp thực tế; PNJ/TCH giữ nền nhận diện dự phòng. Ảnh VJC cũ đúng tòa Vietjet Plaza nhưng biển HDBank chiếm ưu thế, nên đã gỡ để tránh nhận diện nhầm. Nhãn phân biệt rõ tòa nhà thuê, văn phòng đại diện và trụ sở pháp lý; xem [bảng đối chiếu 100 mã](company_images_review.md). Ảnh nền phủ kín khung bằng object-fit: cover và căn điểm nhấn theo ảnh; không còn viền trống do giữ nguyên tỷ lệ ảnh gốc. Ảnh tư liệu HHV và PHR có ghi năm nguồn. Khi chọn mã, danh tính doanh nghiệp và hình ảnh cập nhật từ tài nguyên cục bộ; giá và các kết quả của mã cũ được xóa trong lúc đợi SSI trả dữ liệu cho mã mới.

Tổng quan có ba phần: Cổ phiếu & biểu đồ, Sổ lệnh & quy mô, Bảng giá. Hai mục sau nằm dưới Tổng quan trong menu; thanh điều hướng ghim và tự đánh dấu phần đang xem khi cuộn.

Biểu đồ giá dùng dữ liệu OHLC chính thức từ SSI qua `/api/v3/data/ohlc`, không ghép nến từ các lần nhận bảng giá. Có Đường, Vùng, Nến, Bậc thang; khoảng phút, giờ, phiên, tuần, tháng, năm và chọn ngày; mỗi nến/điểm từ 1 phút đến 1 ngày, tự giới hạn theo độ dài khoảng. Có thể bật tắt khối lượng, tham chiếu đúng phiên, bình quân khớp phiên SSI đã ghi, MA20 và MA50. Bình quân phiên chỉ xuất hiện tại các mốc cùng ngày đã thu đủ gần cuối nến; không tính lại từ OHLC. MA là trung bình giá đóng của 20/50 nến theo đơn vị đang chọn; chỉ hiện khi đủ nến. Khối lượng là khối lượng từng nến do SSI trả. API giao diện `/api/price-history` giữ token ở máy chủ; cache riêng `data/ssi/chart_history.sqlite3`, tối đa 128 bộ lọc, dùng lại trước khi đồng bộ nền. Biểu đồ đường nhỏ cạnh mã dùng xanh/đỏ theo thay đổi so với tham chiếu, trung tính nếu chưa có tỷ lệ.

Phát lại vẫn chỉ dùng các lần nhận thực tế đã lưu trên máy, tách khỏi bảng giá và sổ lệnh hiện tại. Không cho chọn nến trong Phát lại vì các bản nhận rời rạc không thể hiện đầy đủ cao/thấp của thị trường. Giá còn sót từ ngày trước được loại khỏi biểu đồ ngày mới; khối lượng giữa hai lần nhận không được tính khi thiếu mốc đầu, mất mẫu hoặc đặt lại bộ đếm. Phần Sổ lệnh bổ sung đồ thị độ sâu cộng dồn theo số mức giá SSI thực sự cấp (tối đa 10 mỗi phía) và ghi rõ cùng thời điểm sổ.

Hai nội dung biểu đồ đều có Mở rộng, kéo chọn đoạn trên đồ thị tổng hoặc biểu đồ chính, kéo ngang, nút +/− và Toàn khoảng. Ctrl + cuộn thu phóng quanh con trỏ; bấm một điểm để ghim tooltip. Các phím ←/→ xem từng điểm, Shift + ←/→ dịch khoảng, Home đặt lại. MA được tính trên toàn bộ nến đã tải rồi mới cắt khoảng xem. Đồ thị tổng chọn khoảng chỉ hiện trong Mở rộng; hai mép vùng sáng hỗ trợ kéo bằng chuột/chạm và điều chỉnh bằng phím ←/→, Home/End. Bản thường giữ Khoảng xem, kéo chọn trên biểu đồ chính và nút đặt lại; thu nhỏ giữ nguyên đoạn đã chọn. Nâng cao đặt cạnh Khoảng xem, mặc định thu gọn ở cả bản thường và Mở rộng, chứa kiểu biểu đồ, độ chia thời gian, các đường và chế độ kéo. Hàng nhanh giữ nội dung/khoảng xem; chọn ngày tùy ý vẫn dùng được khi thiết lập đóng. Mở rộng giữ nguyên lựa chọn và đoạn đang xem. Chi tiết nguồn chuyển vào Nâng cao → Nguồn & tình trạng dữ liệu, thay cho đoạn mô tả dài dưới đồ thị tổng. Xem [cách trình bày biểu đồ](chart_layout.md). Thu phóng chỉ lọc dữ liệu tại trình duyệt, không gọi API theo chuyển động chuột.

Giao diện đã bỏ khối hướng dẫn chuột/bàn phím dưới đồ thị tổng. Khi mở hoặc đổi dữ liệu/kiểu biểu đồ, đường hiện dần và cột khối lượng mở nhẹ từ đáy; trục và nhãn không chạy hiệu ứng. Hiệu ứng dùng tối đa hai nhóm dữ liệu, áp dụng cho giá, thanh khoản, độ sâu và đường chi phí. Thu phóng rời rạc chuyển nhẹ, còn kéo liên tục, cập nhật nền và các khung Phát lại phản hồi ngay. Tooltip và cửa sổ mở rộng có hiệu ứng ngắn; tự giảm chuyển động theo thiết lập hệ điều hành. Các đường nhỏ trong bảng giá giữ tĩnh để tránh nhấp nháy khi bảng tự cập nhật.

Chênh giá & lượng chờ có thể bật riêng chênh giá, độ dày phía ít hơn (nét đứt), chờ mua và chờ bán. Hai trục tách bps và tỷ đồng; lượng chờ là tổng giá trị tại các mức SSI đã cấp, chưa phải khối lượng đã khớp. Ngoài giờ, đồ thị đọc lại phiên sổ hợp lệ gần nhất hoặc ngày người dùng chọn từ kho thật; nến OHLC không được dùng để tạo sổ lệnh. Khoảng 15 phút/1 giờ được tính lùi từ bản sổ hợp lệ cuối cùng, giữ đồ thị tổng cả phiên. Phát lại chạy trong đoạn đang chọn; đồ thị tổng biểu diễn toàn bộ phiên lịch sử đã lưu, còn biểu đồ chính hiện dần đến vị trí phát. Bảng giá, sổ lệnh và cảnh báo bên ngoài giữ nguồn đối chiếu riêng.

Khi mở Phát lại mà chưa chọn ngày, ứng dụng tự tìm phiên gần nhất có giá đã ghi nhận cho mã đang chọn. Ngày nghỉ hoặc bản kiểm tra kết nối không đẩy phiên thật ra khỏi lựa chọn mặc định. Chọn ngày cụ thể vẫn giữ đúng ngày đó và ghi rõ khi chưa có giá để phát lại. Với 1.517 mã, dự trù khoảng 20–30 GB cho 30 ngày lịch và kho gốc tối đa 2 GB; đây là ngoại suy từ phạm vi cũ, cần đo lại qua phiên đầy đủ trên cả ba sàn. Xem [chính sách lưu dữ liệu](storage_policy.md).

Ngoài giờ, phần so sánh dùng ảnh sổ hợp lệ đã lưu trong phiên, có nhãn và thời điểm rõ. Giá khớp gần nhất có timestamp riêng. Phần chưa có dữ liệu hiển thị “_”; không có banner hoặc thông báo lỗi thiếu dữ liệu trên giao diện. Bộ thu vẫn tự thử lại, dùng cache đúng thời điểm và kiểm tra dữ liệu trước khi tính. Ảnh sổ cũ không phải giá đang có thể giao dịch.

## Dữ liệu

SSI v3 HTTPS cung cấp danh sách mã/ngành/tham chiếu; WebSocket nhận quote/trade/market.flag. Giá là đồng, khối lượng là cổ phiếu. Khi API thành phần trả dữ liệu chưa đúng cấu trúc, dùng danh sách SSI hợp lệ đã lưu và ghi rõ; không tự đổi mã chỉ số thành cổ phiếu hoặc gắn 100 mã thành VN30.

Cache ở data/ssi, lưu riêng ảnh thay đổi, tổng hợp ngày, nến giá và sự kiện gốc. Bản mới không cắt ảnh ở 2.500/ngày hay sự kiện ở 50.000/ngày; áp dụng giữ theo ngày và ngân sách bản tin gốc được mô tả phía trên. Kho cũ vẫn đọc được. API của giao diện là /api/product; các URL nghiên cứu cũ trả 410, hàm nghiên cứu nội bộ chỉ giữ cho kiểm thử.

## Phạm vi tính

Đầu ra chính chỉ dùng chênh giá, độ sâu, tỷ lệ lượng chờ trên các mức thực nhận (tối đa 10 mỗi phía) và ước tính đối ứng/giá bình quân theo quy mô. Bảng sổ ghi số mức thực tế; ảnh cũ chỉ có 3 mức vẫn được giữ đúng phạm vi đã thu. OFI, LQS và Amihud không được tính hoặc xuất trong /api/product và CSV sản phẩm. OFI cần chuỗi sự kiện phù hợp, LQS là điểm ghép chưa hiệu chuẩn, Amihud 5 phút hiện chỉ là biến thể dùng giá trị giao dịch ước tính; chúng không cần thiết cho bộ đầu ra này. Mã phân tích cũ được giữ ngoài luồng sản phẩm để tương thích kiểm thử. Không coi có lượng chờ là chắc chắn khớp được, không ngoại suy các mức giá chưa nhận được, chưa tính phí/thuế hoặc phản ứng thị trường.

Xem [bản rà soát trước](product_review.md) và [hợp đồng SSI](ssi_api_contract.md). Báo cáo học phần sẽ cập nhật sau theo phạm vi sản phẩm. Chạy kiểm thử bằng run_tests.ps1; tests dùng cache/control tạm, không điều khiển bộ thu thật.

Công cụ theo dõi thanh khoản; không phải khuyến nghị đầu tư.

API Tổng quan đọc lịch sử gọn của mã được chọn bằng SQLite JSON, chỉ nạp đầy đủ một ảnh sổ khi cần xếp bảng giá. Không còn mở toàn bộ100mã trong hàng nghìn bản lưu cho mỗi lần tải. Bộ kiểm thử đối chiếu kết quả giữa cách đọc đầy đủ và cách đọc gọn; cache gốc vẫn chỉ đọc. Style sản phẩm được gộp vào product.css để tránh giao diện chỉ tải được một phần; khi chỉnh các tệp CSS nguồn, dựng lại bằng scripts/build_styles.py.
