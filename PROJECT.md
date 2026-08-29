# Project: Vietnamese Traffic Law Agentic RAG Platform

## Architecture
PostgreSQL 16 + pgvector unified single-engine architecture with ltree, pg_trgm, btree_gin, and unaccent extensions.
7-tool Model Context Protocol (MCP) JSON-RPC 2.0 server providing deterministic domain primitives.
Context-Preserving Hierarchical Chunking (CPHC) generating Canonical Fully Qualified Chunks (CFQC).
Multi-hop reasoning engine executing deterministic beam-search graph traversal over the Decoupled Normative Triad (Law <-> Decree <-> QCVN) with algebraic Scope Override resolution and cryptographic Chain of Custody (CoC) audit trails.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Pydantic Taxonomy Schemas | Comprehensive enums, extraction models, DAG planning models, CoC schemas | M1 | docs/01, docs/04, docs/05 |
| 2 | DB Containerization & Schema | Modern `compose.yaml`, 7 core tables DDL, GIN/GIST/HNSW indexes | M2 | docs/02 |
| 3 | In-DB Stored Procedures & RRF | `hybrid_legal_search` with RRF and `traverse_normative_triad` recursive CTE | M2 | docs/02 |
| 4 | Async Connection Pool | `asyncpg` pool manager with health check and lifecycle management | M2 | docs/02 |
| 5 | CPHC 6-Tier Regex Parser | AST parser extracting document hierarchy from Vietnamese legal text | M3 | docs/04 |
| 6 | Prefix Synthesis & CFQC | Synthesizing Article headers + Clause lead sentences for complete context | M3 | docs/04 |
| 7 | Cross-Reference Graph Linker | Regex + reference extraction linking 9 statutory relation types | M3 | docs/04 |
| 8 | Idempotent Bulk Loader | High-throughput PostgreSQL ingestion with conflict handling | M3 | docs/04 |
| 9 | MCP Server & Protocols | JSON-RPC 2.0 Server with Stdio and SSE transport layers | M4 | docs/03 |
| 10 | MCP Specialized 7-Tool Suite | 7 high-bandwidth domain tools with JSON Schema validation | M4 | docs/03 |
| 11 | Query Decomposer & DAG Planner | Intent classification (6 classes) and sub-goal DAG construction | M5 | docs/05 |
| 12 | Deterministic Beam Traverser | Multi-hop graph search (K=3, Dmax=4) across normative triad | M5 | docs/05 |
| 13 | Scope Override & Conflict Engine | Signaling precedence inequality and emergency privilege lattices | M5 | docs/05 |
| 14 | Cryptographic Chain of Custody | SHA-256 evidence hashing, AST citation grounding validator | M5 | docs/05 |
| 15 | CLI Commands Suite | `rag-eval legal-migrate`, `legal-ingest`, `legal-server`, `legal-query` | M6 | ORIGINAL_REQUEST |
| 16 | Unit, Integration & E2E Tests | Mocked DB & live integration tests passing `./scripts/check.sh` | M6 & E2E | ORIGINAL_REQUEST |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Domain Models & Strict Schemas | `src/rag_eval/legal/schemas.py` | none | DONE |
| M2 | Database & Migrations Subsystem | `compose.yaml`, `src/rag_eval/legal/db/` | M1 | DONE |
| M3 | CPHC Ingestion Pipeline | `src/rag_eval/legal/ingestion/` | M1, M2 | DONE |
| M4 | MCP JSON-RPC 2.0 Server | `src/rag_eval/legal/mcp/` | M1, M2, M3 | DONE |
| M5 | Multi-Hop Reasoning & Overrides | `src/rag_eval/legal/reasoning/` | M1, M4 | DONE |
| M6 | CLI Commands & QA Integration | `src/rag_eval/cli.py`, `tests/` | M1-M5 | DONE |
| E2E | Requirement-Driven E2E Test Suite | `tests/legal/`, `TEST_READY.md` | M1 | DONE |

## Interface Contracts
### `src/rag_eval/legal/schemas.py` [VERIFIED & COMPLETE]
- Exposes all core enums: `VehicleCategory`, `ViolationCategory`, `NormRole`, `ActorCategory`, `GraphRelationType`, `SignCategoryEnum`, `CacheValidationStatus`, `LegalIntent`, `SignalTier`, `Temporality`, `SubGoalType`.
- Exposes Pydantic models: `FineBounds`, `AdditionalSanctions`, `DemeritPointDeduction`, `ExceptionMetadata`, `ReferencedEntity`, `LegalNormExtraction`, `CanonicalFullyQualifiedChunk`, `ExtractedEntities`, `SubGoalNode`, `ExecutionPlanDAG`, `TrafficSignalCommand`, `ConflictEvaluationResult`, `ChainOfCustodyStep`, `ChainOfCustodyPlanSummary`, `PrecedenceResolutionAudit`, `TemporalValidationAudit`, `AntiHallucinationAudit`, `ChainOfCustody`.

### `src/rag_eval/legal/db/` [VERIFIED & COMPLETE]
- `get_db_pool(dsn: str | None = None)` -> `asyncpg.Pool`
- `close_db_pool()` -> `None`
- `check_db_health(pool: asyncpg.Pool)` -> `bool`
- `run_migrations(pool: asyncpg.Pool)` -> `list[str]`
- SQL DDL in `src/rag_eval/legal/db/sql/001_initial_schema.sql`
- Stored procedures in `src/rag_eval/legal/db/sql/002_stored_procs.sql` (`hybrid_legal_search`, `traverse_normative_triad`, `expand_vehicle_category`, `resolve_scope_overrides`, `query_runtime_knowledge_cache`)

### `src/rag_eval/legal/ingestion/` [VERIFIED & COMPLETE]
- `LegalASTParser.parse_document(doc_code, raw_text)` -> `ASTNode`
- `CPHCEngine.synthesize_chunks(ast_root)` -> `list[CanonicalFullyQualifiedChunk]`
- `DeterministicGraphLinker.extract_deterministic_edges(chunk)` -> `list[dict]`
- `PostgresBulkLoader.ingest_document(doc_meta, chunks, edges)` -> `int`
- `LegalIngestionPipeline.ingest_file(file_path)` -> `dict`

### `src/rag_eval/legal/mcp/` [VERIFIED & COMPLETE]
- `create_mcp_server()` -> MCP Server instance with 7 registered tool handlers:
  - `mcp_traffic_corpus_validate`
  - `mcp_traffic_hybrid_search`
  - `mcp_traffic_hierarchical_navigate`
  - `mcp_traffic_graph_traverse`
  - `mcp_traffic_scope_override_detect`
  - `mcp_traffic_sign_catalog_lookup`
  - `mcp_traffic_knowledge_cache_query` / `mcp_traffic_knowledge_cache_write`

### `src/rag_eval/legal/reasoning/` [VERIFIED & COMPLETE]
- `LegalQueryPlanner.plan(query_text)` -> `ExecutionPlanDAG`
- `TriadBeamTraverser.traverse(plan, mcp_client)` -> `list[TraversalPath]`
- `ScopeOverrideEngine.resolve_conflict(...)` -> `ConflictEvaluationResult`
- `ChainOfCustodyGenerator.generate(...)` -> `ChainOfCustody`

## Code Layout
```text
src/rag_eval/
├── legal/
│   ├── __init__.py
│   ├── schemas.py                 # M1: Domain taxonomy, Pydantic models, DAG & CoC schemas (DONE)
│   ├── db/                        # M2: Database Subsystem & Containerization (DONE)
│   │   ├── __init__.py
│   │   ├── connection.py          # M2: asyncpg connection pool manager & health checks
│   │   ├── migrations.py          # M2: DDL schema migration runner
│   │   └── sql/
│   │       ├── 001_initial_schema.sql # M2: Tables, extensions, enums, indexes
│   │       └── 002_stored_procs.sql   # M2: RRF hybrid search & recursive CTE
│   ├── ingestion/                 # M3: CPHC Ingestion Pipeline & AST Parser (DONE)
│   │   ├── __init__.py
│   │   ├── grammar.py             # M3: 6-tier regex grammar rules
│   │   ├── parser.py              # M3: AST parser extracting hierarchy
│   │   ├── cphc.py                # M3: CFQC prefix synthesis & context preservation
│   │   ├── graph_linker.py        # M3: Cross-reference relational linker
│   │   ├── loader.py              # M3: Idempotent PostgreSQL bulk loader
│   │   └── pipeline.py            # M3: End-to-end ingestion pipeline runner
│   ├── mcp/                       # M4: 7-Tool MCP JSON-RPC 2.0 Server (DONE)
│   │   ├── __init__.py
│   │   ├── server.py              # M4: MCP Server & transport
│   │   └── tools.py               # M4: 7 Tool handlers with JSON schema validation
│   └── reasoning/                 # M5: Multi-Hop Reasoning & Overrides (DONE)
│       ├── __init__.py
│       ├── planner.py             # M5: Query decomposer, intent & DAG builder
│       ├── traverser.py           # M5: Deterministic beam search graph traverser
│       ├── overrides.py           # M5: Statutory precedence & emergency privilege engine
│       └── chain_of_custody.py    # M5: CoC generator & AST citation grounding validator
├── cli.py                         # M6: CLI commands (legal-migrate, legal-ingest, legal-server, legal-query) (DONE)
compose.yaml                       # M2: Docker Compose V2 PostgreSQL 16 + pgvector (DONE)
.env.example                       # M2: Environment configuration template (DONE)
tests/
├── test_legal_schemas.py          # M1 unit tests (18 passed)
├── test_legal_db.py               # M2 unit tests (17 passed)
├── test_legal_ingestion.py        # M3 unit tests (15 passed)
├── test_legal_e2e.py              # Unified E2E runner (125 tests)
└── legal/                         # E2E test suite framework (DONE)
```
