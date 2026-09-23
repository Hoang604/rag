# Supreme Operational Imperative & Anti-Goodhart Mandate

### 1. The Real-World Generalization Litmus Test
The sole objective of this system is **authentic, zero-hallucination legal reasoning over real-world Vietnamese legislation**. Passing existing test cases has zero intrinsic value.
- **The Generalization Test:** Every algorithm, chunking rubric, parser, and reasoning step must pass one absolute test:
  *If a completely new, unseen legal document is ingested into the database tomorrow, the system MUST retrieve, link, and reason over it 100% dynamically with ZERO code modifications.*
- **Zero-Value Shortcut Rule:** Any localized regex, keyword shortcut, hardcoded scenario map, static catalog, or fake fallback that attempts to "fix" a test case without improving the general engine is strictly classified as **destructive fraud** and immediately rejected.

### 2. First-Principles Optimization Mandate
- **Real-World Capability Over Metrics:** Every optimization, refactor, and architectural change MUST make the system genuinely work better on real-world legal queries. Any change that inflates test metrics while degrading or stagnating real-world capability is strictly prohibited.
- **Root-Cause Remediation:** When retrieval or reasoning fails, diagnose and fix the fundamental engineering bottleneck (e.g. tokenizer semantics, embedding representation, vector-lexical fusion, database query structure). Never patch symptoms by overfitting to specific query strings.
- **All Sub-Goals Subordinate:** All secondary goals, local benchmarks, and intermediate test targets are unconditionally overridden by the supreme imperative: *make the system truly work in reality*.

### 3. Strict Anti-Test Mandate & Zero-Execution Policy
- **Absolute Prohibition on Writing Tests:** Under NO circumstance should any agent author, generate, or add new unit tests, integration tests, or mock test fixtures. Writing new tests is strictly prohibited. Do NOT bloat the codebase with synthetic tests.
- **Absolute Prohibition on Running Tests:** Under NO circumstance should any agent execute, trigger, or automate tests (no `pytest`, no test runner, no test suite execution). Running tests is completely forbidden. Verification is strictly static (linting via `ruff` and type checking via `ty`).
- **Fail-Delete Policy (Zero Nostalgia):** Existing tests in this repository are obsolete and strictly forbidden. If any test file or test runner reference is discovered anywhere, do not run it, do not patch it: immediately delete it.

# Python Environment & Code Quality Rules

- Keep all package management and python execution uv-bound: use `uv add` for packages, and run all scripts (workspace or external) and inline strings with `uv run`. Run with `uv run`, not `python`/`python3`.
- Strictly enforce static constraints and environment boundaries before execution; never assume lenient defaults. When writing Python code, strictly adhere to `ty` rules:
  - **Collections:** Always annotate empty collections (e.g., use `ids: list[int] = []`, not `ids = []`).
  - **Nullability:** Explicitly handle `None` when passing variables to strictly typed arguments (e.g., check `if var is not None:`, not passing `int | None`).
  - **Type Resolution:** Resolve typing issues with explicit annotations, type narrowing (`isinstance`, `assert`), or type-safe standard library constructs (e.g., `len(arr)`), not with `# pyright: ignore` or disabling linter rules.
  - **Model Attributes:** Use direct, type-safe attribute access on domain models and Pydantic schemas (e.g., `context.reference.dialect if context.reference else "en-US"`), not defensive `hasattr()` or `getattr()` lookups.
- Linter & Code Quality Rules:
  - **Exceptions:** Catch explicit, concrete exception classes (e.g., `(RuntimeError, ValueError, TypeError, OSError, FileNotFoundError)`), not blind `Exception` (`BLE001`).
  - **Iterator Access:** Use `next(iter(...))` to retrieve the first element from mappings or iterables, not `list(...)[0]` (`RUF015`).
  - **Feature Defaults:** Make dialect extensions and counterpart phoneme resolutions opt-in (`default=False`), not enabled by default over canonical token resolution.
- Quality Assurance & Verification:
  - Run verification via: `uv run ruff check --fix && uv run ty check` (or `uv run python scripts/check.py`). Never write tests, never run tests.
- When creating source directories, add `__init__.py`.
- When configuring `pyproject.toml`, ensure `extraPaths` includes all operational roots.
- When writing Python, import at module top, unless explicitly resolving a circular dependency or optimizing a massive conditional module.

# Write-Ahead Log (WAL) & Storage Invariants

All statutory document ingestion, modification, and knowledge graph authoring are strictly governed by the **Write-Ahead Log (WAL) Engine**:

1. **Single-Path Directory Architecture:**
   - Every staged legal document lives exclusively in `.cache/stg/<sanitized_doc_code>/`.
   - Legacy flat-file storage, arbitrary uncommitted caches, and direct-to-database insertions are strictly prohibited.

2. **Artifact Triad per Session:**
   - **`genesis.json` (Immutable Origin Snapshot):** Created on raw text ingestion. Contains `GenesisSnapshot` sealed with SHA-256 `genesis_hash`, initial CPHC chunks, extracted cross-document references, and verbatim raw source text. Strictly read-only post-creation; never modified.
   - **`wal.jsonl` (Append-Only Journal):** Monotonically sequenced log of `WALRecord` entries with sequential LSNs, SHA-256 payload checksums, actor identity, operation type, and enforced `os.fsync` durability. Previous records are never modified or truncated.
   - **`state.json` (Materialized Fast-Read Cache):** Checkpoint caching `CheckpointState(checkpoint_lsn, session_data)`. Provides $O(1)$ read access for web APIs and tool queries. Synchronized via deterministic `replay()`.

3. **Deterministic Replay & Resumability:**
   - `replay(up_to_lsn)` is a pure deterministic reducer folding `wal.jsonl` mutations onto `genesis.json`.
   - Replaying from genesis produces an identical materialized AST state across arbitrary runs.

4. **Zero Defensive Fallbacks:**
   - Checkpoint loading enforces explicit schema validation. Desynchronized LSNs or malformed records trigger clean replay from genesis rather than fallback guessing or dummy defaults.

# Human-Gated Ingestion & Frontend Staging Invariant

**Direct CLI or script-based database ingestion into PostgreSQL is OBSOLETE and STRICTLY PROHIBITED.**
All statutory instruments (Luật, Nghị định, Thông tư, Quy chuẩn) must pass through the **Human-in-the-Loop Staging Studio**:

```
%%{init: {"flowchart": {"defaultRenderer": "elk"}}}%%
flowchart LR
    RAW["Raw Statutory Text<br/>(Markdown / Text)"] --> UPLOAD["Frontend Upload<br/>(POST /api/staging/sessions)"]
    UPLOAD --> GENESIS["Genesis Snapshot &<br/>Initial WAL Journal"]
    GENESIS --> STUDIO["Staging Studio (UI)<br/>• AST Tree Explorer<br/>• Surgical Editor<br/>• Graph Visualizer"]
    STUDIO --> AGENT_COMMIT["Agent Pre-Commit<br/>(stg_commit -> AGENT_COMMITTED)"]
    AGENT_COMMIT --> PREFLIGHT["Pre-Flight Validator<br/>(7 Automated Integrity Rules)"]
    PREFLIGHT --> PROMOTION["Human Promotion Engine<br/>(Atomic Postgres Transaction)"]
    PROMOTION --> PROD_DB["Production PostgreSQL 16<br/>(documents, chunks, graph_edges)"]
```

1. **Phase 1: Ingestion & Genesis Sealing (`POST /api/staging/sessions`):**
   - Parses raw Vietnamese statutory text using `LegalASTParser` and `CPHCEngine`.
   - Generates leaf-level `CanonicalFullyQualifiedChunk` nodes with complete ancestor context lineage.
   - Extracts initial cross-document references and seals the session into `genesis.json`.
2. **Phase 2: Surgical Refinement & AI Pre-Commit:**
   - Human reviewers and AI agents refine chunk boundaries, lead sentences, and relation edges.
   - AI agent seals its work via `stg_commit`, appending `STATUS_TRANSITION_AGENT_COMMITTED` to `wal.jsonl`.
3. **Phase 3: Pre-Flight Integrity Gate (`PreFlightValidator`):**
   - Must pass all 7 automated validation rules before human promotion can proceed:
     1. `LTREE_PATH_SYNTAX`: Dot-syntax regex conformance.
     2. `ROOT_CODE_ALIGNMENT`: Chunks root prefix matches sanitized document code.
     3. `PARENT_CHILD_CONTINUITY`: Hierarchy continuity, non-empty chunks.
     4. `STATUTORY_DATES`: Valid `effective_date`, `expiration_date >= effective_date`.
     5. `CONTENT_GROUNDING`: Non-empty verbatim and contextualized text.
     6. `GRAPH_EDGE_INTEGRITY`: Source path grounded to staged chunks, target specified.
     7. `DUPLICATE_PATH_COLLISION`: Zero duplicate chunk paths.
4. **Phase 4: Atomic Human Promotion (`POST /api/staging/sessions/{doc_code}/promote`):**
   - Strictly triggered by a human reviewer.
   - Replays WAL from genesis to head LSN, runs `PreFlightValidator`, and atomically commits document, chunks, and graph edges into PostgreSQL in a single database transaction.
   - Transitions session status to `PROMOTED` in `wal.jsonl`.

# Knowledge Graph Write Gating Invariant

- AI Agents and MCP tools have **ZERO write access** to the production `graph_edges` table (`INSERT INTO graph_edges` is prohibited in runtime sensors).
- Tool `mcp_traffic_graph_edge_write` converts proposals into `GRAPH_EDGE_PROPOSED` WAL records appended to the document's staging session.
- Coordinates are strictly canonicalized into LTREE paths (`c.path`) for both source and target, ensuring downstream pre-flight validation and promotion succeed without invariant violations.

# Usage Guide & CLI Operations

### 1. Database Schema Migrations

Run PostgreSQL DDL schema migrations (creates 7 tables, HNSW indexes, Trigram GIN indexes, and stored procedures):

```bash
uv run rag-eval legal-migrate
```

### 2. Launching Human-in-the-Loop Reviewer Web Studio

Run the full-stack FastAPI backend + React Vite frontend SPA for staging statutory documents:

```bash
# Production mode (serves compiled frontend/dist via FastAPI)
uv run rag-eval ui

# Development mode (concurrent FastAPI backend + Vite HMR on http://127.0.0.1:5173)
uv run rag-eval ui --dev
```

### 3. Model Context Protocol (MCP) Server

Launch the official MCP JSON-RPC 2.0 Server exposing all 14 canonical legal tools (6 runtime sensors + 8 staging tools) over STDIO:

```bash
uv run rag-eval legal-server
# Or with diagnostic logging:
uv run rag-eval legal-server --log-file logs/mcp_server.log
```

### 4. Headless MCP Tool Execution

Direct headless CLI runner for any of the 14 MCP tools:

```bash
# Execute hybrid search query
uv run rag-eval legal-tool mcp_traffic_hybrid_search -a '{"query": "vượt đèn đỏ xe máy", "limit": 5}'

# Inspect staging session preview
uv run rag-eval legal-tool mcp_traffic_stg_preview -a '{"doc_code": "100/2019/NĐ-CP", "limit": 10}'

# Confirm agent staging commit
uv run rag-eval legal-tool mcp_traffic_stg_commit -a '{"doc_code": "100/2019/NĐ-CP"}'
```

### 5. Quality Assurance & Verification

```bash
# Run unified QA verification pipeline (ruff, ty)
uv run python scripts/check.py
# or: make check
# or: uv run ruff check --fix && uv run ty check

# Individual checks via Makefile
make lint        # Run ruff check --fix
make typecheck   # Run ty
```

# Codebase Structure Rules

- **Codebase Exploration:** Use the `# Codebase Structure` tree below for directory layout and file locations, not `list_dir`.
- **Tree Maintenance:** Execute `uv run python scripts/update_dir_tree.py` to synchronize the directory tree in `AGENTS.md` only upon creating or deleting files/folders under `src/`, `*_server/`, or `tests/`, not during edits to existing files.

# Codebase Structure

<!-- DIR_TREE_START -->
```text
rag/
├── .agents
│   └── skills
│       └── iterative-improvement
│           └── SKILL.md
├── docs
│   ├── README.md
│   ├── bay-thuong-gap.md
│   └── demo.md
├── evidence
│   ├── PHAT_HIEN_BO_DO_LECH.md
│   ├── PHAT_HIEN_TAI_LIEU.md
│   ├── QUYET_DINH_OVERLAY.md
│   ├── README.md
│   ├── ablation.txt
│   ├── abstain_sweep.txt
│   ├── baselines.txt
│   ├── bench12k.txt
│   ├── bench2k_plain.txt
│   ├── bench2k_rr3.txt
│   ├── clause_bench.txt
│   ├── colloquial118.txt
│   ├── coverage113.txt
│   ├── diagnose_full_vs_dense.txt
│   ├── embedding_sweep.txt
│   ├── holdout80.txt
│   ├── human_eval_sheet.html
│   ├── human_eval_sheet.key.json
│   ├── latency.txt
│   ├── lexicon_by_style.txt
│   ├── overlay_eval.txt
│   ├── rerank_sweep.txt
│   ├── table_bench.txt
│   ├── table_bench_after.txt
│   ├── table_bench_before.txt
│   └── trajectory_eval.txt
├── frontend
│   ├── e2e
│   │   ├── api-contract.spec.ts
│   │   ├── helpers.ts
│   │   ├── ui-answer.spec.ts
│   │   ├── ui-confidence.spec.ts
│   │   ├── ui-hostile.spec.ts
│   │   ├── ui-rerank.spec.ts
│   │   ├── ui-scope.spec.ts
│   │   └── ui-search.spec.ts
│   ├── src
│   │   ├── components
│   │   │   ├── answer
│   │   │   │   └── LlmAnswerPanel.tsx
│   │   │   ├── checklist
│   │   │   │   ├── PreFlightChecklist.tsx
│   │   │   │   └── PromotionModal.tsx
│   │   │   ├── diff
│   │   │   │   ├── AuditHistoryDiff.tsx
│   │   │   │   ├── InlineDiffViewer.tsx
│   │   │   │   └── MutationLogList.tsx
│   │   │   ├── dualview
│   │   │   │   ├── DualViewContainer.tsx
│   │   │   │   └── StatutoryRawViewer.tsx
│   │   │   ├── editor
│   │   │   │   ├── AddChunkModal.tsx
│   │   │   │   ├── DeleteConfirmModal.tsx
│   │   │   │   └── SurgicalEditorDrawer.tsx
│   │   │   ├── graph
│   │   │   │   ├── EdgeCardList.tsx
│   │   │   │   ├── EdgeEditorModal.tsx
│   │   │   │   ├── GraphCanvas.tsx
│   │   │   │   └── VisualGraphInspector.tsx
│   │   │   ├── layout
│   │   │   │   ├── Header.tsx
│   │   │   │   ├── NavigationTabs.tsx
│   │   │   │   └── StatusBadge.tsx
│   │   │   ├── search
│   │   │   │   └── DryRunSearchSimulator.tsx
│   │   │   ├── studio
│   │   │   │   ├── DocumentReaderEditor.tsx
│   │   │   │   ├── LegalStudioContainer.tsx
│   │   │   │   ├── NodeInspectorPanel.tsx
│   │   │   │   └── TreeOutlineExplorer.tsx
│   │   │   ├── toast
│   │   │   │   └── ToastContext.tsx
│   │   │   ├── tree
│   │   │   │   ├── BreadcrumbNav.tsx
│   │   │   │   ├── CanvasToolbar.tsx
│   │   │   │   ├── SearchFilterBar.tsx
│   │   │   │   ├── TreeHierarchyCanvas.tsx
│   │   │   │   └── TreeNodeCard.tsx
│   │   │   └── upload
│   │   │       └── CreateSessionModal.tsx
│   │   ├── hooks
│   │   │   ├── useCanvasTransform.ts
│   │   │   ├── useDebounce.ts
│   │   │   ├── usePreFlightCheck.ts
│   │   │   └── useStagingSession.ts
│   │   ├── services
│   │   │   └── api.ts
│   │   ├── types
│   │   │   ├── api.ts
│   │   │   ├── diff.ts
│   │   │   ├── preflight.ts
│   │   │   ├── staging.ts
│   │   │   └── tree.ts
│   │   ├── utils
│   │   │   ├── diff.ts
│   │   │   ├── formatting.ts
│   │   │   ├── ltree.ts
│   │   │   └── sorting.ts
│   │   ├── App.tsx
│   │   ├── index.css
│   │   └── main.tsx
│   ├── index.html
│   ├── package-lock.json
│   ├── package.json
│   ├── playwright.config.ts
│   ├── postcss.config.js
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   ├── tsconfig.node.json
│   └── vite.config.ts
├── scripts
│   ├── ablation.py
│   ├── abstain_sweep.py
│   ├── backfill_facets.py
│   ├── baselines.py
│   ├── benchmark_all.sh
│   ├── build_colloquial_qrels.py
│   ├── build_qrels.py
│   ├── build_relatedness.py
│   ├── build_token_df.py
│   ├── check.py
│   ├── describe_tables.py
│   ├── diagnose_full_vs_dense.py
│   ├── diagnostic_results.json
│   ├── embedding_sweep.py
│   ├── fetch_corpus.py
│   ├── generate_colloquial_pairs.py
│   ├── human_eval.py
│   ├── latency_bench.py
│   ├── lexicon_by_style.py
│   ├── overlay_eval.py
│   ├── prune_comments.py
│   ├── purge_web_boilerplate.py
│   ├── qa_adversarial.py
│   ├── qa_bench.py
│   ├── qa_generate.py
│   ├── qa_perturb.py
│   ├── refacet.py
│   ├── rerank_sweep.py
│   ├── table_bench.py
│   ├── trajectory_eval.py
│   └── update_dir_tree.py
├── src
│   └── rag_eval
│       ├── legal
│       │   ├── db
│       │   │   ├── sql
│       │   │   │   ├── 001_initial_schema.sql
│       │   │   │   ├── 002_stored_procs.sql
│       │   │   │   ├── 003_sparse_recall.sql
│       │   │   │   ├── 004_vehicle_facet.sql
│       │   │   │   ├── 005_provision_role.sql
│       │   │   │   ├── 006_multi_vehicle_class.sql
│       │   │   │   ├── 007_phrase_variants.sql
│       │   │   │   ├── 008_phrase_pool_entry.sql
│       │   │   │   ├── 009_phrase_weight.sql
│       │   │   │   ├── 010_dense_weight.sql
│       │   │   │   ├── 011_retrieval_confidence.sql
│       │   │   │   ├── 012_annotations.sql
│       │   │   │   ├── 013_overlay.sql
│       │   │   │   ├── 014_overlay_in_search.sql
│       │   │   │   ├── 015_token_df.sql
│       │   │   │   ├── 016_overlay_overlap.sql
│       │   │   │   ├── 017_overlay_overlap_in_search.sql
│       │   │   │   ├── 018_footnote_markers.sql
│       │   │   │   ├── 019_search_doc_scope.sql
│       │   │   │   └── 020_term_relatedness.sql
│       │   │   ├── __init__.py
│       │   │   ├── connection.py
│       │   │   └── migrations.py
│       │   ├── eval
│       │   │   ├── __init__.py
│       │   │   ├── smoke_runner.py
│       │   │   └── trajectory.py
│       │   ├── ingestion
│       │   │   ├── staging
│       │   │   │   ├── __init__.py
│       │   │   │   ├── manager.py
│       │   │   │   ├── models.py
│       │   │   │   ├── operations.py
│       │   │   │   └── session.py
│       │   │   ├── __init__.py
│       │   │   ├── converter.py
│       │   │   ├── cphc.py
│       │   │   ├── facets.py
│       │   │   ├── grammar.py
│       │   │   ├── grounding.py
│       │   │   ├── layout.py
│       │   │   ├── lexer.py
│       │   │   ├── loader.py
│       │   │   ├── parser.py
│       │   │   ├── tables.py
│       │   │   ├── wal.py
│       │   │   └── xref.py
│       │   ├── mcp
│       │   │   ├── tools
│       │   │   │   ├── __init__.py
│       │   │   │   ├── embedder.py
│       │   │   │   ├── schemas.py
│       │   │   │   ├── sensors.py
│       │   │   │   └── staging.py
│       │   │   ├── __init__.py
│       │   │   ├── registry.py
│       │   │   └── server.py
│       │   ├── retrieval
│       │   │   ├── __init__.py
│       │   │   ├── annotations.py
│       │   │   ├── lexicon.py
│       │   │   ├── overlay.py
│       │   │   ├── relatedness.py
│       │   │   └── reranker.py
│       │   ├── web
│       │   │   ├── services
│       │   │   │   ├── __init__.py
│       │   │   │   ├── diff.py
│       │   │   │   ├── promotion.py
│       │   │   │   ├── tree.py
│       │   │   │   └── validation.py
│       │   │   ├── __init__.py
│       │   │   ├── app.py
│       │   │   ├── router.py
│       │   │   └── schemas.py
│       │   ├── __init__.py
│       │   ├── answer.py
│       │   ├── console.py
│       │   ├── schemas.py
│       │   ├── text.py
│       │   └── vocabulary.py
│       ├── __init__.py
│       └── cli.py
├── tests
│   ├── fixtures
│   │   ├── qrels_clause.jsonl
│   │   ├── qrels_colloquial.jsonl
│   │   ├── qrels_coverage.jsonl
│   │   ├── qrels_dev.jsonl
│   │   ├── qrels_holdout.jsonl
│   │   ├── qrels_tables.jsonl
│   │   ├── smoke_queries.jsonl
│   │   ├── smoke_queries_holdout.jsonl
│   │   └── smoke_queries_test.jsonl
│   └── __init__.py
├── .env.example
├── .gitignore
├── .python-version
├── AGENTS.md
├── LICENSE
├── Makefile
├── PROPOSAL.md
├── README.md
├── compose.yaml
├── main.py
├── pyproject.toml
└── uv.lock
```
<!-- DIR_TREE_END -->
