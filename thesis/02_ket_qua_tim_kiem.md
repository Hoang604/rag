# Kết quả thực nghiệm: tìm kiếm (trả lời CH2)

## Thiết lập

- **Kho văn bản:** 14 văn bản, 6.775 đoạn, nạp từ snapshot của repo.
- **Bộ đánh giá:** `data/eval/retrieval.jsonl`, gồm 715 câu: tập dev 592 câu, dùng khi phát triển; tập holdout 123 câu, chỉ dùng để kiểm tra cuối.
- **Đầu vào mỗi câu:** lời gọi `search` đầu tiên mà agent viết cho câu hỏi đó. Chấm trên lời gọi chứ không trên câu hỏi thô, vì người dùng không tự gọi công cụ.
- **"Tìm thấy":** điều khoản đáp án (hoặc một điều khoản nằm dưới nó) xuất hiện trong kết quả.
- **Hit@k:** đáp án nằm trong k kết quả đầu. **MRR:** trung bình nghịch đảo thứ hạng của đáp án.
- **Mô hình embedding:** Qwen3-Embedding-0.6B, cắt còn 512 chiều.
- **Thời gian:** gồm tạo vector câu hỏi trên CPU và truy vấn DB, chạy lần lượt từng câu.
- **Kiểm định ý nghĩa thống kê:** kiểm định McNemar chính xác, ghép cặp trên cùng 715 câu.
- **Kiểm tra công cụ đo:** công cụ đo cho ra đúng kết quả của lệnh chính thức `legal-eval` (dev 553/592, holdout 120/123, khớp đến từng nhóm).

## Bảng so sánh

| # | Cấu hình | Dev tìm thấy | Holdout tìm thấy | Dev Hit@1 / Hit@5 / MRR | Holdout Hit@1 / Hit@5 / MRR | Thời gian p50 / p95 (ms) |
| :-- | :-- | --: | --: | --: | --: | --: |
| 1 | Chỉ vector (có prompt câu hỏi) | 83,8% | 86,2% | 50,0 / 78,4 / 0,617 | 56,9 / 83,7 / 0,673 | 364 / 515 |
| 1b | Chỉ vector, không prompt | 81,8% | 87,0% | 47,6 / 74,8 / 0,586 | 52,8 / 79,7 / 0,633 | 278 / 399 |
| 2 | Chỉ BM25 | 88,7% | 92,7% | 57,8 / 80,9 / 0,681 | 61,8 / 88,6 / 0,734 | 50 / 85 |
| 3 | Chỉ `ts_rank` (bản cũ) | 67,2% | 69,9% | 13,7 / 45,8 / 0,275 | 16,3 / 50,4 / 0,286 | 38 / 78 |
| 4 | Vector + BM25 (RRF k = 20), không tìm nguyên văn | 91,0% | 95,1% | 59,3 / 82,6 / 0,695 | 63,4 / 88,6 / 0,742 | 406 / 573 |
| 4b | Vector + `ts_rank`, k = 60, không prompt (như bản cũ) | 87,2% | 91,1% | 54,7 / 80,2 / 0,655 | 60,2 / 86,2 / 0,720 | 312 / 460 |
| **5** | **Hệ thống đầy đủ** | **93,4%** | **97,6%** | 58,6 / 83,8 / 0,692 | 64,2 / 88,6 / 0,751 | 501 / 690 |
| 6a | 5, bỏ prompt câu hỏi | 92,7% | 96,7% | 56,2 / 84,5 / 0,679 | 64,2 / 89,4 / 0,751 | 414 / 561 |
| 6b | 5, RRF k = 60 | 92,7% | 97,6% | 58,4 / 83,3 / 0,690 | 64,2 / 87,8 / 0,750 | 500 / 678 |
| 6c | 5, tìm nguyên văn xếp theo thứ tự văn bản | 92,7% | 97,6% | 58,6 / 83,8 / 0,692 | 64,2 / 88,6 / 0,751 | 501 / 689 |
| 6d | Hệ thống đầy đủ như trên `main` trước PR #15 | 90,9% | 94,3% | 56,1 / 82,4 / 0,670 | 61,0 / 85,4 / 0,720 | 404 / 562 |

Cột "tìm thấy" của dòng 1–4b là Hit@10. Dòng 5–6d dùng cách chấm của `legal-eval`: tối đa 20 điều khoản, gồm 10 từ tìm lai và tối đa 10 từ tìm nguyên văn. Cột Hit@1 và Hit@5 so trực tiếp được giữa mọi dòng.

## Nhận xét

1. **BM25 thay `ts_rank` là thay đổi lớn nhất.**
   - Chỉ riêng nhánh từ khoá, Hit@1 trên dev tăng từ 13,7% lên 57,8%, tỉ lệ tìm thấy từ 67,2% lên 88,7%: 163 câu tốt lên, 8 câu kém đi, p ≈ 10⁻³⁸.
   - Lý do: `ts_rank` không có IDF, nên từ có mặt ở hầu hết các đoạn ("xe", "giao thông") nặng ngang từ hiếm. Nó cũng không chuẩn hoá độ dài, nên đoạn dài được lợi.
2. **Tìm lai hơn hẳn chỉ dùng vector, nhưng chỉ hơn BM25 một phần.**
   - So với chỉ vector: thêm 64 câu tìm thấy, mất 10 (p ≈ 10⁻¹⁰).
   - So với chỉ BM25: tăng độ phủ (thêm 29, mất 12, p = 0,01), nhưng Hit@1 như nhau (p = 0,38).
   - Lưu ý: lời gọi trong bộ đề là truy vấn agent đã viết lại bằng thuật ngữ luật. Đó là điều kiện thuận lợi cho BM25. Với câu khẩu ngữ người dùng gõ thẳng, kết quả có thể ngược lại (xem Chương 3).
3. **Nhánh tìm nguyên văn chỉ tăng độ phủ.** Thêm 17 câu tìm thấy, không mất câu nào (dev 91,0% lên 93,4%, p ≈ 1,5·10⁻⁵). Toàn bộ nằm ở hạng 11–20, Hit@1 không đổi. Đổi lại tốn thêm khoảng 90 ms truy vấn DB.
4. **Ba lựa chọn nhỏ mỗi thứ chỉ cứu vài câu:**
   - Prompt câu hỏi: Hit@1 tăng (27 câu tốt lên, 13 câu kém đi, p = 0,04), nhưng tốn khoảng 85 ms CPU mỗi câu.
   - RRF k = 20 thay vì 60: thêm 4 câu trên dev (p = 0,125). Đây là hằng số được chọn bằng cách nhìn tập dev.
   - Xếp kết quả tìm nguyên văn theo vector câu hỏi: thêm 4 câu (p = 0,125).
   - Gộp cả PR #15 (từ dòng 6d lên dòng 5): 26 câu tốt lên, 7 câu kém đi (p = 0,001). Số câu trượt trên dev giảm từ 54 xuống 39.
5. **Trên tập holdout, chênh lệch giữa các cấu hình chỉ 1–4 câu.** Với 123 câu, các chênh lệch này riêng lẻ không có ý nghĩa thống kê.

## Mô hình embedding lớn hơn (Qwen3-Embedding-4B)

**Chưa đo được trên thiết lập này.**

- Máy phát triển có GPU 4 GB, không chứa nổi 4B ở fp16 (8 GB trọng số). Chạy trên CPU ước khoảng 77 giờ cho toàn bộ kho.
- Ngày 2/10 có một lần tính vector 4B trên Kaggle, nhưng dùng kho văn bản và các bộ đề cũ (trước khi luồng nạp được viết lại). Kết quả chỉ tìm theo vector, đúng ở hạng 1:
  - dev 76,0%, holdout 76,2%, colloquial 71,3%;
  - coverage 74,3%, tables 40,0%, clause 88,9%.
  
  Khi kết hợp với BM25, 4B cho kết quả gần như 0,6B. Số liệu này **không so trực tiếp được** với bảng trên.
- Muốn có số so sánh được thì phải tính lại vector 4B cho kho hiện tại trên GPU lớn (ví dụ Kaggle), rồi chạy lại đúng các dòng 1, 4 và 5.

## Tái lập

Dữ liệu từng câu, kiểm định ghép cặp và lệnh tái lập nằm ở `phu_luc_ablation_raw.md`. Bản gốc ở `D:\rw\ablation\` (file `per_case.json`, `paired.json`).
