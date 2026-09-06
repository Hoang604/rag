# Hệ thống truy hồi và RAG cho Luật Giao thông đường bộ Việt Nam

Truy hồi điều khoản pháp luật giao thông đường bộ: tìm đúng Điều, Khoản, Điểm
áp dụng cho một tình huống, có hiệu lực tại một thời điểm, và trả về nguyên văn
kèm địa chỉ trích dẫn. Hệ thống phục vụ qua một MCP server (JSON-RPC 2.0 trên
stdio) và một giao diện web cho người thẩm định.

> Mọi con số trong tài liệu này đều truy được về một file trong
> [`evidence/`](evidence/README.md) hoặc về một lệnh chạy lại được. Phần
> [Chưa có](#chưa-có) liệt kê những gì hệ thống **không** làm.

---

## Hệ thống thực sự gồm những gì

| Thành phần | Hiện trạng |
| :--- | :--- |
| MCP server | JSON-RPC 2.0 trên stdio, **15 tool**: 6 truy hồi, 8 dàn dựng (staging), 1 ghi metadata |
| Lưu trữ | PostgreSQL 16, **8 bảng**: `documents`, `chunks`, `graph_edges`, `annotations`, `overlay_weights`, `overlay_active`, `token_df`, và `schema_migrations` do trình di trú tự tạo |
| Chỉ mục | `pgvector` HNSW (384 chiều), `ltree` cho đường dẫn phân cấp, `pg_trgm`, `tsvector`/GIN với cấu hình `vietnamese_legal` |
| Nhúng | `intfloat/multilingual-e5-small`, 384 chiều, tiền tố bất đối xứng `query:` / `passage:` |
| Chia văn bản | CPHC — chunk giữ nguyên văn, mang theo tiền tố ngữ cảnh của tổ tiên trong cây |
| Hợp nhất xếp hạng | RRF, `k=60`, trộn nhánh dense và nhánh full-text |
| Xếp hạng lại | Cross-encoder `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`, pool 10, mặc định **bật** |
| Từ chối trả lời | Hai tín hiệu: không có từ khóa nào khớp → `none`; cosine < 0,86 → cảnh báo `low` |
| Di trú DDL | 18 file trong `src/rag_eval/legal/db/sql/`, tất cả idempotent |
| Giao diện | FastAPI + Vite/React cho người thẩm định |
| Kiểm thử | 237 test pytest, 63 test Playwright end-to-end |

Corpus hiện tại: **7.112 chunk**, trong đó 5.571 còn hiệu lực.

---

## Kết quả đo

Chấm ở hai độ mịn khác nhau vì chúng trả lời hai câu hỏi khác nhau: đúng **Điều**
là "có tìm ra điều luật không", đúng **Khoản/Điểm** là "có trích dẫn chính xác
không". Con số dưới đây ở mức Điều.

| Tập | n | Hit@1 | Hit@3 | Hit@5 | File |
| :--- | ---: | ---: | ---: | ---: | :--- |
| Toàn bộ, không rerank | 12.155 câu có đáp án | 79,3% | 89,5% | 92,6% | `evidence/bench12k.txt` |
| Mẫu 2k, không rerank | 1.980 | 79,3% | 90,2% | 93,0% | `evidence/bench2k_plain.txt` |
| Mẫu 2k, có rerank | 1.980 | **86,4%** | 94,0% | 95,1% | `evidence/bench2k_rr3.txt` |
| Tập niêm phong | 80 | 80,0% | 92,5% | 92,5% | `evidence/holdout80.txt` |
| Tập phủ tài liệu mỏng | 113 | 82,3% | — | 85,8% | `evidence/coverage113.txt` |

Tập niêm phong chưa từng được dùng để chọn tham số. Khoảng cách hẹp giữa Hit@1
và Hit@5 trên tập phủ (82,3 → 85,8) cho biết phần sai còn lại là **không truy
hồi được**, không phải xếp hạng sai — rerank không chữa được loại lỗi đó.

---

## Chạy thử

```bash
# 1. PostgreSQL 16 + pgvector
docker compose up -d

# 2. Cấu hình
cp .env.example .env

# 3. Di trú DDL (tạo 8 bảng, index HNSW, stored procedure)
uv run rag-eval legal-migrate

# 4. Nạp corpus
uv run rag-eval legal-bootstrap && uv run rag-eval legal-promote

# 5. MCP server trên stdio
uv run rag-eval legal-server

# 6. Giao diện thẩm định
uv run rag-eval ui
```

`uv run rag-eval --help` liệt kê toàn bộ lệnh.

---

## Kiểm thử và chất lượng

```bash
./scripts/check.sh     # ruff + ty + pytest
make test              # 237 test pytest
cd frontend && npx playwright test   # 63 test end-to-end
```

Sinh lại số liệu đánh giá: xem bảng lệnh trong
[`evidence/README.md`](evidence/README.md).

---

## Chưa có

Ghi ra để không ai đọc tài liệu này rồi tưởng hệ thống làm được:

- **Không có lớp sinh câu trả lời.** Hệ thống truy hồi và trích dẫn điều khoản;
  nó không viết văn bản tư vấn.
- **Không có bảo đảm nào về sai số bịa.** Cơ chế duy nhất là từ chối trả lời khi
  không có từ khóa nào khớp, đo được 25/25 câu vô nghĩa và 0/408 câu thật báo
  nhầm. Đó là một tín hiệu, không phải một bảo đảm.
- **Chưa có thẩm định bởi chuyên gia pháp lý.** Bộ phiếu mù 60 câu đã dựng sẵn
  (`evidence/human_eval_sheet.html`) nhưng chưa ai điền.
- **Overlay học từ phản hồi chưa kết luận.** Đã cài đủ cơ chế, mặc định tắt; hiệu
  quả đo được nằm trong nhiễu (`evidence/overlay_eval.txt`).
- **Không đa ngôn ngữ.** Chỉ tiếng Việt, kể cả truy vấn không dấu.
- **Số đo thời gian chạy trong `evidence/` không so sánh được giữa các cấu hình**,
  vì nhiều tác vụ nặng CPU đã chạy chồng nhau khi đo. Số chất lượng không bị ảnh
  hưởng. Dùng `scripts/latency_bench.py` để đo lại trên máy rảnh.

Thư mục `audits/` là tài liệu do một lượt chạy agent trước sinh ra. Các con số
trong đó (995 test, điểm 97,7/100, "UNCONDITIONAL PRODUCTION APPROVAL") **không
khớp với code hiện tại** và không nên dùng làm căn cứ nghiệm thu.

---

## Cấu trúc

```text
rag/
├── evidence/          # Output đo lường + ánh xạ khẳng định → file → lệnh
├── scripts/           # Sinh câu hỏi, benchmark, quét model, dựng qrels
├── src/rag_eval/
│   ├── cli.py         # CLI (Typer)
│   └── legal/
│       ├── console.py     # Buộc stdout về UTF-8 cho entry point
│       ├── db/            # 18 file DDL, connection pool, batch loader
│       ├── eval/          # smoke runner, đánh giá quỹ đạo agent
│       ├── ingestion/     # Parser AST, chunker CPHC, graph linker, facet
│       ├── mcp/           # MCP stdio server + 15 tool
│       ├── retrieval/     # Cross-encoder, lexicon mở rộng, overlay, annotation
│       ├── web/           # FastAPI cho giao diện thẩm định
│       └── schemas.py     # Model Pydantic v2
├── frontend/          # Vite/React + Playwright
├── tests/             # 237 test pytest, fixture qrels
├── compose.yaml       # PostgreSQL 16 + pgvector
└── pyproject.toml
```
