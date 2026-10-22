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

# Đánh giá câu trả lời cuối

`scripts/agent_eval.py` chỉ chấm điều khoản agent trích. Bộ này chấm thứ người dùng đọc trên tab Hỏi Đáp: câu trả lời có nêu đúng mức phạt, số điểm bị trừ, dữ kiện chính, và có từ chối câu ngoài phạm vi không.

## Bộ dữ liệu: `data/eval/answers.jsonl`

81 câu (71 trong phạm vi, 10 ngoài phạm vi) lấy theo câu hỏi người dùng thật (thuvienphapluat, luatvietnam, báo, diễn đàn), khôi phục từ `tests/fixtures/user_questions.jsonl` (bị xoá ở commit 4b81087). Đáp án được tra tay trong văn bản luật, không lấy từ đầu ra của hệ thống. Mỗi dòng:

| Trường | Ý nghĩa |
| :--- | :--- |
| `question`, `in_scope` | câu hỏi; `false` là câu hệ thống phải từ chối (án hình sự, bồi thường dân sự, bảo hiểm thương mại, luật nước ngoài, giá cả) |
| `topic`, `style`, `source` | chủ đề; văn phong câu người dùng gõ (`formal`, `colloquial`, `unaccented`, `typo`, `multi_hop`), tức là đầu vào của agent, không phải của `search`; URL nguồn hoặc `paraphrase` |
| `expected` | các path chấp nhận được; trích một path trong đó, hoặc điều khoản nằm dưới nó, là trích đúng |
| `amounts` | các mốc tiền (đồng) phải có trong câu trả lời |
| `facts` | các dữ kiện phải có; `\|` ngăn các cách viết tương đương |
| `note` | ghi chú về nhãn cho người review |

Nhãn cũ (văn bản, Điều, Khoản, Điểm) được quy về path hiện tại và kiểm tra trên DB: mọi path đều tồn tại, mọi mốc tiền và dữ kiện đều có trong lời văn điều khoản, trừ các câu có `note`:

- u014, u033: số điểm bị trừ nằm ở khoản 16 Điều 6, nhãn cũ thiếu; đã thêm khoản đó vào `expected`, không đổi `amounts`/`facts`.
- u063, u064: Thông tư 12/2025/TT-BCA không còn trong corpus; cùng Điều, Khoản có ở Thông tư 108/2026/TT-BCA.
- u071: Nghị định 100/2019/NĐ-CP không có trong corpus; bỏ target của nó, chỉ chấm mức phạt hiện hành.
- u016, u017, u020: con số nằm trong ô bảng (cột km/h, m), nên chuỗi "60km", "55m" không có nguyên văn trong văn bản; u070: "168" là số hiệu văn bản.

Không câu nào bị bỏ. Đây là bộ đánh giá: câu dùng để curate graph phải khác bộ này, như với `retrieval.jsonl`.

## Cách chấm: `scripts/answer_eval.py`

Chạy đúng đường của `/api/answer` chế độ agent (`answer_with_agent` trong `answer.py`, dùng chung với router): agent gọi tool MCP, backend đọc lại các nguồn được trích, đánh số lại `[#n]`, kiểm tra số liệu và cho agent làm lại một lần nếu có số liệu không bám nguồn.

Câu hỏi chỉ đi vào agent. Agent tự viết mọi lời gọi `search` (query bằng thuật ngữ luật, pattern nguyên văn) theo mô tả tool, như ở `retrieval.jsonl`; không có bước nào đưa câu hỏi thô thẳng vào `search`. Mỗi dòng kết quả lưu `searches`, các lời gọi `search` agent đã viết, và `--report` in số lời gọi mỗi câu cùng số lời gọi dùng nguyên văn câu hỏi.

Câu trong phạm vi **đúng toàn phần** khi: có trích nguồn; trích đúng Điều (`cite_article`); đủ `amounts` (đọc được "4.000.000 đồng", "4–6 triệu", "800 nghìn", "100k", "1,2 triệu"); đủ `facts` (so khớp bỏ dấu, bỏ số 0 đầu, bỏ khoảng trắng trước đơn vị); và grounding đạt. Báo riêng trích đúng Khoản/Điểm (`cite_exact`), từ chối nhầm, thời gian và chi phí. Câu ngoài phạm vi đúng khi không trích nguồn nào hoặc câu trả lời có cụm từ chối ("không tìm thấy", "không có căn cứ", "ngoài phạm vi", ...).

Lỗi của provider (hết hạn mức, CLI báo lỗi, máy chủ MCP không kết nối được, không có JSON kết thúc) được ghi là lỗi, không tính điểm, và chạy lại ở lần sau; gặp lỗi hạn mức thì dừng.

```bash
uv run python scripts/answer_eval.py --budget 25          # cả bộ; nối vào experiments/runs/answer_eval.jsonl, chạy lại thì tiếp tục
uv run python scripts/answer_eval.py --only u001 o001     # vài câu
uv run python scripts/answer_eval.py --report             # chỉ in báo cáo
```

Cần `DATABASE_URL` và `claude` trong PATH. Lần kiểm tra trên 7 câu (2026-10-14): trung bình 0,29 USD và 45 giây mỗi câu, nên cả bộ khoảng 24 USD và 1 giờ (gấp đôi ở câu agent phải làm lại vì số liệu không bám nguồn).

Giới hạn: chấm bằng so khớp chuỗi nên "bốn triệu" bị chấm sai, và câu trả lời có thêm nội dung sai mà vẫn đủ mốc yêu cầu vẫn được tính đúng; 71 câu là mẫu nhỏ, chênh lệch dưới khoảng 8 điểm phần trăm chưa nói lên điều gì; đáp án do một người soạn.
