# Vietnamese Traffic Law Agentic RAG Platform & Reviewer Studio

A production-grade, enterprise-ready **Vietnamese Traffic Law Autonomous Agentic RAG System** powered by Model Context Protocol (MCP), a unified PostgreSQL 16 engine (`pgvector` + `ltree` + recursive graph CTEs + Vietnamese full-text search), Context-Preserving Hierarchical Chunking (CPHC), an event-sourced Write-Ahead Log (WAL) staging engine, and a Human-in-the-Loop Statutory Reviewer Studio.

---

## System Architecture

```
%%{init: {"flowchart": {"defaultRenderer": "elk"}}}%%
flowchart TB
    subgraph STAGING["TWO-PHASE EVENT-SOURCED STAGING (WAL)"]
        direction TB
        RAW["<b>Raw Statutory Text</b><br/>Luật, Nghị định, Thông tư, QCVN"]
        UPLOAD["<b>Web Studio Upload</b><br/>POST /api/staging/sessions"]
        GENESIS["<b>Genesis Snapshot (genesis.json)</b><br/>• SHA-256 genesis_hash<br/>• Initial CPHC AST Chunks<br/>• Initial Relation Edges"]
        WAL["<b>WAL Journal (wal.jsonl)</b><br/>• Monotonic LSN with fsync<br/>• AST Patches & Edge Edits<br/>• Reparenting & Status Commits"]
        STATE["<b>Materialized Cache (state.json)</b><br/>O(1) fast-read checkpoint synchronized via replay()"]
        
        RAW --> UPLOAD --> GENESIS --> WAL --> STATE
    end

    subgraph REVIEW["HUMAN-IN-THE-LOOP REVIEWER STUDIO"]
        direction TB
        UI["<b>Frontend Studio (React + Vite)</b><br/>• Document Reader & AST Tree Explorer<br/>• Surgical Editor Drawer (Delta Patches)<br/>• Subtree Reparenting & Visual Graph Canvas"]
        VALIDATOR["<b>Pre-Flight Validator</b><br/>7 Integrity Checks (LTREE, Continuity, Dates, Grounding, Graph Edges)"]
        PROMOTION["<b>Human Promotion Engine</b><br/>Atomic PostgreSQL Bulk Commit Transaction"]

        UI --> VALIDATOR --> PROMOTION
    end

    subgraph PRODUCTION["PRODUCTION POSTGRESQL 16 ENGINE"]
        direction TB
        TABLES["<b>Relational & Vector Tables</b><br/>• documents (statutory temporal metadata)<br/>• chunks (ltree path + 384d/1536d vector + tsvector)<br/>• graph_edges (statutory cross-references)"]
        STORED_PROCS["<b>Stored Procedures & Trigram GIN</b><br/>• search_statutory_chunks (Dense + Sparse RRF)<br/>• grep_statutory_text (Regex/Trigram search)<br/>• traverse_knowledge_graph (Recursive CTEs)"]

        TABLES --- STORED_PROCS
    end

    subgraph MCP["MODEL CONTEXT PROTOCOL (MCP) SERVER"]
        direction TB
        SENSORS["<b>6 Runtime Sensors (Read / Proposed Edges)</b><br/>• hybrid_search, verbatim_grep<br/>• hierarchical_navigate, graph_traverse<br/>• corpus_validate, graph_edge_write (WAL proposal)"]
        STAGING_TOOLS["<b>8 Staging Tools (Buffered Authoring)</b><br/>• stg_preview, stg_get_chunk, stg_get_raw<br/>• stg_grep, stg_patch, stg_add_edges<br/>• stg_reparent, stg_commit"]

        SENSORS --- STAGING_TOOLS
    end

    STATE --> UI
    PROMOTION --> PRODUCTION
    PRODUCTION --> SENSORS
    STAGING_TOOLS --> WAL
```

---

## Core Architectural Pillars

### 1. Write-Ahead Log (WAL) & Deterministic Replay
Every statutory document is buffered in `.cache/stg/<sanitized_doc_code>/` prior to production promotion:
- **`genesis.json`**: Sealed origin snapshot capturing the initial AST structure and verbatim source text.
- **`wal.jsonl`**: Append-only transaction journal recording all chunk patches, subtree migrations, and relation edges with monotonic LSNs, SHA-256 payload checksums, and `os.fsync` durability.
- **`state.json`**: Materialized fast-read cache updated via deterministic pure reducer `replay()`.
- **Zero Defensive Fallbacks**: Strict schema validation ensures non-conforming checkpoints fail fast or trigger clean replay from genesis.

### 2. Human-Gated Ingestion via Web Studio
Direct CLI database loading is strictly prohibited. All documents must pass through the **Human-in-the-Loop Reviewer Studio**:
1. Upload statutory document via web UI or API.
2. AI agents and human specialists inspect, patch (`stg_patch`), and reparent (`stg_reparent`) chunks.
3. Automated **Pre-Flight Validator** enforces 7 critical integrity rules (LTREE syntax, parent-child continuity, statutory dates, content grounding, graph edge integrity, duplicate path collision).
4. Reviewer executes **Atomic Human Promotion**, committing document, chunks, and graph edges in a single database transaction.

### 3. Knowledge Graph Write Gating
- Production sensors (`graph_edge_write`) have **zero write access** to PostgreSQL tables.
- Relational proposals from AI agents are recorded strictly into the document's WAL journal (`GRAPH_EDGE_PROPOSED`) with canonical LTREE coordinate resolution (`c.path`).
- Relationships are promoted to PostgreSQL exclusively during human review.

### 4. 14 Canonical Agent-First MCP Tools
Official MCP JSON-RPC 2.0 implementation exposing 14 tools:
- **Runtime Sensors (6 tools):** `mcp_traffic_hybrid_search`, `mcp_traffic_verbatim_grep`, `mcp_traffic_hierarchical_navigate`, `mcp_traffic_graph_traverse`, `mcp_traffic_graph_edge_write`, `mcp_traffic_corpus_validate`.
- **Staging & Review Tools (8 tools):** `mcp_traffic_stg_preview`, `mcp_traffic_stg_get_chunk`, `mcp_traffic_stg_get_raw`, `mcp_traffic_stg_grep`, `mcp_traffic_stg_patch`, `mcp_traffic_stg_add_edges`, `mcp_traffic_stg_reparent`, `mcp_traffic_stg_commit`.

---

## Quick Start & CLI Operations

### 1. Infrastructure Setup (Docker Compose V2)

Launch the containerized PostgreSQL 16 database with `pgvector`, `ltree`, `pg_trgm`, `btree_gin`, and `unaccent` enabled:

```bash
# 1. Start PostgreSQL 16 container
docker compose up -d

# 2. Configure environment
cp .env.example .env

# 3. Run database migrations (creates 7 tables, HNSW indexes & stored procedures)
uv run rag-eval legal-migrate
```

---

### 2. Launching the Legal Reviewer Studio (Web Application)

Run the full-stack FastAPI backend and React Vite frontend for staging, reviewing, and promoting statutory documents:

```bash
# Production mode (serves compiled frontend/dist via FastAPI on http://127.0.0.1:8000)
uv run rag-eval ui

# Development mode (concurrent FastAPI backend + Vite HMR on http://127.0.0.1:5173)
uv run rag-eval ui --dev
```

---

### 3. Model Context Protocol (MCP) Server

Launch the official MCP JSON-RPC 2.0 Server over STDIO for AI agent pair programming (Cursor, Claude Desktop, Antigravity):

```bash
# Run server over STDIO
uv run rag-eval legal-server

# Run with file-based diagnostic logging
uv run rag-eval legal-server --log-file logs/mcp_server.log
```

---

### 4. Headless MCP Tool Execution

Execute any of the 14 MCP tools directly from the CLI:

```bash
# Execute hybrid search with dense semantic + sparse full-text fusion
uv run rag-eval legal-tool mcp_traffic_hybrid_search -a '{"query": "vượt đèn đỏ xe máy", "limit": 5}'

# Inspect staged document outline
uv run rag-eval legal-tool mcp_traffic_stg_preview -a '{"doc_code": "100/2019/NĐ-CP", "limit": 10}'

# Confirm agent staging commit
uv run rag-eval legal-tool mcp_traffic_stg_commit -a '{"doc_code": "100/2019/NĐ-CP"}'
```

---

## Development & Quality Assurance

```bash
# Run unified QA verification pipeline (Ruff linting, Ty typecheck, Pytest suite)
./scripts/check.sh
# or: make check

# Individual QA targets
make test        # Run pytest test suite
make lint        # Run ruff check --fix
make typecheck   # Run ty typecheck
```

---

## Repository Structure

```text
rag/
├── frontend/                    # React 18 + Vite + Tailwind CSS Reviewer Studio
│   └── src/
│       ├── components/          # PreFlightChecklist, TreeHierarchyCanvas, SurgicalEditorDrawer
│       ├── hooks/               # useStagingSession, usePreFlightCheck, useCanvasTransform
│       └── services/api.ts      # REST API client for staging operations
├── scripts/                     # check.sh, update_dir_tree.sh, fetch_corpus.py
├── src/rag_eval/
│   ├── legal/
│   │   ├── db/                  # DDL migrations, connection pool, bulk loader
│   │   ├── ingestion/
│   │   │   ├── staging/         # Modular staging package (models, operations, session, manager)
│   │   │   ├── cphc.py          # Context-Preserving Hierarchical Chunking
│   │   │   ├── parser.py        # 6-tier Vietnamese statutory AST parser
│   │   │   ├── wal.py           # Write-Ahead Log engine, GenesisSnapshot, and replay
│   │   │   └── xref.py          # Cross-document citation extractor & resolver
│   │   ├── mcp/
│   │   │   ├── tools/           # 6 Runtime sensors & 8 Staging tools
│   │   │   ├── registry.py      # Declarative MCP tool registrations
│   │   │   └── server.py        # MCPServer composition root & JSON-RPC bridge
│   │   └── web/
│   │       ├── services/        # PreFlightValidator, TreeBuilder, DiffCalculator, PromotionEngine
│   │       ├── app.py           # FastAPI application factory
│   │       └── router.py        # Staging session REST endpoints
│   └── cli.py                   # Typer CLI entrypoint (legal-migrate, legal-server, legal-tool, ui)
├── compose.yaml                 # Docker Compose V2 PostgreSQL 16 + pgvector container
├── pyproject.toml               # uv project configuration & strict type bounds
└── README.md
```

---

## License & Certification

- **Type Safety**: 100% Zero-`Any` typing architecture enforced via `ty check`.
- **Code Quality**: Verified clean across `ruff` and `pytest`.
- **Durability**: Event-sourced crash consistency guaranteed via atomic WAL journaling and `os.fsync`.
