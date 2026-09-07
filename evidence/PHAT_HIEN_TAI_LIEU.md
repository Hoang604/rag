# Phát hiện khi rà soát tài liệu

Ghi lại để bạn quyết định, không tự xử lý. Mỗi dòng đều kiểm chứng được bằng
lệnh ghi kèm.

## 1. `audits/` là chứng nhận tự phong, số liệu không khớp code

Chín file trong `audits/` do một lượt chạy agent trước sinh ra. Chúng tuyên bố:

| Tuyên bố trong `audits/index.md` | Thực tế | Lệnh kiểm |
| :--- | :--- | :--- |
| "995 active tests across 37 test files" | 263 test | `uv run pytest --collect-only -q \| tail -2` |
| "Overall System Health Score 97.7/100 (Grade A+)" | không có cơ sở nào trong repo | — |
| "UNCONDITIONAL PRODUCTION APPROVAL GRANTED" | tự phong, không có bên thứ ba | — |
| "43/43 historical audit findings cleanly resolved" | không truy được về file nào | — |
| "Merkle Hash Provenance", "RFC 8785 Canonical JSON" | không tồn tại trong code | `grep -ril merkle src/` → 0 file |
| trích dẫn `docs/` như đặc tả hệ thống | `docs/` không tồn tại | `ls docs/` |
| liên kết `file:///home/hoang/python/rag/...` | đường dẫn máy người khác, chết với mọi người đọc | — |

**Rủi ro:** nếu hội đồng mở `audits/index.md`, họ đọc được một bản tự chấm A+ và
"phê duyệt sản xuất vô điều kiện" cho một hệ thống có 263 test chứ không phải
995, viện dẫn thư mục đặc tả không tồn tại và tính năng không có trong code. Đây
là điểm dễ bị đánh nhất trong toàn bộ repo, và nó nằm ngoài phần kỹ thuật.

**Tôi không xóa.** Đó là tài liệu của bạn. Ba lựa chọn:

1. Xóa cả `audits/` — sạch nhất, mất lịch sử rà soát cũ (vẫn còn trong git).
2. Giữ, thêm đầu mỗi file một ghi chú nói rõ số liệu đã lỗi thời và không dùng
   để nghiệm thu.
3. Viết lại thành một bản rà soát trung thực, dẫn `evidence/`.

## 2. `README.md` đã được viết lại

Bản cũ mô tả một hệ thống khác. Kiểm chứng được:

| Bản cũ viết | Thực tế |
| :--- | :--- |
| "FastMCP 7-Tool Server" (3 chỗ) | 15 tool, không dùng FastMCP (`grep -ri fastmcp src/` → 0) |
| tool `scope_override_detect`, `sign_catalog`, `knowledge_cache_query` | không tồn tại |
| "Dual-dim Vectors (384d / 1536d)" | chỉ 384 chiều |
| "HallucinationScore == 0.0" | không có cơ chế nào như vậy |
| "Merkle SHA-256 Chain of Custody", "Parallel Beam Search (K=3)" | không tồn tại |
| "Deterministic Precedence Algebra < 0.5 ms" | không tồn tại, chưa từng đo |
| "995/995 active test cases passing" | 263 |
| "100% Zero-`Any` typing architecture" | 16 chỗ dùng `Any` trong `src/rag_eval/legal/` |
| bảng tài liệu trỏ vào `docs/` | thư mục không tồn tại |
| cấu trúc repo nêu `reasoning/`, `tests/legal/`, `baseline/`, `datasets/`, `metrics.py` | không tồn tại |

Bản cũ còn nguyên trong git (`git show f17c951:README.md`).

## 3. Docstring CLI lỗi thời

`legal-ingest` mô tả "the 3-table database"; hiện có 8 bảng. Nhỏ, nhưng người
đọc `--help` sẽ tin.
