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
│   ├── 01_legal_information_structure.md
│   ├── 02_database_schema_pgvector.md
│   ├── 03_mcp_tools_and_server.md
│   ├── 04_ingestion_and_chunking_strategy.md
│   ├── 05_retrieval_and_reasoning_pipeline.md
│   ├── 06_testing_principles_and_quality_standards.md
│   ├── README.md
│   └── index.md
├── scripts
│   ├── benchmark_all.sh
│   ├── check.sh
│   └── update_dir_tree.sh
├── src
│   └── rag_eval
│       ├── baseline
│       │   ├── __init__.py
│       │   ├── bm25.py
│       │   ├── chunking.py
│       │   ├── dense.py
│       │   └── pipeline.py
│       ├── datasets
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── beir_fiqa.py
│       │   ├── cuad.py
│       │   ├── qasper.py
│       │   └── scifact.py
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
│       │   │   ├── benchmark_gen.py
│       │   │   ├── cphc.py
│       │   │   ├── grammar.py
│       │   │   ├── graph_linker.py
│       │   │   ├── loader.py
│       │   │   ├── parser.py
│       │   │   └── pipeline.py
│       │   ├── mcp
│       │   │   ├── __init__.py
│       │   │   ├── server.py
│       │   │   └── tools.py
│       │   ├── reasoning
│       │   │   ├── __init__.py
│       │   │   ├── chain_of_custody.py
│       │   │   ├── overrides.py
│       │   │   ├── pipeline.py
│       │   │   ├── planner.py
│       │   │   └── traverser.py
│       │   ├── __init__.py
│       │   └── schemas.py
│       ├── __init__.py
│       ├── cli.py
│       ├── metrics.py
│       └── schemas.py
├── tests
│   ├── legal
│   │   ├── fixtures
│   │   │   ├── __init__.py
│   │   │   ├── laws_data.py
│   │   │   ├── scenarios_data.py
│   │   │   └── signs_data.py
│   │   ├── mocks
│   │   │   ├── __init__.py
│   │   │   ├── mock_db.py
│   │   │   ├── mock_mcp.py
│   │   │   └── mock_reasoning.py
│   │   ├── tier1_features
│   │   │   ├── __init__.py
│   │   │   ├── test_r1_schemas.py
│   │   │   ├── test_r2_database.py
│   │   │   ├── test_r3_ingestion.py
│   │   │   ├── test_r4_mcp_tools.py
│   │   │   ├── test_r5_reasoning.py
│   │   │   └── test_r6_cli.py
│   │   ├── tier2_boundary
│   │   │   ├── __init__.py
│   │   │   ├── test_boundary_alcohol.py
│   │   │   ├── test_boundary_fines.py
│   │   │   ├── test_boundary_inputs.py
│   │   │   ├── test_boundary_speed.py
│   │   │   ├── test_boundary_temporal.py
│   │   │   └── test_boundary_weights.py
│   │   ├── tier3_combinatorial
│   │   │   ├── __init__.py
│   │   │   └── test_cross_feature_matrix.py
│   │   ├── tier4_scenarios
│   │   │   ├── __init__.py
│   │   │   └── test_multi_hop_scenarios.py
│   │   ├── __init__.py
│   │   ├── runners.py
│   │   └── test_challenger_r6.py
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_adversarial_r2.py
│   ├── test_adversarial_r4.py
│   ├── test_adversarial_r5.py
│   ├── test_adversarial_r5_stress.py
│   ├── test_baseline.py
│   ├── test_challenger_deep_empirical.py
│   ├── test_challenger_r1_stress.py
│   ├── test_challenger_r3_stress.py
│   ├── test_cli.py
│   ├── test_datasets.py
│   ├── test_legal_db.py
│   ├── test_legal_e2e.py
│   ├── test_legal_ingestion.py
│   ├── test_legal_mcp.py
│   ├── test_legal_reasoning.py
│   ├── test_legal_schemas.py
│   ├── test_legal_tier1.py
│   ├── test_legal_tier2.py
│   ├── test_legal_tier3.py
│   ├── test_legal_tier4.py
│   ├── test_metrics.py
│   └── test_schemas.py
├── .env.example
├── .gitignore
├── .python-version
├── AGENTS.md
├── Makefile
├── PROJECT.md
├── README.md
├── compose.yaml
├── main.py
├── pyproject.toml
└── uv.lock
```
<!-- DIR_TREE_END -->
