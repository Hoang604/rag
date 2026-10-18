# Tư liệu đồ án tốt nghiệp

| File | Nội dung | Trạng thái |
| :-- | :-- | :-- |
| `01_cau_hoi_nghien_cuu.md` | Bài toán, 3 câu hỏi nghiên cứu, 3 đóng góp, phạm vi | Bản nháp |
| `02_ket_qua_tim_kiem.md` | Bảng ablation tìm kiếm (715 câu, dev/holdout), kiểm định McNemar | Đủ số liệu, thiếu Qwen3-4B trên kho hiện tại |
| `03_ket_qua_cau_tra_loi.md` | Đo câu trả lời cuối (81 câu), so sánh tìm một lần với agent | Đủ 81/81 câu |
| `04_han_che_va_bai_hoc.md` | Các lần hệ thống hoặc cách đo bị sai, hạn chế còn lại | Bản nháp |
| `05_phan_tich_loi.md` | Phân loại lỗi câu trả lời và các câu tìm kiếm còn trượt | Bản nháp |
| `06_thiet_ke_he_thong.md` | Kiến trúc, luồng dữ liệu, tìm kiếm, agent, công cụ đánh giá, 9 quyết định thiết kế | Bản nháp |
| `07_tong_quan.md` | Tổng quan nghiên cứu liên quan, 44 tài liệu tham khảo | Bản nháp, đã kiểm nguồn của 7 tài liệu từng đánh dấu "cần kiểm tra" |
| `phu_luc_ablation_raw.md` | Báo cáo gốc của lần chạy ablation, lệnh tái lập | Nguyên bản |
| `review/review_sheet.csv`, `review/huong_dan_review.md` | Bảng và hướng dẫn cho người học luật duyệt 81 đáp án | Chờ người duyệt |

Số liệu gốc nằm ở `D:\rw\ablation\` và `D:\rw\int\experiments\runs\answer_eval.jsonl`. Báo cáo LaTeX ở `latex/` (biên dịch bằng image Docker `texlive-thesis`, 68 trang, phần chính 45 trang). Code tương ứng là nhánh `task/thesis-integration` (`main` + PR #15, #16, #17, chưa push).

Còn thiếu cho một đồ án hoàn chỉnh: kết quả duyệt của người học luật, và nếu kịp thì một thử nghiệm nhỏ với người dùng thật.
