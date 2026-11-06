# Tài liệu

Tổng quan hệ thống, kiến trúc, cài đặt và cấu hình nằm ở [`../README.md`](../README.md);
quy ước làm việc, cách chạy đánh giá và cấu trúc mã nằm ở [`../AGENTS.md`](../AGENTS.md).

## Vì sao không có thư mục `audits/` và `experiments/`

Cả hai từng được theo dõi trong Git và nay đã bị bỏ theo dõi (vẫn còn trên máy, chỉ
không đẩy lên kho mã nữa):

- **`audits/`** do một lượt rà soát tự động sinh ra. Một số kết luận trong đó đã bị các
  phép đo về sau phủ định, nên để nguyên trên một kho mã công khai thì người đọc dễ
  tưởng đó là kết quả đã được kiểm chứng.
- **`experiments/`** chứa 65 báo cáo từng vòng lặp của một quy trình dò tham số. Đó là
  nhật ký làm việc, không phải tài liệu.

## Tài liệu cũ đã gỡ

Đề cương (`PROPOSAL.md`), thư mục luận văn `thesis/` và các tài liệu cũ trong `docs/`
(`final_report.md`, `demo.md`, `eval_suite.md`, `bay-thuong-gap.md`) đã được gỡ khỏi
kho mã vì không còn khớp với hệ thống hiện tại. Có thể lấy lại từ lịch sử Git.
