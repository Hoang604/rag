# Bằng chứng số liệu

Mọi con số trong `BAO_CAO_TIEN_DO_SPRINT2.md`, trong `README.md` và trong kịch
bản bảo vệ đều phải truy được về một file ở đây, hoặc về một lệnh chạy lại được.
Thư mục này tồn tại vì trước đó toàn bộ output nằm trong thư mục tạm của phiên
làm việc — hết phiên là mất, và một con số không kiểm lại được thì không khác gì
một con số bịa.

## Ánh xạ khẳng định → bằng chứng

| Khẳng định | File | Lệnh sinh lại |
| :--- | :--- | :--- |
| Toàn bộ, không rerank: Hit@1 79,3% trên **12.155 câu có đáp án** (trong 12.241 câu đã chấm) | `bench12k.txt` | `uv run python scripts/qa_bench.py <suite>` |
| Mẫu 2k **không** rerank: 79,3 / 90,2 / 93,0 | `bench2k_plain.txt` | `uv run python scripts/qa_bench.py <suite2k>` |
| Mẫu 2k **có** rerank: 86,4 / 94,0 / 95,1 | `bench2k_rr3.txt` | `... --rerank 10` |
| Bảng reranker 4 tập, 2 mức chấm | `rerank_sweep.txt` | `uv run python scripts/rerank_sweep.py` |
| Quét embedding **5 model** | `embedding_sweep.txt` | `uv run python scripts/embedding_sweep.py` |
| Độ trễ p50/p95 và thông lượng, đo trên máy rảnh | `latency.txt` | `uv run python scripts/latency_bench.py --n 40 --warmup 3 --concurrency 8` |
| Overlay bật/tắt, 0/30/60% sai | `overlay_eval.txt` | `uv run python scripts/overlay_eval.py --error-rates 0.0 0.3 0.6` |
| Tập niêm phong 80 câu: 80,0 / 92,5 / 92,5 | `holdout80.txt` | `uv run python scripts/qa_bench.py tests/fixtures/qrels_holdout.jsonl --rerank 10` |
| Tập phủ tài liệu mỏng 113 câu: 82,3 / 85,8 | `coverage113.txt` | `uv run python scripts/qa_bench.py tests/fixtures/qrels_coverage.jsonl --rerank 10` |
| Bảng baseline 5 chế độ, hai mức chấm | `baselines.txt` | `uv run python scripts/baselines.py` và `--strict` |
| Đánh giá quỹ đạo agent, 2 chính sách × 3 tập | `trajectory_eval.txt` | `uv run python scripts/trajectory_eval.py` |
| Phiếu thẩm định mù 60 câu (30 máy chấm đúng, 30 chấm sai) | `human_eval_sheet.html` + `.key.json` | `uv run python scripts/human_eval.py sheet` |

Cách đọc `bench12k.txt`: dòng đầu ghi số câu **đã chấm**, dòng Hit@k tính trên
số câu **có đáp án**. Hai số đó khác nhau và không được dùng lẫn.

## Không còn khẳng định nào chưa có bằng chứng

Mục "chưa đo" trước đây liệt kê độ trễ và thông lượng. Đã đo lại trên máy rảnh
bằng `latency_bench.py`, và **các số đo tay cũ sai theo cả hai hướng**:

| | đo tay (cũ) | đo lại (`latency.txt`) |
| :--- | ---: | ---: |
| p50 không rerank | 207 ms | **135 ms** |
| p50 có rerank | ~1.300 ms | **913 ms** |
| thông lượng không rerank | 10,29 req/s | **9,75 req/s** |
| thông lượng có rerank | 1,95 req/s | **1,40 req/s** |
| mức giảm thông lượng | 5,3 lần | **7,0 lần** |

Độ trễ thực **tốt hơn** con số từng báo, còn thông lượng khi bật rerank **tệ
hơn**. Đó chính là lý do một con số đo tay không dùng được: nó không sai theo
một chiều đoán trước được.

## Kết quả âm tính, ghi lại vì chúng cũng là kết quả

- **Overlay học từ phản hồi không cho hiệu quả đo được.** Ở `n=80`, cấu hình
  60% phản hồi sai chấm điểm giống hệt cấu hình 0% sai. Nguyên nhân đã ghi
  trong `overlay_eval.txt`: overlay kích hoạt theo đẳng thức tập token, còn
  guard chặt chẽ chặn ở mức chứa 0,8 — một tập cha — nên dưới guard chặt overlay
  không bao giờ có cơ hội thể hiện.
- **Chính sách `verify-answerable` không hơn `top-hit`.** Trên cả ba tập, mọi
  chỉ số trùng khít, chỉ tốn thêm lượt gọi trên tập `dev`
  (`trajectory_eval.txt`). Bước xác minh không mua được gì đo được.
- **Cấu hình đang chạy chỉ thắng dense đơn lẻ ở một ô trong bốn.** Đo lại đầy
  đủ trong `baselines.txt`, Hit@1:

  | | dense | full |
  | :--- | ---: | ---: |
  | `test`, mức Điều | 80,0 | **85,0** |
  | `test`, mức Khoản/Điểm | **75,0** | 70,0 |
  | `qrels200`, mức Điều | **70,0** | 68,0 |
  | `qrels200`, mức Khoản/Điểm | **64,5** | 62,0 |

  Trên tập 200 câu — tập lớn hơn `test` gấp năm lần — dense đơn lẻ thắng ở cả
  hai mức chấm. Đây là kết quả cần trả lời chứ không phải cần giấu: lớp hợp
  nhất và các facet domain hiện chưa chứng minh được giá trị ngoài một ô duy
  nhất.

- **Không được trích cột `tuned`.** Cấu hình `full` đạt 100,0/100,0/1,000 ở đó
  vì đó chính là tập đã dùng để chỉnh tham số. Con số đó không đo được gì.

- **BGE-M3 tốt hơn e5-small đúng 3 câu, ở cả bốn ô.** Trên `test` (n=40) 3 câu
  đọc thành +7,5 điểm; trên `qrels200` (n=200) cùng 3 câu đọc thành +1,5 điểm.
  Script không lưu kết quả từng câu nên **không kiểm định được ý nghĩa thống
  kê**. Giá: nhúng corpus 408s → 5.310s, số chiều 384 → 1024. Quyết định giữ
  e5-small; chi tiết và cách đọc bảng ở cuối `embedding_sweep.txt`.

## Con số đến từ suy đoán, không từ đo

Ghi riêng để không lẫn với phần trên:

- **Bảng tiến độ ngày-người.** Đây là **ước lượng của tôi** về mức hoàn thành
  từng hạng mục so với bảng công sức trong kế hoạch, không phải một phép đo. Nó
  có thể lệch và nên được đọc như một đánh giá chủ quan.

## Cảnh báo khi đọc các con số thời gian

Các số liệu về **thời gian chạy** trong phiên này không đáng tin cậy để so sánh
giữa các model hay cấu hình, vì nhiều tác vụ nặng CPU chạy chồng lên nhau. Một
ví dụ cụ thể: `vietnamese-sbert` mất hơn một tiếng để nhúng corpus trong khi đo
riêng nó chỉ cần ~14 phút — chênh lệch đó là do tranh CPU, không phải do model.

Số liệu về **chất lượng** (Hit@k, MRR) không bị ảnh hưởng bởi việc này.

## Sinh lại được trên Windows

Các lệnh trên từng **sập** khi ghi ra file trên Windows: Python lấy encoding
stdout từ locale khi stdout không phải terminal, và cp1252 không mã hóa được
"tập". `rich` cũng vậy. Đã sửa trong tiến trình
(`src/rag_eval/legal/console.py`), có test cấu trúc quét mọi entry point
(`tests/test_console_encoding.py`) để lỗi không quay lại.

Xem thêm `PHAT_HIEN_TAI_LIEU.md` về các tuyên bố không khớp code trong `audits/`.
