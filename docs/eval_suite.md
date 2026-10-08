# Bộ đánh giá theo câu hỏi người dùng

Bộ này đo hai thứ trên cùng một bộ câu hỏi: **tìm kiếm** (`hybrid_search` có trả đúng điều khoản không) và **câu trả lời cuối** (thứ người dùng thấy trên tab Hỏi Đáp có đúng không).

## Bộ câu hỏi: `tests/fixtures/user_questions.jsonl`

81 câu, gồm 71 câu trong phạm vi và 10 câu ngoài phạm vi. Câu hỏi được lấy từ những gì người dùng thật hay hỏi, không sinh từ văn bản luật:

- **Nguồn.** Các trang hỏi đáp (thuvienphapluat, luatvietnam), báo (tuoitre, thanhnien, vnexpress, dantri), diễn đàn (voz, xetv) và blog (momo, yadea). Câu lấy gần nguyên văn từ tiêu đề hoặc câu hỏi trên các trang đó có trường `source` là URL. Câu được viết lại theo văn phong diễn đàn có `source` là `paraphrase`.
- **Chủ đề.** Phân bổ theo mức độ được hỏi nhiều: đèn đỏ/đèn vàng, nồng độ cồn, tốc độ, mũ bảo hiểm, điện thoại, chở người, phần đường và làn, dừng đỗ, bằng lái, giấy tờ, xe không chính chủ, trẻ em trên ô tô, điểm GPLX, độ tuổi, biển báo, câu nhiều bước.
- **Văn phong (`style`).** `formal` (15 câu), `colloquial` (36), `unaccented` không dấu (11), `typo` viết tắt kiểu "xm", "ko", "gplx" (5), `multi_hop` cần ghép hai văn bản hoặc so sánh (4).
- **Ngoài phạm vi (`in_scope: false`).** Gồm án tù khi gây tai nạn chết người, bồi thường dân sự, bảo hiểm thương mại, luật nước ngoài, giá xăng, giá xe. Hệ thống phải từ chối các câu này.
- **Trùng lặp.** Không câu nào trùng nguyên văn với 6 bộ `qrels_*` cũ.

### Đáp án

Mỗi đáp án được tra tay trong `data/raw/*.txt`, không lấy từ kết quả tìm kiếm của hệ thống, để không chấm hệ thống bằng chính đầu ra của nó.

- `targets` là danh sách các căn cứ chấp nhận được, ghi đến Điều/Khoản/Điểm, hoặc `path_suffix` với phụ lục QCVN. Câu chưa nói rõ loại xe được chấp nhận cả Điều 6 (ô tô) lẫn Điều 7 (xe máy). Những điểm đã bị NĐ 238/2026 sửa (trẻ em ngồi ghế trước) chấp nhận cả văn bản gốc và văn bản sửa đổi. Với câu hỏi về quy tắc, điều khoản quy tắc trong Luật TTATGT cũng được tính đúng.
- `expected.amounts` là các mốc tiền phạt phải xuất hiện trong câu trả lời. Câu chưa nói loại xe thì câu trả lời phải nêu mức của cả hai loại.
- `expected.facts` là các dữ kiện chính phải có, ví dụ "4 điểm", "12 tháng", "dưới 6 tuổi", "60km". Dấu `|` ngăn các cách viết tương đương.
- Trước khi chạy đã đối chiếu với DB: mọi target đều tồn tại đến đúng mức Khoản/Điểm.

## Cách chấm: `scripts/eval_suite.py`

```
uv run python scripts/eval_suite.py retrieval                 # chấm tìm kiếm, không tốn lượt LLM
uv run python scripts/eval_suite.py answer --mode agent       # chấm câu trả lời qua /api/answer
uv run python scripts/eval_suite.py answer --mode retrieve
uv run python scripts/eval_suite.py report
```

Cần `DATABASE_URL` và `PYTHONPATH=scripts`; chế độ agent cần thêm `claude` trong PATH. Kết quả được ghi nối vào `experiments/runs/eval_*.jsonl`, nên nếu bị ngắt giữa chừng thì chạy lại sẽ tiếp tục từ câu chưa làm. Dùng `--only u001 u002` để chạy một số câu, `--tag` để tách các lần chạy.

### Tìm kiếm

Gọi `hybrid_search` lấy 10 kết quả cho mỗi câu, rồi tính:

- Hit@1, @3, @5, @10 và MRR ở mức Điều;
- tỉ lệ có đúng Khoản/Điểm trong top 5;
- kết quả tách theo văn phong và theo chủ đề.

Với câu ngoài phạm vi, chỉ ghi lại độ tin cậy mà công cụ tìm kiếm trả về.

### Câu trả lời cuối

Bộ chấm gọi đúng endpoint `/api/answer` mà UI dùng, qua `TestClient` của FastAPI. Vì vậy cái được chấm chính là đường đi thật: agent gọi tool, backend đọc lại các nguồn được trích, đánh số lại `[#n]` và kiểm tra số liệu.

Một câu trong phạm vi được tính **đúng toàn phần** khi thoả cả năm điều kiện:

1. Không từ chối: có ít nhất một nguồn được trích.
2. Trích đúng Điều: có một nguồn khớp một target.
3. Đủ các mốc tiền trong `amounts`. Bộ đọc số hiểu các cách viết "4.000.000 đồng", "4–6 triệu", "800 nghìn", "100k", "1,2 triệu".
4. Đủ các dữ kiện trong `facts`. Khi so khớp, bộ chấm bỏ dấu, bỏ số 0 ở đầu ("04 điểm" thành "4 điểm") và bỏ khoảng trắng trước đơn vị ("60 km/h" thành "60km/h").
5. Số liệu bám nguồn (grounding): mọi số tiền và số Điều trong câu trả lời phải có trong các điều khoản được trích.

Ngoài ra bộ chấm báo riêng tỉ lệ trích đúng Khoản/Điểm, tỉ lệ từ chối nhầm và thời gian trả lời.

Một câu ngoài phạm vi được tính đúng khi hệ thống không trích nguồn nào, hoặc câu trả lời có cụm từ từ chối ("không tìm thấy", "chưa có dữ liệu", "ngoài phạm vi", ...).

Nếu provider trả về thông báo hết hạn mức ("session limit", "rate limit"), câu đó được ghi là **lỗi**, không tính vào điểm, và được chạy lại ở lần sau.

### Giới hạn đã biết

- Chấm số tiền và dữ kiện bằng so khớp chuỗi, nên một câu trả lời đúng nhưng diễn đạt quá khác (ví dụ "bốn triệu") sẽ bị chấm sai. Không dùng LLM làm giám khảo, để kết quả lặp lại được và không tốn thêm lượt gọi.
- Câu trả lời có thêm nội dung sai mà vẫn đủ các mốc yêu cầu thì vẫn được tính đúng. Lớp grounding chỉ bắt được trường hợp số liệu không có trong nguồn.
- 71 câu là cỡ mẫu nhỏ: chênh lệch dưới khoảng 8 điểm phần trăm giữa hai lần chạy chưa nói lên điều gì.
- Đáp án do một người soạn. Nên có người thứ hai duyệt lại, nhất là các câu nhiều bước và câu về biển báo.

## Kết quả lần chạy đầu (2026-10-08, DB `rag_legal_main`, Qwen3-0.6B + BM25)

Tìm kiếm, 71 câu trong phạm vi:

| nhóm | n | @1 | @3 | @5 | @10 | MRR | đúng Điểm@5 |
| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| tất cả | 71 | 49,3 | 73,2 | 83,1 | 91,5 | 0,635 | 69,0 |
| colloquial | 36 | 58,3 | 88,9 | 88,9 | 97,2 | 0,733 | 83,3 |
| formal | 15 | 53,3 | 86,7 | 100 | 100 | 0,719 | 73,3 |
| unaccented | 11 | 27,3 | 36,4 | 54,5 | 72,7 | 0,377 | 36,4 |
| typo | 5 | 40,0 | 40,0 | 80,0 | 80,0 | 0,480 | 80,0 |
| multi_hop | 4 | 25,0 | 25,0 | 50,0 | 75,0 | 0,342 | 0,0 |

- Hit@1 trên câu hỏi kiểu người dùng là 49%, thấp hơn nhiều so với 79,5% trên `qrels_dev`. Các bộ cũ được sinh từ chính văn bản nên đánh giá tìm kiếm cao hơn thực tế.
- Lỗi hay gặp nhất là nhầm loại xe: câu về xe máy kéo về Điều 8 (xe máy chuyên dùng) hoặc Điều 9 (xe đạp), vì các điều này dùng cùng cách diễn đạt hành vi.
- Câu không dấu yếu nhất, vì chỉ chạy BM25.
- Với cả 10 câu ngoài phạm vi, độ tin cậy của tìm kiếm đều không ở mức `none`/`low`. Vì vậy chế độ `retrieve` không có tín hiệu nào để từ chối trả lời.

Câu trả lời cuối (chế độ agent) mới chạy thử 7 câu thì hết hạn mức phiên của tài khoản Claude. Cả 7 câu đều đúng, gồm 6 câu trong phạm vi và 1 câu ngoài phạm vi. Mẫu quá nhỏ để kết luận; cần chạy lại cả bộ.
