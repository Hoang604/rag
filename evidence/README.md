# Bằng chứng số liệu

Mọi con số trong `BAO_CAO_TIEN_DO_SPRINT2.md` và trong kịch bản bảo vệ đều phải
truy được về một file ở đây, hoặc về một lệnh chạy lại được. Thư mục này tồn tại
vì trước đó toàn bộ output nằm trong thư mục tạm của phiên làm việc — hết phiên
là mất, và một con số không kiểm lại được thì không khác gì một con số bịa.

## Ánh xạ khẳng định → bằng chứng

| Khẳng định | File | Lệnh sinh lại |
| :--- | :--- | :--- |
| Bench 12.241 truy vấn, Hit@1 79,3% | `bench12k.txt` | `uv run python scripts/qa_bench.py <suite>` |
| Bench 2k **không** rerank: 79,3 / 90,2 / 93,0 | `bench2k_plain.txt` | `uv run python scripts/qa_bench.py <suite2k>` |
| Bench 2k **có** rerank: 86,4 / 94,0 / 95,1 | `bench2k_rr3.txt` | `... --rerank 10` |
| Bảng reranker 4 tập, 2 mức chấm | `rerank_sweep.txt` | `uv run python scripts/rerank_sweep.py` |
| Quét embedding 3 model | `embedding_sweep.txt` | `uv run python scripts/embedding_sweep.py` |
| Overlay bật/tắt, 0/30/60% sai | `overlay_eval.txt` | `uv run python scripts/overlay_eval.py --error-rates 0.0 0.3 0.6` |
| Tập niêm phong 80 câu: 80,0 / 92,5 | `holdout80.txt` | `uv run python scripts/qa_bench.py tests/fixtures/qrels_holdout.jsonl --rerank 10` |

## Chưa có file, cần sinh lại

| Khẳng định | Lệnh |
| :--- | :--- |
| Bảng baseline 5 chế độ (§2.1) | `uv run python scripts/baselines.py` và `--strict` |
| Bảng trajectory eval (§2.2) | `uv run python scripts/trajectory_eval.py` |
| Độ trễ 207ms / ~1.300ms và thông lượng 10,29 / 1,95 req/s | đo qua `POST /api/search`, chưa có script cố định |

## Con số đến từ suy đoán, không từ đo

Ghi riêng để không lẫn với phần trên:

- **Bảng tiến độ 80/118 ngày-người (§8).** Đây là **ước lượng của tôi** về mức
  hoàn thành từng hạng mục so với bảng công sức trong kế hoạch, không phải một
  phép đo. Nó có thể lệch và nên được đọc như một đánh giá chủ quan.

## Cảnh báo khi đọc các con số thời gian

Các số liệu về **thời gian chạy** trong phiên này không đáng tin cậy để so sánh
giữa các model hay cấu hình, vì nhiều tác vụ nặng CPU chạy chồng lên nhau. Một
ví dụ cụ thể: `vietnamese-sbert` mất hơn một tiếng để nhúng corpus trong khi đo
riêng nó chỉ cần ~14 phút — chênh lệch đó là do tranh CPU, không phải do model.

Số liệu về **chất lượng** (Hit@k, MRR) không bị ảnh hưởng bởi việc này.
