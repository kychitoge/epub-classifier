# EpubClassifier

EpubClassifier phân tích, phân loại và tổ chức các tiểu thuyết EPUB. Nó xác thực cấu trúc EPUB, trích xuất siêu dữ liệu, phát hiện loại bản dịch và tùy chọn làm phong phú dữ liệu thông qua tìm kiếm web. Kết quả được xuất sang báo cáo có thể đọc được bằng máy móc và con người.

## Yêu Cầu Hệ Thống

- Python 3.8 hoặc mới hơn
- Windows, macOS hoặc Linux
- Tối thiểu 2 GB dung lượng đĩa trống (tùy thuộc vào kích thước thư viện)
- Kết nối Internet (cho các tính năng tìm kiếm web)

## Cài Đặt

1. Giải nén gói triển khai đến vị trí mong muốn.

2. Điều hướng đến thư mục dự án:
   ```
   cd EpubClassifier
   ```

3. Cài đặt các phụ thuộc:
   ```
   pip install -r requirements.txt
   ```

## Cấu Hình

### Tổng Quan config.json

Tệp `config.json` kiểm soát tất cả hành vi của công cụ. Các phần chính:

- **PATHS**: Thư mục đầu vào và đầu ra
  - `INPUT_FOLDER`: Thư mục chứa các tệp EPUB để xử lý (mặc định: `books`)
  - `OUTPUT_BASE_FOLDER`: Thư mục cho kết quả (mặc định: `Output`)
  - `DB_FILE`: Tên tệp Excel đầu ra (mặc định: `master_data.xlsx`)
  - `LOG_FILE`: Vị trí đầu ra nhật ký (mặc định: `app.log`)
  - `CACHE_DIR`: Thư mục bộ nhớ đệm web/AI (mặc định: `.cache`)

- **AI_ALLOWED**: **Mặc định là `false`** (các tính năng AI bị vô hiệu hóa)
  - Đặt thành `true` chỉ nếu bạn có khóa API hợp lệ và muốn phát hiện bản dịch qua AI
  - Khi `false`, tất cả các lệnh gọi API sẽ bị bỏ qua; phát hiện bản dịch chỉ sử dụng quy tắc tĩnh

- **FEATURES**:
  - `DRY_RUN`: Xem trước các thay đổi mà không sửa đổi tệp
  - `RESUME_ENABLED`: Lưu điểm kiểm tra và tiếp tục từ gián đoạn
  - `CACHE_ENABLED`: Bộ nhớ đệm tìm kiếm web và phản hồi API
  - `HEADLESS_BROWSER`: Sử dụng trình duyệt headless cho tìm kiếm web (cần các phụ thuộc bổ sung)

- **API_KEYS**: 
  - `GOOGLE_API_KEY`: Tùy chọn (chỉ được sử dụng nếu `AI_ALLOWED = true`)
  - `METRUYENCV_COOKIE`: Xác thực tìm kiếm web tùy chọn

- **SYSTEM**:
  - `MAX_WORKERS`: Các luồng xử lý song song (mặc định: 10)
  - `SAVE_INTERVAL`: Tần suất lưu điểm kiểm tra (mặc định: mỗi 20 tệp)

### Ví Dụ Cấu Hình

```json
{
  "AI_ALLOWED": false,
  "PATHS": {
    "INPUT_FOLDER": "C:\\Books\\MyLibrary",
    "OUTPUT_BASE_FOLDER": "C:\\Results",
    "DB_FILE": "master_data.xlsx",
    "LOG_FILE": "processing.log",
    "CACHE_DIR": ".cache"
  },
  "FEATURES": {
    "DRY_RUN": false,
    "RESUME_ENABLED": true,
    "CACHE_ENABLED": true
  }
}
```

## Cách Chạy

### Thử Nghiệm (Chỉ Phân Tích)

Xem trước những gì công cụ sẽ làm mà không sửa đổi bất kỳ tệp nào:

```
python main.py --config config.json --dry-run
```

Đầu ra được ghi vào `OUTPUT_BASE_FOLDER` mà không thực hiện thao tác tệp.

### Chạy Bình Thường

Xử lý các tệp EPUB và tạo báo cáo:

```
python main.py --config config.json
```

### Với Các Tùy Chọn

Tiếp tục từ điểm kiểm tra cuối cùng:
```
python main.py --config config.json
```
(Tiếp tục được bật theo mặc định; sử dụng `--no-resume` để vô hiệu hóa)

Vô hiệu hóa bộ nhớ đệm và buộc gọi web mới:
```
python main.py --config config.json --no-cache
```

Ghi đè tệp cấu hình:
```
python main.py --config /path/to/custom_config.json
```

## Kết Quả Đầu Ra

Xử lý tạo ra các đầu ra sau trong `OUTPUT_BASE_FOLDER`:

### Báo Cáo

- **MachineReport.xlsx**: Chẩn đoán hệ thống toàn diện cho tất cả các tệp được xử lý
  - Kết quả xác thực, nhãn phân loại, điểm số độ tin cậy
  - Dữ liệu làm phong phú web, loại lỗi, siêu dữ liệu đầy đủ
  - Một hàng cho mỗi tệp (thành công và thất bại)

- **HumanReport.xlsx**: Chế độ xem tuyển chọn cho người đọc
  - Chỉ những cuốn sách được phân loại thành công và hợp lệ
  - Cột thân thiện với Việt Nam: Tên truyện (Tiêu đề), Tác giả (Tác giả), Số chương (Số chương)
  - Loại phân loại: "Người dịch" (Bản dịch Con Người) hoặc "máy convert" (Máy)

### Nhật Ký

- **app.log** (hoặc `LOG_FILE` được cấu hình): Nhật ký xử lý chi tiết
  - Dấu thời gian, sự kiện xử lý, cảnh báo, lỗi
  - Hữu ích để khắc phục sự cố và giám sát các lần chạy dài

### Bộ Nhớ Đệm

- **.cache/**: Bộ nhớ đệm tìm kiếm web và phản hồi API
  - Được quản lý tự động; các mục hết hạn sau 30 ngày
  - Xóa để buộc tìm kiếm lại

## An Toàn & Tuân Thủ

**AI bị vô hiệu hóa theo mặc định** (`AI_ALLOWED = false` trong config.json). Khi bị vô hiệu hóa:
- Không có lệnh gọi API Google Generative AI
- Không có phụ thuộc AI bên ngoài được tải vào bộ nhớ
- Phát hiện bản dịch sử dụng quy tắc tĩnh xác định chỉ
- Tuân thủ được duy trì trên tất cả xử lý

**Hành vi xác định**: Tất cả các hoạt động có thể tái tạo được. Chạy lại trên cùng một bộ đầu vào sẽ tạo ra kết quả giống hệt (không bao gồm thay đổi dữ liệu web bên ngoài). Bật chế độ thử nghiệm để xác minh hành vi trước.

**Xử lý dữ liệu**: 
- Đường dẫn tệp được xử lý và siêu dữ liệu được ghi vào báo cáo Excel cục bộ chỉ
- Không có dữ liệu nào được gửi đến các dịch vụ bên ngoài trừ khi `AI_ALLOWED = true` và các tính năng web hoạt động
- Nhật ký chứa thông tin chẩn đoán đầy đủ để kiểm toán

## Các Cạm Bẫy Phổ Biến & Khắc Phục Sự Cố

### Không tìm thấy tệp EPUB

**Vấn đề**: Thông báo "Không tìm thấy tệp EPUB" mặc dù tệp nằm trong thư mục.

**Giải pháp**: Xác minh `INPUT_FOLDER` trong config.json trỏ đến thư mục chính xác. Kiểm tra xem các tệp có phần mở rộng `.epub` (phân biệt chữ hoa chữ thường trên Linux/macOS).

### Điểm kiểm tra ngăn xử lý lại

**Vấn đề**: Thêm tệp mới không xử lý lại các tệp hiện có.

**Nguyên nhân**: Tính năng tiếp tục lưu các điểm kiểm tra. Chỉ các tệp mới/chưa xử lý được phân tích.

**Giải pháp**: Xóa các tệp điểm kiểm tra (tìm trong thư mục bộ nhớ đệm) hoặc sử dụng `--no-resume` để buộc xử lý lại toàn bộ.

### Hết bộ nhớ trên các thư viện lớn

**Vấn đề**: Quá trình bị sập với lỗi bộ nhớ trên 10.000+ tệp EPUB.

**Giải pháp**: Giảm `SYSTEM.MAX_WORKERS` trong config.json (ví dụ: từ 10 xuống 4). Xử lý theo lô bằng cách sử dụng các thư mục đầu vào riêng biệt.

### Lỗi API khi AI_ALLOWED = true

**Vấn đề**: Lỗi từ Google API hoặc tìm kiếm web.

**Nguyên nhân**: Khóa API không hợp lệ, giới hạn tốc độ hoặc phụ thuộc bị mất.

**Giải pháp**: Xác minh `API_KEYS` trong config.json có hợp lệ. Đặt `AI_ALLOWED = false` để bỏ qua tất cả lệnh gọi API. Kiểm tra tệp nhật ký để biết thông báo lỗi cụ thể.

### DRY_RUN hiển thị lỗi nhưng không di chuyển tệp

**Nguyên nhân**: Đây là hành vi chính xác. Chế độ thử nghiệm báo cáo các vấn đề mà không sửa đổi tệp.

**Giải pháp**: Xem xét MachineReport.xlsx để biết lý do lỗi chi tiết. Sửa cấu hình hoặc tệp đầu vào, sau đó chạy mà không cần cờ thử nghiệm.

## Phiên Bản & Giấy Phép

**Phiên bản**: v1.0.0 (Đóng băng: 2026-01-07)

Xem tệp LICENSE để biết các điều khoản cấp phép.
