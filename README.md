# Liquidity · LOPM

Ứng dụng theo dõi thanh khoản cổ phiếu Việt Nam, sử dụng **SSI FastConnect Data v3**. Giao diện tiếng Việt, có chế độ sáng/tối, chạy cục bộ trên máy người dùng.

LOPM giúp xem giá, lượng chờ mua–bán và khả năng đáp ứng một số tiền tham chiếu. Ứng dụng chỉ đọc dữ liệu thị trường. Không cần thông tin tài khoản giao dịch, RSA hay OTP.

## Chức năng

- Theo dõi VN30, VN100 và danh mục cổ phiếu HOSE, HNX, UPCoM do SSI cung cấp; lọc ngành, tìm kiếm và danh sách theo dõi.
- Sổ lệnh tối đa **10 mức thực nhận mỗi phía**, chênh mua–bán, độ dày và ước tính đối ứng theo quy mô.
- Biểu đồ đường, vùng, nến và bậc thang; khối lượng, tham chiếu, BQ phiên SSI, MA20/MA50 tùy chọn. Có thu phóng, kéo chọn khoảng, con trỏ và Mở rộng.
- Cảnh báo điều kiện lượng chờ chưa đáp ứng quy mô hoặc chênh giá vượt ngưỡng.
- Tổng hợp thanh khoản theo ngành, khớp lệnh/thỏa thuận và khối ngoại theo số cổ phiếu khi nguồn có dữ liệu.
- Tải bù lịch sử nến ở nền, lưu dữ liệu cục bộ và Phát lại riêng trong biểu đồ.
- Xuất CSV và tóm tắt HTML mở độc lập. Logo/ảnh doanh nghiệp đi kèm mã nguồn, có bảng nguồn trong tài liệu.

## Yêu cầu

- **Windows 10/11** và **Python 3.10 trở lên**. Các tệp khởi động nhanh và quản lý bộ thu nền được chuẩn bị cho Windows.
- Internet và một cặp **API Key / API Secret của SSI FastConnect Data v3** có quyền dữ liệu phù hợp.
- Dung lượng cho mã nguồn, bộ ảnh doanh nghiệp (khoảng 600 MB) và kho dữ liệu phát sinh khi sử dụng.

Giao diện đã có sẵn CSS và JavaScript; **không cần Node.js để chạy app**. Node.js chỉ dùng khi chạy các kiểm thử JavaScript hoặc dựng lại tài nguyên thiết kế.

Repo không chứa khóa API hoặc dữ liệu giao dịch đã thu trên máy tác giả. Người tải cấu hình SSI của mình. Khi chưa có khóa hoặc chưa nhận được dữ liệu, giao diện giữ `_`; repo không tự cung cấp dữ liệu trực tiếp miễn phí.

## 1. Tải mã nguồn

Trong PowerShell:

```powershell
git clone https://github.com/phunht1690/Liquidity.git
cd Liquidity
```

Hoặc chọn **Code → Download ZIP** trên GitHub, giải nén rồi mở PowerShell tại thư mục có `README.md`, `requirements.txt` và `start.bat`.

## 2. Cài môi trường Python

Kiểm tra phiên bản:

```powershell
py --version
```

Nếu máy không có lệnh `py` nhưng có `python`, dùng `python` thay `py` trong lệnh tạo môi trường bên dưới. Nếu chưa có Python, cài Python 3.10+ rồi mở lại PowerShell.

Ứng dụng dùng môi trường chung tại `%USERPROFILE%\.venv`. Chạy trong thư mục dự án:

```powershell
if (-not (Test-Path -LiteralPath "$env:USERPROFILE\.venv\Scripts\python.exe")) {
    py -m venv "$env:USERPROFILE\.venv"
}
& "$env:USERPROFILE\.venv\Scripts\python.exe" -m pip install -r requirements.txt
```

## 3. Cấu hình SSI

Tạo `.env` nếu chưa có:

```powershell
if (-not (Test-Path -LiteralPath '.env')) {
    Copy-Item -LiteralPath '.env.example' -Destination '.env'
}
```

Mở `.env` bằng trình soạn thảo và điền đúng hai trường của dịch vụ dữ liệu SSI:

```dotenv
SSI_API_KEY=YOUR_SSI_DATA_API_KEY
SSI_API_SECRET=YOUR_SSI_DATA_API_SECRET
```

Giữ `.env` trên máy cá nhân; tệp này đã được loại khỏi Git. Không đưa khóa vào JavaScript, ảnh chụp, báo cáo hoặc commit.

Nếu có một bộ xác thực SSI độc lập thứ hai, có thể điền `SSI_API_KEY_2` và `SSI_API_SECRET_2`. Hai bộ cần có quyền truy cập phù hợp. App dùng một bộ hoạt động và chỉ chuyển dự phòng theo cơ chế lỗi xác thực/quyền truy cập; không đổi key vì một ô thiếu dữ liệu hoặc để bỏ qua giới hạn 429 của SSI.

Tài liệu nguồn: [SSI Developers](https://developers.ssi.com.vn/), [hợp đồng dữ liệu đang dùng](docs/ssi_api_contract.md).

## 4. Khởi động

Mở **`start.bat`**, hoặc chạy:

```powershell
.\start.bat
```

Dashboard mở tại **[http://127.0.0.1:8765/](http://127.0.0.1:8765/)**. Máy chủ Python và bộ thu SSI chạy nền. Mở nhiều lần dùng lại cùng bộ thu.

Lần đầu, dữ liệu hiện tại được ưu tiên; lịch sử nến và các đường giá nhỏ được bổ sung dần qua hàng đợi chung. Có danh mục cổ phiếu chưa có nghĩa mọi mã đã nhận đủ giá/sổ ngay lập tức. Xem **Dữ liệu & cách dùng → Dữ liệu** để theo dõi độ phủ.

Muốn đổi cổng hoặc kiểm tra lỗi trực tiếp trong terminal:

```powershell
& "$env:USERPROFILE\.venv\Scripts\python.exe" -m src.app.launcher --port 8876
# Chạy trực tiếp, dừng bằng Ctrl+C:
& "$env:USERPROFILE\.venv\Scripts\python.exe" -m src.app.server --port 8876
```

Chọn một trong hai cách trên; tránh chạy hai máy chủ cùng cổng. Địa chỉ tương ứng là `http://127.0.0.1:8876/`.

## 5. Cách sử dụng

### Tổng quan

Chọn tab **Cổ phiếu**, **Sổ lệnh** hoặc **Bảng giá** để xem từng nội dung riêng. Tab giữ mã đang chọn, bộ lọc và thiết lập; không cần cuộn qua các phần còn lại. Có thể dùng phím trái/phải khi đang chọn thanh tab. Các mục có dấu **+ / −** thu mở nhẹ; hiệu ứng tắt theo tùy chọn giảm chuyển động của thiết bị.

Tab **Cổ phiếu** ưu tiên nhận diện mã, thống kê phiên và biểu đồ. Bấm tỷ lệ khối lượng để xem lượng đem so sánh và trung bình 20 phiên; Esc hoặc bấm ra ngoài để đóng. Thẻ **Khối ngoại** nằm dưới biểu đồ, ghi phiên riêng và mở chi tiết mua, bán, room ngoại còn lại. Cách tính và nguồn thống kê của mã nằm trong **Dữ liệu & cách dùng → Hướng dẫn → Ví dụ**. Bốn chỉ tiêu chênh mua–bán, độ dày, bên chờ nhiều hơn và mức đáp ứng quy mô nằm ở đầu tab **Sổ lệnh**.

Tóm tắt thanh khoản toàn phạm vi và nút **Xuất tóm tắt HTML** nằm ở đầu tab **Bảng giá**, phía trên lựa chọn cổ phiếu/theo ngành. Mỗi thẻ giữ mẫu số riêng theo số mã đủ dữ liệu. Bấm thẻ để lọc bảng; mốc sổ và quy mô ghi ngay trong khung tóm tắt.

1. Chọn **Phạm vi → Ngành → Cổ phiếu**. Ngày và thời điểm giá/sổ hiển thị riêng.
2. Trong **Sổ lệnh & quy mô**, kéo thanh, nhập số tiền hoặc chọn mức nhanh để kiểm tra. Kết quả tự tính lại trên ảnh sổ đang xem.
3. Xem chênh mua–bán, giá trị chờ, tỷ lệ chờ hai phía và phần khối lượng có đối ứng theo số tiền đã chọn.
4. Ở **Bảng giá**, chọn xem cổ phiếu hoặc theo ngành. Tìm kiếm, danh sách theo dõi và bộ lọc thanh khoản kết hợp với nhau; CSV xuất mọi mã phù hợp trên tất cả trang.

### Biểu đồ

- Chọn **Nội dung** và **Khoảng xem** trên hàng thao tác nhanh.
- Bấm **Nâng cao** cạnh Khoảng xem để đổi kiểu biểu đồ, mỗi nến/điểm và các đường hiển thị. Mặc định có giá, khối lượng và tham chiếu khi có dữ liệu.
- **Mở rộng** để dùng đồ thị tổng kéo chọn thời gian; kéo hai mép vùng chọn hoặc kéo vùng sáng để đổi đoạn. Thu nhỏ giữ nguyên đoạn đã chọn.
- Rê chuột xem số, bấm để ghim; Ctrl + cuộn để thu phóng. Nút **Toàn khoảng** xuất hiện khi đang cắt đoạn.
- MA20/MA50 chỉ dùng khi đủ số nến; BQ phiên SSI chỉ có ở những mốc thực sự đã thu. Nguồn, ngày và độ đầy đủ nằm tại **Nâng cao → Nguồn & tình trạng dữ liệu**.
- **Phát lại** chọn ngày trong kho đã ghi nhận và phát từng bản. Chức năng này chỉ thay đổi biểu đồ; bảng giá và sổ bên ngoài có nguồn đối chiếu riêng.

### Cảnh báo, dữ liệu và xuất file

- **Cảnh báo:** xem mã có chênh giá vượt ngưỡng hoặc thiếu lượng chờ cho quy mô đang chọn; bấm xem để tới sổ tương ứng. Đây là điều kiện quan sát, không phải dự báo giá.
- **Dữ liệu & cách dùng:** phạm vi tại Độ phủ có lựa chọn riêng; xem số mã đã nhận giá, nhận sổ và có sổ dùng được. Tab Hướng dẫn giải thích các bước và chỉ tiêu.
- **Xuất CSV:** bảng số liệu theo bộ lọc. **Xuất tóm tắt HTML:** bản tổng hợp phạm vi/ngành, có thời điểm nguồn và có thể mở độc lập.
- Nút **Sáng/Tối** đổi giao diện và lưu lựa chọn trong trình duyệt.

## Bộ thu nền và lưu dữ liệu

Đóng tab web hoặc cửa sổ khởi động vẫn tiếp tục thu. Máy cần bật, không ngủ và có mạng. Tắt máy sẽ dừng thu.

Trong PowerShell tại thư mục dự án:

```powershell
.\manage_background.ps1 -Action Status
.\manage_background.ps1 -Action Start
.\manage_background.ps1 -Action Stop
# Tùy chọn chạy sau khi đăng nhập Windows:
.\manage_background.ps1 -Action EnableAutostart
.\manage_background.ps1 -Action DisableAutostart
```

Nếu PowerShell không cho chạy tệp `.ps1`, có thể dùng trực tiếp các lệnh Python tương ứng:

```powershell
& "$env:USERPROFILE\.venv\Scripts\python.exe" -m src.app.background --status
& "$env:USERPROFILE\.venv\Scripts\python.exe" -m src.app.launcher --background
& "$env:USERPROFILE\.venv\Scripts\python.exe" -m src.app.background --stop
& "$env:USERPROFILE\.venv\Scripts\python.exe" -m src.app.background --install-autostart
& "$env:USERPROFILE\.venv\Scripts\python.exe" -m src.app.background --remove-autostart
```

Kho tự tạo dưới `data/`, không nằm trong Git:

- Ảnh đã thu phục vụ Phát lại: mặc định **30 ngày lịch**.
- Bản tin gốc: tối đa **7 ngày**, ngân sách mặc định **2 GB**; có thể dọn ngày cũ sớm hơn khi đầy.
- Nến 5 phút/ngày của 30 ngày lịch được tải bù khi nguồn cho phép và dùng lại từ cache.
- Sổ lệnh và giao dịch chi tiết chỉ có cho những khoảng bộ thu thực sự hoạt động. Nến lịch sử không tái tạo được sổ lệnh trước lúc chạy app.

Dung lượng phát sinh tùy số mã và thời gian thu. Chi tiết: [chính sách lưu trữ](docs/storage_policy.md), [thu nền và tải bù](docs/background_collection.md).

## Khi chưa thấy dữ liệu

| Hiện tượng | Cách kiểm tra |
| --- | --- |
| Không mở được app | Kiểm tra Python 3.10+, môi trường `%USERPROFILE%\.venv` và đã cài `requirements.txt`; thử lệnh chạy trực tiếp ở trên. |
| Giao diện có nhiều `_` | Kiểm tra `.env`, quyền FastConnect Data của tài khoản và kết nối Internet; xem độ phủ và thời điểm tại tab Dữ liệu. |
| Key hợp lệ nhưng app chậm hoặc ngừng nhận dữ liệu | Kiểm tra `/api/health`: bộ thu có chạy, WebSocket có kết nối và lần nhận cuối có tăng không. App giới hạn hai truy vấn lịch sử nặng chạy cùng lúc, gộp lượt tải trùng và tự đóng các kết nối SQLite sau khi dùng. Xem [ghi nhận khôi phục kết nối](docs/ssi_connection_recovery.md). |
| Lịch sử/đường nhỏ chưa đủ | Lần đầu app tải lần lượt ở nền; xem tiến độ tải bù và giữ bộ thu chạy. |
| Thị trường đang nghỉ | App hiển thị cache đã có, ghi đúng ngày phiên và thời điểm; không làm mới nhãn thời gian của dữ liệu cũ. |
| BQ phiên bị ngắt hoặc MA50 không bật được | BQ chỉ có các mốc đã ghi; MA50 cần tối thiểu 50 nến. Rê vào tùy chọn để xem giải thích. |
| Chưa có tỷ lệ khối lượng 20 phiên | App cần đủ 20 phiên có cùng các mốc nến để đối chiếu; số phiên đã có được hiển thị cạnh kết quả. |
| Sau cập nhật vẫn thấy giao diện cũ | Tải lại bằng Ctrl + F5. |

Nhật ký cục bộ nằm trong `data/logs/`. Khi chia sẻ chẩn đoán, chỉ gửi phần cần thiết và che thông tin riêng.

## Kiểm thử và phát triển

Chạy Python tests từ thư mục gốc:

```powershell
& "$env:USERPROFILE\.venv\Scripts\python.exe" -m pytest -q -p no:cacheprovider
```

Nếu có Node.js, chạy các nhóm kiểm thử JavaScript:

```powershell
Get-ChildItem .\tests\*.test.cjs | ForEach-Object {
    node $_.FullName
    if ($LASTEXITCODE -ne 0) { throw "Kiểm thử JavaScript thất bại: $($_.Name)" }
}
```

Sau khi sửa CSS nguồn, dựng lại stylesheet:

```powershell
& "$env:USERPROFILE\.venv\Scripts\python.exe" scripts/build_styles.py
```

Kiểm thử dùng fixture tổng hợp và thư mục tạm; không cần cung cấp khóa SSI thật cho bài test. Xác nhận kết nối thị trường thực tế cần quyền API của người sử dụng.

```text
src/app/          Máy chủ HTTP, giao diện và quản lý chạy nền
src/data/         SSI, cache, lịch sử và tính thanh khoản
config/           Cấu hình số tiền, phạm vi và lưu trữ
tests/            Kiểm thử Python/JavaScript
docs/             Hướng dẫn và đối chiếu dữ liệu
design_reference/ HTML/ảnh thiết kế ROMER gốc
report/           Đề cương báo cáo
.env.example      Mẫu cấu hình, không chứa khóa
```

## Tài liệu và nguồn

- [Ghi chú triển khai chi tiết](docs/development_notes.md)
- [SSI API](docs/ssi_api_contract.md) · [Dữ liệu bổ sung](docs/liquidity_extensions.md)
- [Cách trình bày biểu đồ](docs/chart_layout.md) · [Tóm tắt và so sánh ngành](docs/liquidity_brief.md)
- [Nguồn logo/ảnh doanh nghiệp](docs/company_media_coverage.md)

Các phép ước tính dựa trên mức chờ SSI thực sự cấp; lượng đang chờ có thể thay đổi và chưa đảm bảo khớp được. Chỉ tiêu hiện tại và dữ liệu tổng hợp phiên trước có ngày riêng. Ảnh và nhận diện doanh nghiệp có ghi nguồn; quyền đối với tài nguyên của bên thứ ba thuộc chủ sở hữu tương ứng.

LOPM là công cụ theo dõi và đối chiếu thanh khoản, không phải khuyến nghị đầu tư.
