# Sổ tay demo

Mọi lệnh trong file này đã được chạy thật trên máy này (Windows 11, PowerShell
5.1.26100) và kết quả in kèm là kết quả thật, không phải mẫu minh hoạ. Chỗ nào
tôi chưa chạy được thì có ghi rõ.

Đường dẫn gốc, dùng cho mọi lệnh dưới đây:

```
d:\Xây dựng hệ thống Information Retriever, RAG trong lĩnh vực Luật Giao thông\rag
```

---

## 0. Đọc một lần trước khi demo

**PowerShell trên máy này là 5.1, không phải 7.** Ba hệ quả, cả ba đều đã làm
tôi mất thời gian:

| Vấn đề | Cách làm đúng |
| :--- | :--- |
| `&&` không phải toán tử phân cách hợp lệ | Dùng `;` |
| Tiếng Việt in ra bị hỏng | Chạy 2 dòng ở mục 0.1 trước |
| JSON trong tham số bị PowerShell bóc mất dấu `"` | Nhân đôi dấu ngoặc kép: `""key""` (mục 4) |

Nếu bạn có Git Bash thì **mọi lệnh JSON dễ hơn hẳn** — quote một nháy đơn là
xong, không phải nhân đôi gì. Chỗ nào khác nhau tôi để cả hai dạng.

### 0.1 Hai dòng bật UTF-8 cho phiên PowerShell

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
```

Thêm dòng này nữa nếu bạn định **ghi output ra file** (`> ket_qua.txt`):

```powershell
$env:PYTHONIOENCODING = 'utf-8'
```

---

## 1. Khởi động (3 lệnh)

```powershell
cd 'd:\Xây dựng hệ thống Information Retriever, RAG trong lĩnh vực Luật Giao thông\rag'

# 1. PostgreSQL 16 + pgvector — cổng 15432
docker compose up -d

# 2. Kiểm tra database đã healthy chưa
docker compose ps
```

Đợi tới khi cột `STATUS` ghi `Up ... (healthy)`:

```
NAME                 IMAGE                    STATUS                 PORTS
rag_legal_postgres   pgvector/pgvector:pg16   Up 3 hours (healthy)   0.0.0.0:15432->5432/tcp
```

```powershell
# 3. Giao diện web
uv run rag-eval ui
```

Lệnh này tự build frontend nếu thiếu `frontend/dist/`, rồi mở trình duyệt ở
**http://127.0.0.1:8000**.

### Chế độ dev (đang chạy sẵn lúc này)

```powershell
uv run rag-eval ui --dev
```

Chế độ này chạy Vite HMR riêng, và **địa chỉ để mở là http://127.0.0.1:5173**,
không phải 8000. Cổng 8000 vẫn phục vụ `/api/*` nhưng `/` trả về **404** vì
không có `dist/` — đây là hành vi bình thường của `--dev`, không phải lỗi.

Kiểm tra nhanh backend còn sống:

```powershell
curl.exe -s http://127.0.0.1:8000/api/health
```

```json
{"status":"OK","database":"CONNECTED","timestamp":"2026-09-07T13:05:26+07:00"}
```

### 1.1 Nếu `rag-eval ui` báo `[Errno 10048]`

```
ERROR: [Errno 10048] error while attempting to bind on address ('127.0.0.1', 8000):
only one usage of each socket address ... is normally permitted
```

Nghĩa là **một backend cũ vẫn đang giữ cổng 8000** — thường là phiên `--dev` mở
từ trước và chưa Ctrl+C. Chú ý dòng ngay trên nó vẫn ghi `Application startup
complete`: frontend đã build xong và app đã nạp model, chỉ riêng bước bind cổng
là thất bại. Không phải lỗi cấu hình.

Xem ai đang giữ cổng:

```powershell
netstat -ano | Select-String ':8000\s.*LISTENING', ':5173\s.*LISTENING'
Get-Process -Id <PID> | Select-Object Id, ProcessName, StartTime
```

Hai cách xử lý, chọn một:

- **Nhanh nhất:** backend cũ vẫn dùng được, cứ **mở http://127.0.0.1:5173**.
  Kiểm bằng `curl.exe -s http://127.0.0.1:8000/api/health` — ra `"status":"OK"`
  là còn tốt.
- **Muốn một cổng duy nhất (8000):** dừng cả tiến trình `python` (uvicorn) và
  `node` (Vite) rồi chạy lại. Lần này không build lại vì `dist/` đã có.

```powershell
Stop-Process -Id <PID python>, <PID node>
uv run rag-eval ui
```

Đừng chạy `uv run rag-eval ui` ở hai cửa sổ cùng lúc — cửa sổ thứ hai luôn
dừng ở đúng lỗi này.

---

## 2. Demo trên UI

Giao diện có ba tab. **Tab tra cứu và tab hỏi đáp dùng được ngay**, không cần
tạo staging session trước.

### Tab "Thử nghiệm truy xuất" — truy hồi thuần, không có model

Đây là phần lõi của hệ thống: nó **trích** điều khoản kèm địa chỉ Điều/Khoản/
Điểm, không viết văn xuôi.

Câu hỏi nên gõ, kèm kết quả thật:

| Gõ vào | Kết quả đúng |
| :--- | :--- |
| `Xe máy vượt đèn đỏ phạt bao nhiêu?` | `168/2024/NĐ-CP` Điều 7 Khoản 7 Điểm c, rerank **+3,46** |
| `Tốc độ tối đa của oto trên đường cao tốc là bao nhiêu?` | `38/2024/TT-BGTVT` Điều 9 Khoản 3 và Khoản 2 |

Câu thứ hai đáng cho hội đồng xem, vì **trước bản sửa nhãn loại xe nó trả về
Điều 8 — điều khoản có tiêu đề ghi rõ "(trừ đường cao tốc)"**. Chi tiết ở §9.1
báo cáo tiến độ.

**Bộ lọc phạm vi** nằm ngay trong tab này (nút mở danh sách văn bản). Mặc định
là toàn corpus; chọn `38/2024/TT-BGTVT` để giới hạn truy vấn trong đúng thông
tư đó. Văn bản hết hiệu lực được ghi nhãn — trong corpus hiện tại chỉ có
`100/2019/NĐ-CP` (hết hiệu lực 31/12/2024).

### Tab "Hỏi Đáp (LLM)" — model viết câu trả lời

Chọn provider ở dropdown cạnh ô nhập. **`claude` và `codex` chạy được**;
`gemini` có CLI nhưng hết hiệu lực xác thực; `antigravity` không có CLI headless
nên không cắm được.

Ba câu nên demo, vì chúng cho ra **ba hành vi khác nhau** — đây là phần thuyết
phục nhất của tab này:

| Gõ vào | Hệ thống làm gì |
| :--- | :--- |
| `Xe máy vượt đèn đỏ phạt bao nhiêu?` | Trả lời **4.000.000 – 6.000.000 đồng**, grounding **xanh** (mọi Điều và mọi con số đều khớp điều khoản đã truy hồi) |
| `Đâm chết người thì bị mấy năm tù?` | Độ tin cậy **`low`**; model **tự nói "Không đủ căn cứ để trả lời"** và chỉ ra corpus không có quy định hình phạt tù |
| `asdkjfh qwoieu zxcvb` | Băng **hổ phách**: "Không gọi model" — `answer_ms = 0`, câu hỏi không được gửi đi |

Điểm cần nói khi demo: câu thứ hai **không** bị hệ thống chặn (`confidence` là
`low`, không phải `none`) — chính **model** từ chối, vì nó chỉ được đưa các điều
khoản giao thông đường bộ. Câu thứ ba thì hệ thống chặn trước, không tốn một
lượt gọi nào.

Bố cục của tab đặt **phán quyết grounding trước đoạn văn**, và các điều khoản
model đã đọc luôn nằm ngay dưới. Cố ý như vậy để chống đúng một hành vi: đọc
đoạn văn rồi không cuộn xuống kiểm.

### Tab soát/sửa (staging)

Cần có staging session mới dùng được. Dropdown chọn văn bản ở header **chỉ hiện
ở tab này** — nó không phải bộ lọc tìm kiếm.

---

## 3. Demo bằng API (không cần UI)

Backend phải đang chạy. Kết quả dưới đây là thật.

### PowerShell

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$body = @{ query = 'Tốc độ tối đa của oto trên đường cao tốc là bao nhiêu?'; limit = 3 } | ConvertTo-Json
$r = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/search' -Method Post `
     -ContentType 'application/json; charset=utf-8' `
     -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
$r.hits | ForEach-Object { "$($_.address) | $($_.doc_code) | rerank=$([math]::Round($_.rerank_score,2))" }
```

```
Điều 9 Khoản 3 | 38/2024/TT-BGTVT | rerank=2.68
Điều 9 Khoản 2 | 38/2024/TT-BGTVT | rerank=1.66
Điều 8 Khoản 1 | 38/2024/TT-BGTVT | rerank=0.78
```

`[System.Text.Encoding]::UTF8.GetBytes($body)` là cần thiết, không phải cho đẹp:
`Invoke-RestMethod` của PS 5.1 gửi body theo ISO-8859-1 và tiếng Việt sẽ tới
server ở dạng hỏng.

**Giới hạn phạm vi** — thêm `doc_codes`:

```powershell
$body = @{ query = 'tốc độ tối đa trên đường cao tốc'; limit = 3; doc_codes = @('38/2024/TT-BGTVT') } | ConvertTo-Json
```

### Danh sách mã văn bản dùng cho `doc_codes`

Lấy từ database, không phải chép tay:

```powershell
docker exec rag_legal_postgres psql -U postgres -d rag_legal -c "SELECT d.doc_code, d.expiration_date, count(*) AS chunks FROM documents d JOIN chunks c ON c.document_id=d.id GROUP BY 1,2 ORDER BY 1;"
```

```
     doc_code      | expiration_date | chunks
-------------------+-----------------+--------
 100/2019/ND-CP    | 2024-12-31      |   1541
 12/2025/TT-BCA    |                 |    321
 151/2024/ND-CP    |                 |    315
 168/2024/ND-CP    |                 |   1110
 184/2025/ND-CP    |                 |    437
 236/2026/ND-CP    |                 |    109
 238/2026/ND-CP    |                 |    103
 38/2024/TT-BGTVT  |                 |     45
 49/VBHN-VPQH      |                 |    670
 55/VBHN-VPQH      |                 |    806
 65/2024/TT-BCA    |                 |     56
 90/VBHN-VPQH      |                 |    729
 QCVN41/2024/BGTVT |                 |    870
```

Lưu ý mã trong database viết **không dấu** (`ND-CP`, không phải `NĐ-CP`). Mã sai
chính tả trả về **rỗng**, không im lặng trả về toàn corpus — cố ý như vậy.

### Gọi tab hỏi đáp qua API

```powershell
$body = @{ query = 'Xe máy vượt đèn đỏ phạt bao nhiêu?'; provider = 'claude'; limit = 5 } | ConvertTo-Json
$r = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/answer' -Method Post `
     -ContentType 'application/json; charset=utf-8' `
     -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
"provider=$($r.provider) abstained=$($r.abstained) confidence=$($r.confidence) grounding=$($r.grounding.ok)"
$r.answer
```

Kết quả thật (mất ~10 giây, phần lớn là chờ CLI):

```
provider=claude abstained=False confidence=high grounding=True
Xe máy không chấp hành hiệu lệnh của đèn tín hiệu giao thông (vượt đèn đỏ):
phạt tiền từ **4.000.000 đồng đến 6.000.000 đồng** [#1].
...
```

Xem provider nào đang cài:

```powershell
curl.exe -s http://127.0.0.1:8000/api/answer/providers
```

```json
[{"name":"claude","label":"Claude Code","installed":true},
 {"name":"codex","label":"Codex","installed":true},
 {"name":"gemini","label":"Gemini CLI","installed":true}]
```

`installed: true` chỉ nói **file có trên máy**, không nói nó dùng được — `gemini`
là đúng trường hợp đó. Chủ ý báo đúng cái đo được thay vì đoán.

---

## 4. Demo MCP server (đây mới là giao diện chính của hệ thống)

Hệ thống được dựng làm **MCP server trên stdio**, tức model nằm ngoài nó: agent
gọi tool, đọc điều khoản, tự viết câu trả lời. UI chỉ là một client.

```powershell
uv run rag-eval legal-server
```

Server đọc JSON-RPC 2.0 trên stdin, nên chạy trực tiếp thế này sẽ **đứng im chờ
input** — đúng như thiết kế. Muốn xem tool chạy thì dùng runner headless dưới
đây.

### Gọi thẳng một tool

**Git Bash** (JSON quote bình thường):

```bash
uv run rag-eval legal-tool mcp_traffic_hybrid_search \
  --args '{"query":"xe máy vượt đèn đỏ phạt bao nhiêu","limit":3}' 2>/dev/null
```

**PowerShell 5.1** — phải **nhân đôi** mỗi dấu ngoặc kép:

```powershell
uv run rag-eval legal-tool mcp_traffic_hybrid_search --args '{""query"":""xe máy vượt đèn đỏ phạt bao nhiêu"",""limit"":3}' 2>$null
```

Tôi đã thử bốn cách quote khác trong PowerShell 5.1 (nháy đơn thường, `\"`,
`--%`, biến từ `ConvertTo-Json`) — **cả bốn đều hỏng**, ba cái báo lỗi parse JSON
và một cái thoát với mã 2 mà không in gì. Chỉ dạng nhân đôi ở trên là chạy.

Kết quả thật (đã lọc bớt cho gọn):

```
168_2024_nd_cp.c_ii.s_1.a_7.c_7.p_c | rerank= 3.46 | rrf= 0.04442
168_2024_nd_cp.c_ii.s_5.a_36.c_2.p_d | rerank= 0.56 | rrf= 0.03951
168_2024_nd_cp.c_ii.s_2.a_14.c_1.p_b | rerank= 0.37 | rrf= 0.02658
```

`2>/dev/null` / `2>$null` chỉ để bỏ log nạp model cho đỡ rối; bỏ đi thì thấy đủ.

### 15 tool có sẵn

Truy hồi (6): `mcp_traffic_hybrid_search`, `mcp_traffic_verbatim_grep`,
`mcp_traffic_hierarchical_navigate`, `mcp_traffic_graph_traverse`,
`mcp_traffic_graph_edge_write`, `mcp_traffic_corpus_validate`

Ghi metadata (1): `mcp_traffic_add_metadata`

Dàn dựng (8): `mcp_traffic_stg_preview`, `stg_get_chunk`, `stg_get_raw`,
`stg_grep`, `stg_patch`, `stg_add_edges`, `stg_reparent`, `stg_commit`
(tên đầy đủ đều có tiền tố `mcp_traffic_`)

Ví dụ tìm nguyên văn — hữu ích khi hội đồng hỏi "trong luật có câu này không":

```bash
uv run rag-eval legal-tool mcp_traffic_verbatim_grep \
  --args '{"pattern":"cao tốc là 120","limit":2}' 2>/dev/null
```

> **Lưu ý về `mcp_traffic_hybrid_search` qua MCP:** tool này chỉ nhận `query`,
> `temporal_violation_date` và `limit`. **Bộ lọc `doc_codes` chưa được đưa ra
> giao diện MCP** — muốn giới hạn phạm vi thì dùng UI hoặc `/api/search`.

---

## 5. Chạy lại số liệu

Mất từ vài phút tới vài chục phút mỗi lệnh. Đặt `$env:PYTHONIOENCODING='utf-8'`
trước nếu ghi ra file.

```powershell
uv run python scripts/baselines.py          # 5 chế độ truy hồi × 4 tập; thêm --strict cho mức Khoản
uv run python scripts/rerank_sweep.py       # bảng reranker
uv run python scripts/abstain_sweep.py      # ngưỡng từ chối trả lời, 25 mức
uv run python scripts/latency_bench.py      # p50/p95 — chạy khi máy rảnh
uv run python scripts/refacet.py            # đối chiếu nhãn loại xe (mặc định KHÔNG ghi gì)
```

Output cũ nằm sẵn trong [`evidence/`](evidence/README.md), kèm bảng ánh xạ từng
khẳng định về đúng file và đúng lệnh sinh ra nó.

`refacet.py` mặc định chỉ in ra những gì **sẽ** đổi; phải thêm `--apply` mới ghi
database. Cố ý không có cờ `--dry-run` để không ai quên nó.

---

## 6. Kiểm thử

```powershell
uv run pytest -q                            # 261 pass, 4 skip
$env:TEST_WITH_REAL_DB=1; uv run pytest -q  # 263 pass, 2 skip — gồm di trú trên PostgreSQL thật
Remove-Item Env:\TEST_WITH_REAL_DB

cd frontend; npx playwright test            # 75 test UI/API
cd ..

./scripts/check.sh                          # ruff + ty + pytest
```

Hai test skip cuối là **đúng theo thiết kế** — chúng kiểm entry point nào in
tiếng Việt ra stdout, và entry point chỉ in ASCII thì không thể chạm vào bug
encoding nên tự bỏ qua.

Playwright cần backend + Vite đang chạy (`uv run rag-eval ui --dev`).

---

## 7. Dừng

```powershell
# Ctrl+C ở cửa sổ đang chạy `rag-eval ui`, rồi:
docker compose stop        # giữ dữ liệu
docker compose down        # giữ dữ liệu (volume không bị xoá)
```

`docker compose down -v` **xoá cả volume**, tức mất toàn bộ corpus đã nạp và
phải chạy lại `legal-bootstrap` + `legal-promote`. Đừng dùng khi chỉ muốn tắt máy.

---

## 8. Sự cố đã gặp thật, và cách xử lý

| Hiện tượng | Nguyên nhân | Xử lý |
| :--- | :--- | :--- |
| `The token '&&' is not a valid statement separator` | PowerShell 5.1 | Dùng `;` |
| Mở `127.0.0.1:8000` ra 404 | Đang chạy `--dev`, không có `dist/` | Mở **5173** |
| `[Errno 10048] ... only one usage of each socket address` | Một backend cũ vẫn đang giữ cổng 8000 | Mục 1.1 — mở 5173, hoặc dừng tiến trình cũ |
| `API Error 500` giữa lúc đang tra cứu | Backend vừa bị restart | Đợi ~15 giây cho model nạp lại rồi thử lại |
| Tra cứu ra rỗng sau khi chọn bộ lọc | Mã văn bản không khớp (`NĐ-CP` vs `ND-CP`) | Xem lại danh sách ở mục 3 |
| `UnicodeEncodeError` khi ghi output ra file | Python lấy encoding từ locale khi stdout không phải terminal | `$env:PYTHONIOENCODING='utf-8'` |
| Docker không bind được cổng | Cổng nằm trong dải Windows dành cho Hyper-V/WinNAT | `netsh interface ipv4 show excludedportrange protocol=tcp`; đã chuyển sang 15432 để tránh |
| `Không tìm thấy npm trong PATH` | Chưa cài Node.js | Cài Node, hoặc chạy riêng backend: `uv run python -m uvicorn rag_eval.legal.web.app:create_app --factory --host 127.0.0.1 --port 8000` |
| Tab hỏi đáp báo lỗi với `gemini` | CLI có nhưng hết hiệu lực xác thực | Chọn `claude` hoặc `codex` |

---

## 9. Ba câu hỏi hội đồng dễ hỏi, và câu trả lời thật

**"Hệ thống có bịa không?"** — Tab tra cứu thì không, nó chỉ trích nguyên văn.
Tab hỏi đáp có model sinh văn xuôi, và ở đó có lớp kiểm: mọi số hiệu Điều và mọi
con số tiền phải có trong các điều khoản đã truy hồi, lệch thì báo đỏ. Nhưng lớp
đó chỉ xác nhận câu trả lời **nằm trong** văn bản đã cấp, **không** xác nhận nó
**đọc đúng** văn bản đó — không phép kiểm tự động nào làm được việc sau.

**"Sao hỏi về tù lại không trả lời?"** — Corpus chỉ gồm văn bản giao thông đường
bộ, không có Bộ luật Hình sự. Cùng một vụ tai nạn chết người, phần **hành chính**
thì trả lời được (`168/2024/NĐ-CP` Điều 6 Khoản 8, 16–18 triệu đồng), phần
**hình sự** thì không.

**"Độ chính xác bao nhiêu?"** — Hit@1 86,4% ở mức Điều trên mẫu 2.000 câu có
rerank (`evidence/bench2k_rr3.txt`), 80,0% trên tập niêm phong 80 câu chưa từng
dùng để chỉnh tham số (`evidence/holdout80.txt`). Con số 100% ở cột `tuned`
trong `evidence/baselines.txt` **không được trích** — đó là tập đã dùng để chỉnh
tham số, nó không đo được gì. Và **chưa có chuyên gia pháp lý nào thẩm định**;
phiếu mù 60 câu đã dựng sẵn ở `evidence/human_eval_sheet.html` nhưng chưa ai điền.
