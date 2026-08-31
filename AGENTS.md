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
  - Always run linter auto-fix, static type checking, and unit tests concurrently in a single command: `uv run ruff check --fix && uv run ty check && uv run pytest -v` (or `./scripts/check.sh`).
- When creating source directories, add `__init__.py`.
- When configuring `pyproject.toml`, ensure `extraPaths` includes all operational roots.
- When writing Python, import at module top, unless explicitly resolving a circular dependency or optimizing a massive conditional module.

# Execution Architecture & Evaluation Invariants

- **Data Isolation & Clean-Room Boundary:**
  - Ingested datasets are partitioned into open development splits (`data/dev/<dataset>/`) and sealed binary holdout vaults (`data/.holdout_vault/<dataset>.vault`).
  - The holdout vault contains locked evaluation ground truths. The agent must NEVER inspect, read, or parse files in `data/.holdout_vault/` via `view_file` or search tools.
  - All algorithmic inspection, query triage, error diagnosis, and hyperparameter tuning must be performed exclusively against the open development split in `data/dev/`.
- **Single-Path File-Based Evaluation:**
  - All RAG systems (baselines, candidates, or new architectures) must write their generated predictions directly to a persisted file on disk (`.jsonl` or `.json`, e.g., `predictions/<dataset>_baseline.jsonl` or `./experiments/...`).
  - Evaluation must strictly consume persisted prediction files from disk via `rag-eval evaluate --predictions <path>`.
  - In-memory ephemeral direct evaluation without writing predictions to disk first is strictly prohibited to guarantee deterministic traceability, reproducibility, and auditability.

# Usage Guide & CLI Operations

### 1. Ingesting Benchmark Datasets

Download and normalize raw benchmark data into standardized JSONL files (`documents.jsonl`, `queries.jsonl`, `qrels.jsonl`):

```bash
# Download all 4 benchmarks (CUAD, QASPER, SciFact, BEIR/FiQA)
uv run rag-eval download --dataset all --output-dir ./data

# Or download individual datasets
uv run rag-eval download --dataset cuad --output-dir ./data
uv run rag-eval download --dataset qasper --output-dir ./data
uv run rag-eval download --dataset scifact --output-dir ./data
uv run rag-eval download --dataset beir_fiqa --output-dir ./data
```

### 2. Pre-building Dense Vector Index Cache

Precompute and persist the normalized neural embeddings (`BAAI/bge-small-en-v1.5`) with live `tqdm` progress tracking into `.cache/embeddings_*.npz`:

```bash
# Pre-build vector cache for all 4 benchmark datasets
./scripts/build_cache.sh all
# or: uv run rag-eval index --dataset all

# Pre-build vector cache for a specific dataset
./scripts/build_cache.sh scifact
# or: uv run rag-eval index --dataset scifact
```

### 3. Running Baseline Retrieval & Fast Testing

Execute the BM25 baseline retrieval on benchmark datasets. For fast testing, use `--max-queries` (`-n`) and optional `--seed`:

```bash
# Fast test: run only first 50 queries of SciFact
uv run rag-eval baseline --dataset scifact --output-predictions ./predictions/scifact_baseline.jsonl -n 50

# Representative sample test: run 50 random seeded queries across CUAD
uv run rag-eval baseline --dataset cuad --output-predictions ./predictions/cuad_baseline.jsonl -n 50 --seed 42

# Run baseline across all 4 benchmarks at once (defaults to fast 50-query sample)
./scripts/benchmark_all.sh 50 42
# or: make benchmark
```

### 3. Evaluating RAG System Predictions

Run evaluation on a predictions file (`.json` or `.jsonl`) against benchmark ground truths:

```bash
# Evaluate retrieval predictions (automatically saves report into ./reports/<timestamp>/<dataset>_eval.json)
uv run rag-eval evaluate --dataset cuad --predictions ./predictions/cuad_baseline.jsonl

# Explicitly override report destination to a custom file or directory
uv run rag-eval evaluate \
  --dataset scifact \
  --predictions ./predictions/scifact_baseline.jsonl \
  --output-report ./reports/scifact_eval.json
```

### 4. Development & Quality Assurance Shortcuts

```bash
# Run unified QA verification pipeline (ruff, ty, pytest)
./scripts/check.sh
# or: make check
# or: uv run ruff check --fix && uv run ty check && uv run pytest -v

# Run individual checks via Makefile
make test        # Run pytest test suite
make lint        # Run ruff check --fix
make typecheck   # Run ty
```

# Codebase Structure Rules

- **Codebase Exploration:** Use the `# Codebase Structure` tree below for directory layout and file locations, not `list_dir`.
- **Tree Maintenance:** Execute `./scripts/update_dir_tree.sh` to synchronize the directory tree in `AGENTS.md` only upon creating or deleting files/folders under `src/`, `*_server/`, or `tests/`, not during edits to existing files.


# Codebase Structure

<!-- DIR_TREE_START -->
```text
rag/
├── .agents
│   └── skills
│       └── iterative-improvement
│           └── SKILL.md
├── .gemini
│   └── mcp_config.json
├── audits
│   ├── 01_domain_and_schemas_audit.md
│   ├── 02_database_and_storage_audit.md
│   ├── 03_mcp_server_and_tools_audit.md
│   ├── 04_ingestion_and_chunking_audit.md
│   ├── 05_reasoning_and_overrides_audit.md
│   ├── 06_contract_symmetry_and_integration_audit.md
│   ├── 07_performance_security_and_shadow_mechanisms_audit.md
│   ├── 08_test_fidelity_and_verification_audit.md
│   └── index.md
├── docs
│   ├── live_verification
│   │   ├── 01_general_provisions_and_prohibited_acts.md
│   │   ├── 02_road_rules_signals_speed_overtaking.md
│   │   ├── 03_vehicles_registration_auctions_inspections.md
│   │   ├── 04_road_users_licenses_points_working_time.md
│   │   ├── 05_patrol_stopping_accidents_towing.md
│   │   ├── 06_state_management_sanction_synthesis.md
│   │   └── index.md
│   ├── 01_legal_information_structure.md
│   ├── 02_database_schema_pgvector.md
│   ├── 03_mcp_tools_and_server.md
│   ├── 04_ingestion_and_chunking_strategy.md
│   ├── 05_retrieval_and_reasoning_pipeline.md
│   ├── 06_testing_principles_and_quality_standards.md
│   ├── 07_audit_agent_team.md
│   ├── README.md
│   ├── REMEDIATION_AND_PURIFICATION_PLAN.md
│   ├── database.md
│   ├── index.md
│   └── propose_database.md
├── logs
│   └── mcp_server.log
├── scripts
│   ├── benchmark_all.sh
│   ├── check.sh
│   ├── diagnostic_results.json
│   └── update_dir_tree.sh
├── src
│   └── rag_eval
│       ├── legal
│       │   ├── db
│       │   │   ├── sql
│       │   │   │   ├── 001_initial_schema.sql
│       │   │   │   └── 002_stored_procs.sql
│       │   │   ├── __init__.py
│       │   │   ├── connection.py
│       │   │   └── migrations.py
│       │   ├── ingestion
│       │   │   ├── __init__.py
│       │   │   ├── converter.py
│       │   │   ├── cphc.py
│       │   │   ├── grammar.py
│       │   │   ├── loader.py
│       │   │   ├── parser.py
│       │   │   ├── pipeline.py
│       │   │   └── staging.py
│       │   ├── mcp
│       │   │   ├── __init__.py
│       │   │   ├── server.py
│       │   │   └── tools.py
│       │   ├── __init__.py
│       │   └── schemas.py
│       ├── __init__.py
│       └── cli.py
├── tests
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_legal_db.py
│   ├── test_legal_ingestion.py
│   ├── test_legal_mcp.py
│   └── test_legal_schemas.py
├── .env.example
├── .gitignore
├── .python-version
├── AGENTS.md
├── Makefile
├── ORIGINAL_REQUEST.md
├── PROJECT.md
├── README.md
├── compose.yaml
├── main.py
├── pyproject.toml
└── uv.lock
```
<!-- DIR_TREE_END -->
