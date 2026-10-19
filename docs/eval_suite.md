# Đánh giá tìm kiếm

## Bộ dữ liệu: `data/eval/retrieval.jsonl`

Một file duy nhất, 715 câu (592 `dev`, 123 `holdout`), gộp từ 10 bộ fixture cũ, bỏ câu trùng và 41 câu không còn đáp án sau khi viết lại parser (xem `docs/final_report.md`). Mỗi dòng:

| Trường | Ý nghĩa |
| :--- | :--- |
| `question` | câu hỏi của người dùng |
| `query`, `pattern`, `is_regex`, `temporal_violation_date`, `doc_codes` | lời gọi `search` đầu tiên agent viết cho câu hỏi |
| `expected` | các path đáp án; kết quả khớp nếu bằng một path trong đó hoặc nằm dưới nó |
| `split` | `dev` hoặc `holdout` (holdout giữ nguyên thành phần từ các bộ holdout cũ) |
| `note` | ghi chú cho người review về nhãn, nếu có |

## Vì sao chấm trên lời gọi của agent, không trên câu hỏi

Người dùng không gọi tool; agent mới gọi. Agent đọc câu hỏi rồi viết `query` bằng thuật ngữ luật ("vượt đèn đỏ" → "không chấp hành hiệu lệnh của đèn tín hiệu giao thông") và thêm `pattern` là cụm từ nguyên văn. Chấm bằng câu hỏi thô là đo một việc tool không bao giờ phải làm, và chọn mô hình theo thước đo đó sẽ thưởng cho khả năng dịch khẩu ngữ mà agent đã làm sẵn.

Lời gọi được sinh bởi agent chỉ thấy câu hỏi, chỉ dẫn của server MCP (gồm danh mục văn bản) và mô tả tool `search`; không thấy đáp án, repo hay database. Chúng được viết một lần và cố định: sửa lời gọi sau khi thấy điểm là tối ưu thước đo, không phải hệ thống. Lời gọi đo lần gọi đầu tiên; việc agent gọi lại khi kết quả lệch thuộc về `scripts/agent_eval.py`.

Đáp án được quy về path hiện tại từ nhãn cũ (văn bản, Điều, Khoản, Điểm). Câu nào phải định vị lại bằng tay có `note`.

## Cách chấm

Mỗi câu xếp vào nhóm mà điều khoản đáp án rơi vào trong kết quả của `search`: `both` (vừa liên quan về nghĩa vừa chứa `pattern`), `semantic_only`, `verbatim_only`, hoặc `missed`. Tỉ lệ "tìm thấy" là tổng ba nhóm đầu.

## Cách chạy

- UI, tab **Đánh giá tìm kiếm**: lọc, xem, sửa và lưu từng câu; chạy một câu (xem kết quả theo nhóm ngữ cảnh, mỗi điều khoản kèm cách nó khớp (`both`, `semantic_only`, `verbatim_only`), dòng khớp đáp án được tô) hoặc chạy cả bộ (bảng tổng kết theo `dev`/`holdout`).
- `uv run rag-eval legal-eval [--split dev|holdout]`: như nút "Chạy tất cả".
- `uv run python scripts/embedding_sweep.py`: so sánh cấu hình embedding trên cùng lời gọi; vector tính xong được lưu ở bảng `embedding_cache` để lần sau dùng lại.
- `uv run python scripts/agent_eval.py --n 40 --split holdout`: agent thật trả lời cả vòng, chấm theo `expected`, ghép cặp với kết quả lời gọi đầu tiên.
