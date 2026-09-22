# Tài liệu

| Tài liệu | Nội dung |
| :--- | :--- |
| [`demo.md`](demo.md) | Kịch bản demo đầy đủ. Mọi lệnh trong đó đều đã chạy thật và ghi lại đúng kết quả nhận được, kể cả lỗi. Có mục riêng về các điểm khác biệt trên PowerShell. |

Tài liệu kiến trúc, kết quả đo và các quyết định thiết kế nằm ở hai nơi khác:

- [`../README.md`](../README.md) — tổng quan hệ thống, kiến trúc, cài đặt, cấu hình.
- [`../evidence/README.md`](../evidence/README.md) — chỉ mục bằng chứng cho **mọi** con
  số được trích trong tài liệu, cùng các phát hiện đi kèm lý do.

## Vì sao không có thư mục `audits/` và `experiments/`

Cả hai từng được theo dõi trong Git và nay đã bị bỏ theo dõi (vẫn còn trên máy, chỉ
không đẩy lên kho mã nữa):

- **`audits/`** do một lượt rà soát tự động sinh ra. Một số kết luận trong đó đã bị các
  phép đo về sau phủ định, nên để nguyên trên một kho mã công khai thì người đọc dễ
  tưởng đó là kết quả đã được kiểm chứng.
- **`experiments/`** chứa 65 báo cáo từng vòng lặp của một quy trình dò tham số. Đó là
  nhật ký làm việc, không phải tài liệu.

Những gì rút ra được từ hai thư mục đó, nếu đã kiểm chứng lại bằng phép đo, đều được
viết lại trong `evidence/`.
