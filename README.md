<div align="center">

# Traffic Law RAG

**Hệ thống truy hồi và hỏi đáp có trích dẫn cho Luật Giao thông đường bộ Việt Nam**

Tìm đúng **Điều · Khoản · Điểm** áp dụng cho một tình huống, có hiệu lực tại một thời điểm,
trả về **nguyên văn** kèm địa chỉ trích dẫn kiểm chứng được.

[![Python](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16_+_pgvector-4169E1?logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React_+_Vite-61DAFB?logo=react&logoColor=black)](https://vitejs.dev/)
[![MCP](https://img.shields.io/badge/MCP-JSON--RPC_2.0-7C3AED)](https://modelcontextprotocol.io/)
[![Tests](https://img.shields.io/badge/tests-319_passing-success)](#kiểm-thử)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[Giới thiệu](#giới-thiệu) · [Tính năng](#tính-năng-chính) · [Kiến trúc](#kiến-trúc-tổng-thể) · [Cài đặt](#cài-đặt) · [Chạy dự án](#chạy-dự-án) · [Cấu hình](#cấu-hình-môi-trường) · [Đóng góp](#hướng-dẫn-đóng-góp) · [Lộ trình](#lộ-trình)

</div>

---

## Giới thiệu

Tra cứu mức phạt giao thông nghe có vẻ là bài toán tìm kiếm thông thường. Thực tế nó
có ba đặc điểm khiến một hệ thống RAG dựng theo mặc định **hỏng một cách có hệ thống**:

**1. Câu trả lời bị chẻ làm đôi theo chiều dọc.** Mức tiền phạt nằm ở **Khoản**, hành vi
vi phạm nằm ở **Điểm** con bên dưới. Hai cấp khác nhau, và bản thân Khoản không phải là
một đơn vị tìm kiếm độc lập. Đo trên kho hiện tại: chỉ **2,8%** số đoạn tự chứa con số
tiền trong nguyên văn của chính nó.

**2. Người dùng không nói tiếng của văn bản luật.** Không ai hỏi *"không chấp hành hiệu
lệnh của đèn tín hiệu giao thông"* — họ hỏi *"vượt đèn đỏ phạt bao nhiêu"*. Hai cách nói
này **không chung một từ nào**.

**3. Trả lời sai ở đây tốn tiền thật của người đọc.** Một con số phạt bịa ra, kèm trích
dẫn Điều/Khoản/Điểm hoàn toàn đúng địa chỉ, sẽ **không ai phát hiện được**.

Dự án này giải quyết cả ba, và — quan trọng không kém — **đo lại chính mình đủ chặt để
biết chỗ nào chưa giải quyết được**. Mọi con số trong tài liệu này đều truy được về một
file trong [`evidence/`](evidence/README.md) hoặc về một lệnh chạy lại được.

> [!IMPORTANT]
> **Hệ thống này không phải là tư vấn pháp lý.** Nó truy hồi và trích dẫn văn bản quy
> phạm pháp luật. Mọi quyết định có hệ quả pháp lý cần được người có chuyên môn thẩm định.
> Phần [Giới hạn đã biết](#giới-hạn-đã-biết) liệt kê những gì hệ thống **chưa** làm được.

---

## Tính năng chính

### 🏛 Chia văn bản theo cấu trúc pháp lý (CPHC)

Mỗi đoạn giữ **nguyên văn của chính nó** để trích dẫn, đồng thời **mang theo tiền tố ngữ
cảnh của toàn bộ cấp cha** để tìm kiếm. Nhờ vậy một Điểm con vẫn "biết" mức phạt nằm ở
Khoản cha của nó.

```text
verbatim_text        (dùng để trích dẫn · trung vị 175 ký tự)
└─ "Điểm c) Không chấp hành hiệu lệnh của đèn tín hiệu giao thông;"

contextualized_text  (dùng để đánh chỉ mục · trung bình 509 ký tự)
├─ [Nghị định 168/2024/NĐ-CP...] > [Chương II] >
├─ [Điều 7: Xử phạt người điều khiển xe mô tô, xe gắn máy...] >
├─ [Khoản 7: Phạt tiền từ 4.000.000 đồng đến 6.000.000 đồng đối với...]
└─ "Điểm c) Không chấp hành hiệu lệnh của đèn tín hiệu giao thông;"
```

Tác dụng đo được: số đoạn "biết mức phạt của chính mình" tăng từ **2,8% lên 18,5%**, và
độ tương đồng của câu hỏi *"xe máy vượt đèn đỏ phạt bao nhiêu tiền"* với đoạn đúng tăng
từ **0,826 → 0,889** — tức từ **dưới** ngưỡng từ chối trả lời (0,86) lên **trên** ngưỡng.

### 🔀 Truy hồi lai hai nhánh

Nhánh **ngữ nghĩa** (pgvector HNSW) và nhánh **từ khoá** (tsvector/GIN) chạy song song,
hợp nhất bằng **Reciprocal Rank Fusion, `k = 60`** — cộng nghịch đảo thứ hạng chứ không
cộng điểm thô, vì hai thang điểm không quy đổi được sang nhau.

### 🗣 Mở rộng truy vấn cho câu hỏi đời thường

Từ điển **15 cặp** ánh xạ lời nói thường sang lời văn luật, mỗi cụm đích đều đã kiểm
chứng là có thật trong kho. **Chỉ áp dụng cho nhánh từ khoá** — vector vẫn tính từ đúng
chữ người dùng gõ, nên một ánh xạ sai chỉ hỏng được một nửa hệ thống.

> Trước khi có cơ chế này, nhánh từ khoá xếp điều khoản đúng ở hạng **821**.

### 🛑 Từ chối trả lời bằng ba tín hiệu độc lập

| Tín hiệu | Ngưỡng | Kết quả | Cách chọn ngưỡng |
| :--- | :--- | :--- | :--- |
| Không từ khoá nào khớp | — | `none` (chặn) | 0 sai trên 400 câu thật, bắt 25/25 câu vô nghĩa |
| Điểm cross-encoder thấp | `< −1,0` | `low` (cảnh báo) | Bắt 90,2% câu ngoài phạm vi, báo oan 7,1% |
| Cosine thấp | `< 0,86` | `low` (cảnh báo) | Ngưỡng **cao nhất** còn giữ báo oan ở **0,0%** |

Không tín hiệu nào được quyền chặn hẳn ngoài tín hiệu đầu, vì hai phân bố điểm
**chồng lấn nhau** — không tồn tại ngưỡng vừa bắt hết câu xấu vừa không đụng câu thật.
Toàn bộ đường cong đánh đổi: [`evidence/abstain_sweep.txt`](evidence/abstain_sweep.txt).

### 📊 Xử lý bảng biểu

Bảng trong quy chuẩn kỹ thuật gần như không chứa từ nào trùng với cách người ta hỏi. Hệ
thống sinh **một câu mô tả tiếng Việt cho mỗi bảng** và chèn vào `contextualized_text`,
phát hiện và loại **bảng giả** do dàn trang web sinh ra, và **ghép lại các mảnh của một
bảng dài** trước khi đưa cho mô hình đọc.

### 🤖 LLM đứng ngoài, không nhúng vào trong

Hệ thống chỉ trả về nguyên văn điều luật kèm địa chỉ. Mô hình ngôn ngữ gọi vào qua
**MCP (Model Context Protocol)** để lấy điều luật, đọc, rồi mới viết câu trả lời — và
mọi số hiệu Điều cùng mọi con số tiền trong câu trả lời đều được **đối chiếu ngược** lại
điều khoản đã truy hồi.

### 🧪 Mọi ngưỡng đều đo, mọi script đều chạy khô mặc định

Không có hằng số nào được chọn bằng cảm tính. Mọi script đụng vào cơ sở dữ liệu đều
**in ra trước những gì sắp đổi** và chỉ ghi thật khi có cờ `--apply`.

---

## Kiến trúc tổng thể

### Bức tranh hệ thống

```mermaid
graph TB
    subgraph client["Tầng sử dụng"]
        AGENT["AI Agent<br/>(Claude · Codex · Gemini)"]
        WEB["Reviewer UI<br/>React + Vite"]
    end

    subgraph server["Tầng phục vụ"]
        MCP["MCP Server<br/>JSON-RPC 2.0 · stdio<br/><b>15 tools</b>"]
        API["FastAPI<br/>REST /api/*"]
    end

    subgraph core["Tầng lõi truy hồi"]
        EMB["Query Embedder<br/>e5-small · 384d"]
        LEX["Query Expansion<br/>15 cặp đồng nghĩa"]
        FUSE["RRF Fusion<br/>k = 60"]
        RR["Cross-Encoder<br/>Reranker · pool 10"]
        ABS["Abstention<br/>3 tín hiệu"]
    end

    subgraph data["Tầng dữ liệu"]
        PG[("PostgreSQL 16<br/>8 bảng · 19 migrations")]
        IDX["pgvector HNSW · ltree<br/>tsvector/GIN · pg_trgm"]
    end

    AGENT -->|stdio| MCP
    WEB -->|HTTP| API
    MCP --> EMB
    API --> EMB
    EMB --> FUSE
    LEX --> FUSE
    FUSE --> RR --> ABS
    FUSE -.->|truy vấn| PG
    PG --- IDX

    style core fill:#1e293b,stroke:#475569,color:#e2e8f0
    style data fill:#0f172a,stroke:#334155,color:#e2e8f0
```

### Đường đi của một truy vấn

```mermaid
sequenceDiagram
    autonumber
    participant U as Người dùng
    participant S as Hệ thống truy hồi
    participant DB as PostgreSQL
    participant R as Cross-Encoder
    participant L as LLM (qua MCP)

    U->>S: "vượt đèn đỏ phạt bao nhiêu"

    Note over S: Tách làm hai nhánh<br/>với hai kiểu chuẩn hoá khác nhau
    par Nhánh ngữ nghĩa
        S->>S: embed("query: …") → vector 384d
        S->>DB: HNSW · cosine
    and Nhánh từ khoá
        S->>S: mở rộng + "không chấp hành hiệu lệnh…"
        S->>DB: tsquery · vietnamese_legal
    end

    DB-->>S: hai danh sách ứng viên
    S->>S: RRF k=60 → pool 10

    alt Câu CÓ dấu
        S->>R: chấm lại 10 ứng viên
        R-->>S: thứ hạng mới (+7,1 điểm Hit@1)
    else Câu KHÔNG dấu
        Note over S,R: Bỏ qua chấm lại —<br/>đo được là mất 21,2 điểm
    end

    S->>S: Kiểm 3 tín hiệu từ chối

    alt Đủ căn cứ
        S->>S: Ghép lại các cửa sổ bị cắt
        S-->>L: nguyên văn + Điều/Khoản/Điểm
        L-->>U: câu trả lời CÓ trích dẫn
    else Không đủ căn cứ
        S-->>U: "không tìm thấy" — không gọi LLM
    end
```

> [!NOTE]
> Nhánh "không đủ căn cứ" **không gửi gì cho LLM**. Nếu cứ đưa đoạn kém liên quan rồi
> trông chờ mô hình tự nói "tôi không biết", nó thường sẽ cố trả lời bằng kiến thức nền
> — tức là bịa.

### Mô hình dữ liệu

```mermaid
erDiagram
    documents ||--o{ chunks : "chứa"
    chunks ||--o{ graph_edges : "trỏ tới"
    chunks ||--o{ annotations : "được ghi chú"

    documents {
        uuid id PK
        text doc_code "168/2024/ND-CP"
        text title
        date effective_date
    }
    chunks {
        uuid id PK
        ltree path "a_7.c_7.p_c — cây phân cấp"
        text verbatim_text "nguyên văn · để trích dẫn"
        text contextualized_text "có tiền tố cha · để tìm"
        vector embedding "384 chiều"
        tsvector tsv_content "A=ngữ cảnh, B=nguyên văn"
        jsonb metadata "is_table, vehicle_classes…"
        date expiration_date "NULL = còn hiệu lực"
    }
    graph_edges {
        uuid source_id FK
        uuid target_id FK
        text relation_type "sửa đổi · bãi bỏ · dẫn chiếu"
    }
```

Kiểu **`ltree`** là lựa chọn then chốt: nó biến *"lấy Khoản cha của Điểm này"* thành
**một câu truy vấn**, thay vì phải suy đoán từ văn bản.

### Các lựa chọn kỹ thuật và lý do

| Hạng mục | Lựa chọn | Tại sao |
| :--- | :--- | :--- |
| Mô hình nhúng | `intfloat/multilingual-e5-small` · 384d | Hỗ trợ tiếng Việt; tiền tố bất đối xứng `query:`/`passage:` là **bắt buộc** |
| Chỉ mục vector | pgvector HNSW, `ef_search=200` | Nằm cùng cơ sở dữ liệu với văn bản — không phải đồng bộ hai kho |
| Tách từ tiếng Việt | Cấu hình riêng `vietnamese_legal`<br/>= `unaccent` + `simple` | Bỏ dấu vì người dùng gõ không dấu; **không** chia từ gốc vì tiếng Việt là ngôn ngữ đơn lập |
| Hợp nhất | RRF `k = 60` | Hai nhánh có thang điểm không quy đổi được sang nhau |
| Chấm lại | `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` | +7,1 điểm Hit@1 với chi phí **+5 ms** |
| Phân cấp | PostgreSQL `ltree` | Truy vấn tổ tiên/hậu duệ bằng chỉ mục, không đệ quy |

---

## Kết quả đo

Chấm ở **hai độ mịn khác nhau**, vì chúng trả lời hai câu hỏi khác nhau: đúng **Điều** là
*"có tìm ra điều luật không"*, đúng **Khoản/Điểm** là *"có trích dẫn chính xác không"*.

### Mức Điều

| Bộ đề | n | Hit@1 | Hit@3 | Hit@5 | Bằng chứng |
| :--- | ---: | ---: | ---: | ---: | :--- |
| Toàn bộ, không chấm lại | 12.155 | 79,3% | 89,5% | 92,6% | [`bench12k.txt`](evidence/bench12k.txt) |
| Mẫu 2k, không chấm lại | 1.980 | 79,3% | 90,2% | 93,0% | [`bench2k_plain.txt`](evidence/bench2k_plain.txt) |
| Mẫu 2k, **có chấm lại** | 1.980 | **86,4%** | 94,0% | 95,1% | [`bench2k_rr3.txt`](evidence/bench2k_rr3.txt) |
| Bộ đề giữ kín | 80 | 80,0% | 92,5% | 92,5% | [`holdout80.txt`](evidence/holdout80.txt) |
| Phủ tài liệu mỏng | 113 | 82,3% | — | 85,8% | [`coverage113.txt`](evidence/coverage113.txt) |
| **Câu hỏi đời thường** | 108 | **63,9%** | 85,2% | 90,7% | [`colloquial118.txt`](evidence/colloquial118.txt) |

> [!WARNING]
> **Đừng trích 80,0% mà không kèm 63,9%.** Bốn dòng đầu dùng câu hỏi sinh ra *từ chính
> văn bản luật*, nên chúng thừa hưởng từ vựng của luật và **dễ hơn thực tế**. Dòng cuối
> là câu hỏi viết tay theo lối người dân hỏi, và nó thấp hơn **16,1 điểm**. Cơ chế của
> độ lệch này được đo và giải thích trong
> [`evidence/PHAT_HIEN_BO_DO_LECH.md`](evidence/PHAT_HIEN_BO_DO_LECH.md).

### Mức Khoản/Điểm — nơi khoảng cách lộ ra

| Cùng 27 câu viết tay | Hit@1 | Hit@3 | Hit@5 |
| :--- | ---: | ---: | ---: |
| Chấm ở mức **Điều** | 88,9% | 92,6% | 92,6% |
| Chấm ở mức **Khoản/Điểm** | **59,3%** | 85,2% | 92,6% |

Chênh **29,6 điểm**. Một Điều có hơn mười Khoản với hơn mười mức phạt khác nhau — đúng
Điều mà sai Khoản thì với người tra cứu vẫn là **câu trả lời sai**.
→ [`evidence/clause_bench.txt`](evidence/clause_bench.txt)

### Bảng biểu và độ trễ

<table>
<tr><td valign="top">

**30 câu hỏi về bảng**

| | @1 | @3 | @5 |
| :--- | ---: | ---: | ---: |
| Đúng Điều | 73,3% | 90,0% | 100% |
| Đúng bảng — thô | 63,3% | 80,0% | 90,0% |
| Đúng bảng — **sau ghép** | **70,0%** | **90,0%** | **100%** |

</td><td valign="top">

**Độ trễ (8 request đồng thời)**

| | p50 | p95 | req/s |
| :--- | ---: | ---: | ---: |
| Không chấm lại | 82 ms | 122 ms | 16,35 |
| **Có chấm lại** | **87 ms** | 152 ms | 15,33 |

</td></tr>
</table>

> Chi phí của việc chấm lại là **+5 ms và −6% thông lượng**, không phải "+778 ms và mất
> 7 lần thông lượng" như các bản tài liệu trước 08/09/2026 từng ghi. Con số cũ đo trước
> khi tối ưu inference. Chi tiết: [`evidence/README.md`](evidence/README.md).

---

## Cài đặt

### Yêu cầu

| | Phiên bản | Ghi chú |
| :--- | :--- | :--- |
| **Python** | 3.13+ | Quản lý bằng [`uv`](https://docs.astral.sh/uv/) |
| **Docker** | 24+ | Cho PostgreSQL — hoặc tự cài PG 16 + pgvector |
| **Node.js** | 20+ | Chỉ cần nếu build giao diện |
| **RAM** | ≥ 8 GB | Mô hình nhúng + cross-encoder chạy trên CPU |

### Các bước

```bash
# 1. Clone
git clone https://github.com/Hoang604/rag.git
cd rag

# 2. Cài phụ thuộc Python (uv tự tạo .venv)
uv sync

# 3. Khởi động PostgreSQL 16 + pgvector
docker compose up -d

# 4. Chờ database sẵn sàng
docker compose ps        # STATUS phải là "healthy"

# 5. Chạy 19 migration DDL (idempotent — chạy lại vô hại)
uv run rag-eval legal-migrate

# 6. (Tuỳ chọn) Build giao diện web
cd frontend && npm install && npm run build && cd ..
```

<details>
<summary><b>Cài trên Windows / PowerShell</b> — có vài điểm khác</summary>

```powershell
# PowerShell 5.1 KHÔNG hỗ trợ toán tử &&, phải tách từng dòng
uv sync
docker compose up -d
uv run rag-eval legal-migrate

# Tiếng Việt in ra terminal cần biến này, nếu không sẽ lỗi encoding
$env:PYTHONIOENCODING = "utf-8"
```

Cổng PostgreSQL cố ý đặt ở **15432**, không phải dải 49152+: Windows dành riêng từng
khối cổng cho Hyper-V/WinNAT và các khối này **đổi chỗ sau mỗi lần khởi động máy**.

</details>

---

## Chạy dự án

### Giao diện web cho người thẩm định

```bash
uv run rag-eval ui
#  → http://127.0.0.1:8000

uv run rag-eval ui --port 8010     # nếu cổng 8000 đã bị chiếm
```

Giao diện có 3 tab: **tra cứu** · **hỏi đáp bằng AI** · **soát và sửa văn bản**.

### MCP server (cho AI agent)

```bash
uv run rag-eval legal-server        # JSON-RPC 2.0 trên stdio
```

Khai báo trong cấu hình MCP của agent:

```json
{
  "mcpServers": {
    "traffic-law": {
      "command": "uv",
      "args": ["run", "rag-eval", "legal-server"],
      "cwd": "/đường/dẫn/tới/rag"
    }
  }
}
```

### Gọi thẳng một tool từ dòng lệnh

```bash
uv run rag-eval legal-tool mcp_traffic_hybrid_search \
  --args '{"query": "xe máy vượt đèn đỏ phạt bao nhiêu tiền", "limit": 5}'
```

<details>
<summary><b>Trên PowerShell, JSON cần nhân đôi dấu nháy kép</b></summary>

```powershell
uv run rag-eval legal-tool mcp_traffic_hybrid_search --args '{""query"": ""vượt đèn đỏ"", ""limit"": 5}'
```

</details>

### Nạp văn bản mới

```mermaid
graph LR
    A["Văn bản thô<br/>.txt / .docx"] -->|legal-stage| B["Vùng dàn dựng<br/>staging"]
    B -->|legal-link| C["Dựng liên kết<br/>chéo điều luật"]
    C -->|Reviewer UI| D{"Người<br/>thẩm định"}
    D -->|legal-promote| E[("Kho chính thức<br/>promoted")]
    D -->|sửa lại| B

    style E fill:#065f46,stroke:#10b981,color:#ecfdf5
    style D fill:#78350f,stroke:#f59e0b,color:#fffbeb
```

```bash
uv run rag-eval legal-stage --file nghi_dinh_moi.txt \
  --doc-code "999/2026/ND-CP" \
  --doc-title "Nghị định ..." \
  --effective-date 2026-01-01

uv run rag-eval legal-link                    # dựng liên kết chéo
uv run rag-eval legal-promote                 # đưa vào kho chính thức
```

> [!TIP]
> **Mọi lệnh đụng vào dữ liệu đều chạy khô mặc định.** Chúng in ra những gì *sắp* đổi và
> chỉ ghi thật khi có cờ `--apply`. Quy tắc này từng cứu một lần sửa nhãn định lệch
> **692 bản ghi** vì mẫu tìm kiếm quá rộng.

### Kiểm thử

```bash
uv run pytest -q                    # 319 bài — không cần database
TEST_WITH_REAL_DB=1 uv run pytest   # 321 bài — có database thật
make check                          # ruff + ty + pytest

cd frontend && npx playwright test  # 75 bài end-to-end
```

### Chạy lại các phép đo

```bash
uv run python scripts/qa_bench.py --fixture tests/fixtures/qrels_holdout.jsonl
uv run python scripts/qa_bench.py --fixture tests/fixtures/qrels_clause.jsonl --strict
uv run python scripts/table_bench.py --show-misses
uv run python scripts/abstain_sweep.py
uv run python scripts/latency_bench.py
```

---

## Cấu hình môi trường

Dự án chạy được **không cần file `.env`** — mọi giá trị đều có mặc định khớp với
`compose.yaml`. Chép [`.env.example`](.env.example) thành `.env` khi cần đổi.

| Biến | Mặc định | Mô tả |
| :--- | :--- | :--- |
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:15432/rag_legal` | Chuỗi kết nối PostgreSQL |
| `TEST_WITH_REAL_DB` | *(không đặt)* | Đặt `1` để chạy cả các bài kiểm thử cần database thật |
| `PYTHONIOENCODING` | *(không đặt)* | Đặt `utf-8` trên Windows để in được tiếng Việt |

```bash
# .env
DATABASE_URL=postgresql://postgres:postgres@localhost:15432/rag_legal
```

> [!CAUTION]
> Mật khẩu mặc định `postgres:postgres` chỉ dùng cho môi trường phát triển cục bộ.
> **Phải đổi trước khi triển khai ở bất kỳ nơi nào có thể truy cập từ mạng.**

---

## Cấu trúc thư mục

```text
rag/
├── src/rag_eval/
│   ├── cli.py                     # 10 lệnh CLI (typer)
│   └── legal/
│       ├── answer.py              # sinh câu trả lời + đối chiếu chống bịa
│       ├── text.py                # chuẩn hoá tiếng Việt, bỏ dấu
│       ├── schemas.py             # kiểu dữ liệu chung, mã lỗi
│       ├── db/
│       │   ├── connection.py      # pool asyncpg
│       │   ├── migrations.py      # trình chạy DDL idempotent
│       │   └── sql/               # 19 file migration
│       ├── ingestion/
│       │   ├── converter.py       # .docx/.txt → văn bản sạch
│       │   ├── cphc.py            # ★ chia đoạn theo cấu trúc pháp lý
│       │   ├── tables.py          # nhận diện bảng thật / bảng giả
│       │   ├── loader.py          # nhúng vector + ghi vào DB
│       │   └── xref.py            # liên kết chéo, phân giải địa chỉ
│       ├── retrieval/
│       │   ├── lexicon.py         # ★ mở rộng truy vấn (15 cặp)
│       │   ├── reranker.py        # cross-encoder
│       │   ├── overlay.py         # trọng số học từ phản hồi (đang tắt)
│       │   └── annotations.py     # ghi chú của agent
│       ├── mcp/
│       │   ├── server.py          # JSON-RPC 2.0 trên stdio
│       │   └── tools.py           # ★ 15 tool, gồm hybrid_search
│       ├── web/
│       │   ├── app.py             # khởi tạo FastAPI
│       │   ├── router.py          # REST /api/*
│       │   └── schemas.py         # mô hình request/response
│       └── eval/                  # bộ chấm điểm, đối sánh đáp án
│
├── frontend/src/                  # React + Vite + Tailwind
│   ├── components/                # tra cứu · hỏi đáp · soát văn bản
│   ├── services/  hooks/  types/
│
├── scripts/                       # công cụ đo và bảo trì (mặc định chạy khô)
│   ├── qa_bench.py                # chấm điểm truy hồi (--strict = mức Khoản)
│   ├── table_bench.py             # chấm riêng câu hỏi về bảng
│   ├── abstain_sweep.py           # quét ngưỡng từ chối trả lời
│   ├── latency_bench.py           # đo độ trễ và thông lượng
│   └── describe_tables.py         # sinh câu mô tả cho bảng
│
├── tests/                         # 319 bài pytest
│   └── fixtures/                  # bộ đề chấm điểm (.jsonl)
│
├── evidence/                      # ★ bằng chứng cho mọi con số trong tài liệu
├── docs/                          # tài liệu thiết kế, hướng dẫn demo
├── compose.yaml                   # PostgreSQL 16 + pgvector
└── pyproject.toml
```

★ = nơi chứa phần đóng góp chính của dự án.

---

## Giới hạn đã biết

Phần này liệt kê những gì hệ thống **chưa** làm được. Nó được viết ra có chủ đích.

| Giới hạn | Hiện trạng |
| :--- | :--- |
| **Chưa có chuyên gia pháp lý thẩm định** | Phiếu chấm 60 câu đã chuẩn bị, chưa ai điền. Đây là thiếu sót quan trọng nhất. |
| **Độ chính xác mức Khoản/Điểm còn thấp** | 59,3% so với 88,9% ở mức Điều. |
| **Không tách từ ghép tiếng Việt** | `giao thông` bị tách thành `giao` + `thong`. Bù bằng nhánh ngữ nghĩa và điểm thưởng khớp trọn cụm. |
| **Ô gộp trong bảng bị mất** | Khoảng 6% số dòng bảng có ô trải nhiều dòng. |
| **13 đoạn bị hỏng do dàn trang** | Cần nạp lại kho để sửa. |
| **Lớp học từ phản hồi đang tắt** | Đã dựng đủ nhưng chưa có dữ liệu người dùng thật để học. |
| **Kho văn bản giới hạn** | 13 văn bản. Chưa phủ hết lĩnh vực giao thông đường bộ. |

---

## Hướng dẫn đóng góp

Rất hoan nghênh đóng góp. Dự án có một số quy ước **không thoả hiệp**, vì chúng là thứ
giữ cho các con số trong tài liệu này đáng tin.

### Quy ước bắt buộc

> [!IMPORTANT]
> **1. Không có con số nào không có bằng chứng.**
> Mọi khẳng định định lượng phải kèm một file trong `evidence/` hoặc một lệnh chạy lại
> được. Nếu chưa đo thì ghi rõ là *chưa đo*.
>
> **2. Ngưỡng phải đo, không được chọn.**
> Thêm một hằng số ngưỡng thì phải kèm bảng quét toàn dải và báo cáo được–mất ở mỗi mức.
>
> **3. Script đụng dữ liệu phải chạy khô mặc định.**
> In ra những gì sắp đổi; chỉ ghi thật khi có `--apply`.
>
> **4. Kết quả âm tính cũng là kết quả.**
> Thử một hướng mà không hiệu quả thì ghi lại, đừng xoá đi.

### Quy trình

```bash
git checkout -b feat/ten-tinh-nang      # không commit thẳng lên main

# ... viết code ...

make check                               # ruff + ty + pytest, phải sạch hết
TEST_WITH_REAL_DB=1 uv run pytest        # nếu có đụng tới truy vấn
```

Nếu thay đổi ảnh hưởng tới truy hồi, **chạy lại phép đo liên quan và đính kèm kết quả
vào mô tả pull request**:

```bash
uv run python scripts/qa_bench.py --fixture tests/fixtures/qrels_holdout.jsonl
```

### Tiêu chuẩn mã nguồn

| | |
| :--- | :--- |
| Định dạng & lint | `ruff` — phải sạch |
| Kiểm kiểu tĩnh | `ty` — phải sạch |
| Chú thích | Ngắn, chỉ giải thích **tại sao**, không mô tả lại code |
| Thông điệp commit | Nói rõ điều gì đã thay đổi và **bằng chứng nào chứng minh** |

---

## Lộ trình

```mermaid
gantt
    title Lộ trình phát triển
    dateFormat YYYY-MM
    axisFormat %m/%Y

    section Đã xong
    Thu thập và nạp kho văn bản      :done, 2026-08, 1M
    Chia đoạn CPHC + cơ sở dữ liệu  :done, 2026-08, 1M
    MCP server 15 tool              :done, 2026-08, 1M
    Truy hồi lai + chấm lại         :done, 2026-09, 1M
    Giao diện thẩm định             :done, 2026-09, 1M
    Xử lý bảng biểu                 :done, 2026-09, 1M

    section Đang làm
    Nâng độ chính xác mức Khoản     :active, 2026-09, 2M
    Đánh giá bởi chuyên gia luật    :active, 2026-09, 2M

    section Kế tiếp
    Tách từ ghép tiếng Việt         :2026-11, 2M
    Mở rộng kho văn bản             :2026-11, 3M
    Học từ phản hồi người dùng      :2027-01, 2M
```

### Chi tiết

| Ưu tiên | Hạng mục | Vì sao |
| :--- | :--- | :--- |
| 🔴 Cao | **Chuyên gia pháp lý thẩm định 60 câu** | Không con số tự động nào thay được. |
| 🔴 Cao | **Nâng độ chính xác mức Khoản/Điểm** | Khoảng cách 29,6 điểm là điểm yếu lớn nhất hiện nay. |
| 🟡 Vừa | **Nạp lại kho để sửa 13 đoạn hỏng** | Cần chạy lại toàn bộ pipeline nạp. |
| 🟡 Vừa | **Dùng cờ `is_table` khi xếp hạng** | Đã có trong dữ liệu và đã trả ra API, chưa dùng lúc xếp hạng. |
| 🟡 Vừa | **Tách từ ghép tiếng Việt** | Cải thiện nhánh từ khoá cho cụm nhiều âm tiết. |
| 🟢 Thấp | **Xử lý ô gộp trong bảng** | Ảnh hưởng ~6% số dòng bảng. |
| 🟢 Thấp | **Bật lớp học từ phản hồi** | Chờ có dữ liệu người dùng thật. |

---

## Giấy phép

Phát hành theo **[Giấy phép MIT](LICENSE)** — © 2026 Le Bao Hung.

Bạn được tự do dùng, sao chép, sửa đổi và phân phối lại mã nguồn, kể cả cho mục đích
thương mại, với một điều kiện duy nhất: **giữ lại thông báo bản quyền và nội dung giấy
phép**. Phần mềm được cung cấp "nguyên trạng", không kèm bảo đảm nào.

Chọn MIT vì đây là đồ án học thuật: mục đích là để người khác tham khảo, trích dẫn và kế
thừa được, càng ít rào cản càng tốt.

> [!NOTE]
> **Giấy phép này áp dụng cho mã nguồn, không áp dụng cho văn bản pháp luật.**
>
> Văn bản quy phạm pháp luật trong `data/` được thu thập từ các nguồn chính thống của cơ
> quan nhà nước. Theo Điều 15 Luật Sở hữu trí tuệ, **văn bản quy phạm pháp luật không
> thuộc phạm vi bảo hộ quyền tác giả** — nên bản thân nội dung luật không bị giấy phép
> này ràng buộc, và cũng không được nó cấp quyền gì thêm. Hãy đối chiếu lại nguồn gốc
> trước khi phân phối lại.
>
> Các mô hình học máy được tải về khi chạy (`intfloat/multilingual-e5-small`,
> `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`) có giấy phép riêng của chúng.

---

## Tài liệu liên quan

| Tài liệu | Nội dung |
| :--- | :--- |
| [`docs/demo.md`](docs/demo.md) | Kịch bản demo, từng lệnh đã chạy thật |
| [`evidence/README.md`](evidence/README.md) | Chỉ mục toàn bộ bằng chứng đo đạc |
| [`evidence/PHAT_HIEN_BO_DO_LECH.md`](evidence/PHAT_HIEN_BO_DO_LECH.md) | Vì sao bộ đề tự sinh cho điểm cao hơn thực tế 16 điểm |
| [`evidence/QUYET_DINH_OVERLAY.md`](evidence/QUYET_DINH_OVERLAY.md) | Quyết định tắt lớp học từ phản hồi, kèm số liệu |
| [`AGENTS.md`](AGENTS.md) | Quy ước dành cho AI agent làm việc trên kho mã này |

---

<div align="center">

**Xây dựng hệ thống Information Retrieval / RAG trong lĩnh vực Luật Giao thông**

Đồ án tốt nghiệp · 2026

</div>
