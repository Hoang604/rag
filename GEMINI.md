- Keep all package management and python execution uv-bound: use `uv add` for packages, and run all scripts (workspace or external) and inline strings with `uv run`. Run with `uv run`, not `python`/`python3`.
- Strictly enforce static constraints and environment boundaries before execution; never assume lenient defaults. When writing Python code, strictly adhere to `basedpyright` rules:
  - **Collections:** Always annotate empty collections (e.g., use `ids: list[int] = []`, not `ids = []`).
  - **Nullability:** Explicitly handle `None` when passing variables to strictly typed arguments (e.g., check `if var is not None:`, not passing `int | None`).
  - **Type Resolution:** Resolve typing issues with explicit annotations, type narrowing (`isinstance`, `assert`), or type-safe standard library constructs (e.g., `len(arr)`), not with `# pyright: ignore` or disabling linter rules.
  - **Model Attributes:** Use direct, type-safe attribute access on domain models and Pydantic schemas (e.g., `context.reference.dialect if context.reference else "en-US"`), not defensive `hasattr()` or `getattr()` lookups.
- Linter & Code Quality Rules:
  - **Exceptions:** Catch explicit, concrete exception classes (e.g., `(RuntimeError, ValueError, TypeError, OSError, FileNotFoundError)`), not blind `Exception` (`BLE001`).
  - **Iterator Access:** Use `next(iter(...))` to retrieve the first element from mappings or iterables, not `list(...)[0]` (`RUF015`).
  - **Feature Defaults:** Make dialect extensions and counterpart phoneme resolutions opt-in (`default=False`), not enabled by default over canonical token resolution.
- Quality Assurance & Verification:
  - Always run linter auto-fix, static type checking, and unit tests concurrently in a single command: `uv run ruff check --fix && uv run basedpyright && uv run pytest -v` (or `./scripts/check.sh`).
- When creating source directories, add `__init__.py`.
- When configuring `pyproject.toml`, ensure `extraPaths` includes all operational roots.
- When writing Python, import at module top, unless explicitly resolving a circular dependency or optimizing a massive conditional module.

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
# Run unified QA verification pipeline (ruff, basedpyright, pytest)
./scripts/check.sh
# or: make check
# or: uv run ruff check --fix && uv run basedpyright && uv run pytest -v

# Run individual checks via Makefile
make test        # Run pytest test suite
make lint        # Run ruff check --fix
make typecheck   # Run basedpyright
```

# Codebase Structure Rules

- **Codebase Exploration:** Use the `# Codebase Structure` tree below for directory layout and file locations, not `list_dir`.
- **Tree Maintenance:** Execute `./scripts/update_dir_tree.sh` to synchronize the directory tree in `GEMINI.md` only upon creating or deleting files/folders under `src/`, `*_server/`, or `tests/`, not during edits to existing files.


# Codebase Structure

<!-- DIR_TREE_START -->
```text
rag/
├── .agents
│   └── skills
│       └── iterative-improvement
│           └── SKILL.md
├── .ruff_cache
│   ├── 0.16.3
│   │   ├── 11112199446812463272
│   │   ├── 17831153981841827116
│   │   ├── 3155087360883495795
│   │   ├── 7122368123262901865
│   │   ├── 7123161447614724338
│   │   └── 8151934279000226171
│   ├── .gitignore
│   └── CACHEDIR.TAG
├── experiments
│   ├── iter_000_baseline_20260818_212253
│   │   └── report.md
│   ├── iter_001_candidate_pool_100_20260818_212850
│   │   ├── predictions
│   │   │   ├── beir_fiqa_baseline.jsonl
│   │   │   ├── cuad_baseline.jsonl
│   │   │   ├── qasper_baseline.jsonl
│   │   │   └── scifact_baseline.jsonl
│   │   ├── reports
│   │   │   ├── beir_fiqa_eval.json
│   │   │   ├── cuad_eval.json
│   │   │   ├── qasper_eval.json
│   │   │   └── scifact_eval.json
│   │   ├── failures.md
│   │   ├── hypothesis.md
│   │   └── report.md
│   ├── iter_002_bm25_stemming_20260818_214000
│   │   ├── predictions
│   │   │   ├── beir_fiqa_baseline.jsonl
│   │   │   ├── cuad_baseline.jsonl
│   │   │   ├── qasper_baseline.jsonl
│   │   │   └── scifact_baseline.jsonl
│   │   ├── reports
│   │   │   ├── beir_fiqa_eval.json
│   │   │   ├── cuad_eval.json
│   │   │   ├── qasper_eval.json
│   │   │   └── scifact_eval.json
│   │   ├── failures.md
│   │   ├── hypothesis.md
│   │   └── report.md
│   ├── iter_003_weighted_rrf_20260818_223500
│   │   ├── predictions
│   │   │   ├── beir_fiqa_baseline.jsonl
│   │   │   ├── cuad_baseline.jsonl
│   │   │   ├── qasper_baseline.jsonl
│   │   │   └── scifact_baseline.jsonl
│   │   ├── reports
│   │   │   ├── beir_fiqa_eval.json
│   │   │   ├── cuad_eval.json
│   │   │   ├── qasper_eval.json
│   │   │   └── scifact_eval.json
│   │   ├── failures.md
│   │   ├── hypothesis.md
│   │   └── report.md
│   ├── iter_004_bm25_tuning_20260818_224700
│   │   ├── predictions
│   │   │   ├── beir_fiqa_baseline.jsonl
│   │   │   ├── cuad_baseline.jsonl
│   │   │   ├── qasper_baseline.jsonl
│   │   │   └── scifact_baseline.jsonl
│   │   ├── reports
│   │   │   ├── beir_fiqa_eval.json
│   │   │   ├── cuad_eval.json
│   │   │   ├── qasper_eval.json
│   │   │   └── scifact_eval.json
│   │   ├── failures.md
│   │   ├── hypothesis.md
│   │   └── report.md
│   ├── iter_005_multichunk_pooling_20260818_230000
│   │   ├── predictions
│   │   │   ├── beir_fiqa_baseline.jsonl
│   │   │   ├── cuad_baseline.jsonl
│   │   │   ├── qasper_baseline.jsonl
│   │   │   └── scifact_baseline.jsonl
│   │   ├── reports
│   │   │   ├── beir_fiqa_eval.json
│   │   │   ├── cuad_eval.json
│   │   │   ├── qasper_eval.json
│   │   │   └── scifact_eval.json
│   │   ├── failures.md
│   │   ├── hypothesis.md
│   │   └── report.md
│   ├── iter_006_bge_query_instruction_20260818_231500
│   │   ├── predictions
│   │   │   ├── beir_fiqa_baseline.jsonl
│   │   │   ├── cuad_baseline.jsonl
│   │   │   ├── qasper_baseline.jsonl
│   │   │   └── scifact_baseline.jsonl
│   │   ├── reports
│   │   │   ├── beir_fiqa_eval.json
│   │   │   ├── cuad_eval.json
│   │   │   ├── qasper_eval.json
│   │   │   └── scifact_eval.json
│   │   ├── failures.md
│   │   ├── hypothesis.md
│   │   └── report.md
│   ├── iter_007_chunk_size_1000_20260818_233000
│   │   ├── predictions
│   │   │   ├── beir_fiqa_baseline.jsonl
│   │   │   ├── cuad_baseline.jsonl
│   │   │   ├── qasper_baseline.jsonl
│   │   │   └── scifact_baseline.jsonl
│   │   ├── reports
│   │   │   ├── beir_fiqa_eval.json
│   │   │   ├── cuad_eval.json
│   │   │   ├── qasper_eval.json
│   │   │   └── scifact_eval.json
│   │   ├── failures.md
│   │   ├── hypothesis.md
│   │   └── report.md
│   ├── iter_008_chunk_size_750_20260818_235800
│   │   ├── predictions
│   │   │   ├── beir_fiqa_baseline.jsonl
│   │   │   ├── cuad_baseline.jsonl
│   │   │   ├── qasper_baseline.jsonl
│   │   │   └── scifact_baseline.jsonl
│   │   ├── reports
│   │   │   ├── beir_fiqa_eval.json
│   │   │   ├── cuad_eval.json
│   │   │   ├── qasper_eval.json
│   │   │   └── scifact_eval.json
│   │   ├── failures.md
│   │   ├── hypothesis.md
│   │   └── report.md
│   ├── iter_009_convex_score_fusion_20260819_001500
│   │   ├── predictions
│   │   │   ├── beir_fiqa_baseline.jsonl
│   │   │   ├── cuad_baseline.jsonl
│   │   │   ├── qasper_baseline.jsonl
│   │   │   └── scifact_baseline.jsonl
│   │   ├── reports
│   │   │   ├── beir_fiqa_eval.json
│   │   │   ├── cuad_eval.json
│   │   │   ├── qasper_eval.json
│   │   │   └── scifact_eval.json
│   │   ├── failures.md
│   │   ├── hypothesis.md
│   │   └── report.md
│   ├── iter_010_bm25_bigrams_20260819_003000
│   │   ├── predictions
│   │   │   ├── beir_fiqa_baseline.jsonl
│   │   │   ├── cuad_baseline.jsonl
│   │   │   ├── qasper_baseline.jsonl
│   │   │   └── scifact_baseline.jsonl
│   │   ├── reports
│   │   │   ├── beir_fiqa_eval.json
│   │   │   ├── cuad_eval.json
│   │   │   ├── qasper_eval.json
│   │   │   └── scifact_eval.json
│   │   ├── failures.md
│   │   ├── hypothesis.md
│   │   └── report.md
│   ├── iter_011_bge_base_20260819_004500
│   │   ├── predictions
│   │   │   ├── beir_fiqa_baseline.jsonl
│   │   │   ├── cuad_baseline.jsonl
│   │   │   ├── qasper_baseline.jsonl
│   │   │   └── scifact_baseline.jsonl
│   │   ├── reports
│   │   │   ├── beir_fiqa_eval.json
│   │   │   ├── cuad_eval.json
│   │   │   ├── qasper_eval.json
│   │   │   └── scifact_eval.json
│   │   ├── failures.md
│   │   ├── hypothesis.md
│   │   └── report.md
│   ├── iter_012_bm25_stopwords_20260819_011500
│   │   ├── predictions
│   │   │   ├── beir_fiqa_baseline.jsonl
│   │   │   ├── cuad_baseline.jsonl
│   │   │   ├── qasper_baseline.jsonl
│   │   │   └── scifact_baseline.jsonl
│   │   ├── reports
│   │   │   ├── beir_fiqa_eval.json
│   │   │   ├── cuad_eval.json
│   │   │   ├── qasper_eval.json
│   │   │   └── scifact_eval.json
│   │   ├── failures.md
│   │   ├── hypothesis.md
│   │   └── report.md
│   ├── iter_013_candidate_pool_150_20260819_013000
│   │   ├── predictions
│   │   │   ├── beir_fiqa_baseline.jsonl
│   │   │   ├── cuad_baseline.jsonl
│   │   │   ├── qasper_baseline.jsonl
│   │   │   └── scifact_baseline.jsonl
│   │   ├── reports
│   │   │   ├── beir_fiqa_eval.json
│   │   │   ├── cuad_eval.json
│   │   │   ├── qasper_eval.json
│   │   │   └── scifact_eval.json
│   │   ├── failures.md
│   │   ├── hypothesis.md
│   │   └── report.md
│   ├── iter_014_candidate_pool_200_20260819_014500
│   │   ├── predictions
│   │   │   ├── beir_fiqa_baseline.jsonl
│   │   │   ├── cuad_baseline.jsonl
│   │   │   ├── qasper_baseline.jsonl
│   │   │   └── scifact_baseline.jsonl
│   │   ├── reports
│   │   │   ├── beir_fiqa_eval.json
│   │   │   ├── cuad_eval.json
│   │   │   ├── qasper_eval.json
│   │   │   └── scifact_eval.json
│   │   ├── failures.md
│   │   ├── hypothesis.md
│   │   └── report.md
│   ├── iter_015_rrf_k10_20260819_021000
│   │   ├── predictions
│   │   │   ├── beir_fiqa_baseline.jsonl
│   │   │   ├── cuad_baseline.jsonl
│   │   │   ├── qasper_baseline.jsonl
│   │   │   └── scifact_baseline.jsonl
│   │   ├── reports
│   │   │   ├── beir_fiqa_eval.json
│   │   │   ├── cuad_eval.json
│   │   │   ├── qasper_eval.json
│   │   │   └── scifact_eval.json
│   │   ├── failures.md
│   │   ├── hypothesis.md
│   │   └── report.md
│   ├── iter_016_bm25_b060_20260819_022500
│   │   ├── predictions
│   │   │   ├── beir_fiqa_baseline.jsonl
│   │   │   ├── cuad_baseline.jsonl
│   │   │   ├── qasper_baseline.jsonl
│   │   │   └── scifact_baseline.jsonl
│   │   ├── reports
│   │   │   ├── beir_fiqa_eval.json
│   │   │   ├── cuad_eval.json
│   │   │   ├── qasper_eval.json
│   │   │   └── scifact_eval.json
│   │   ├── failures.md
│   │   ├── hypothesis.md
│   │   └── report.md
│   ├── iter_017_dense_weight_3_20260819_024500
│   │   ├── predictions
│   │   │   ├── beir_fiqa_baseline.jsonl
│   │   │   ├── cuad_baseline.jsonl
│   │   │   ├── qasper_baseline.jsonl
│   │   │   └── scifact_baseline.jsonl
│   │   ├── reports
│   │   │   ├── beir_fiqa_eval.json
│   │   │   ├── cuad_eval.json
│   │   │   ├── qasper_eval.json
│   │   │   └── scifact_eval.json
│   │   ├── failures.md
│   │   ├── hypothesis.md
│   │   └── report.md
│   ├── iter_018_dense_weight_15_20260819_030500
│   │   ├── predictions
│   │   │   ├── beir_fiqa_baseline.jsonl
│   │   │   ├── cuad_baseline.jsonl
│   │   │   ├── qasper_baseline.jsonl
│   │   │   └── scifact_baseline.jsonl
│   │   ├── reports
│   │   │   ├── beir_fiqa_eval.json
│   │   │   ├── cuad_eval.json
│   │   │   ├── qasper_eval.json
│   │   │   └── scifact_eval.json
│   │   ├── failures.md
│   │   ├── hypothesis.md
│   │   └── report.md
│   ├── iter_019_bm25_k1_20_20260819_032500
│   │   ├── predictions
│   │   │   ├── beir_fiqa_baseline.jsonl
│   │   │   ├── cuad_baseline.jsonl
│   │   │   ├── qasper_baseline.jsonl
│   │   │   └── scifact_baseline.jsonl
│   │   ├── reports
│   │   │   ├── beir_fiqa_eval.json
│   │   │   ├── cuad_eval.json
│   │   │   ├── qasper_eval.json
│   │   │   └── scifact_eval.json
│   │   ├── failures.md
│   │   ├── hypothesis.md
│   │   └── report.md
│   ├── iter_020_clean_title_prefix_20260819_034500
│   │   ├── predictions
│   │   │   ├── beir_fiqa_baseline.jsonl
│   │   │   ├── cuad_baseline.jsonl
│   │   │   ├── qasper_baseline.jsonl
│   │   │   └── scifact_baseline.jsonl
│   │   ├── reports
│   │   │   ├── beir_fiqa_eval.json
│   │   │   ├── cuad_eval.json
│   │   │   ├── qasper_eval.json
│   │   │   └── scifact_eval.json
│   │   ├── failures.md
│   │   ├── hypothesis.md
│   │   └── report.md
│   ├── iter_021_extended_stopwords_20260819_040500
│   │   ├── predictions
│   │   │   ├── beir_fiqa_baseline.jsonl
│   │   │   ├── cuad_baseline.jsonl
│   │   │   ├── qasper_baseline.jsonl
│   │   │   └── scifact_baseline.jsonl
│   │   ├── reports
│   │   │   ├── beir_fiqa_eval.json
│   │   │   ├── cuad_eval.json
│   │   │   ├── qasper_eval.json
│   │   │   └── scifact_eval.json
│   │   ├── failures.md
│   │   ├── hypothesis.md
│   │   └── report.md
│   └── ledger.md
├── predictions
│   ├── beir_fiqa_baseline.jsonl
│   ├── cuad_baseline.jsonl
│   ├── qasper_baseline.jsonl
│   └── scifact_baseline.jsonl
├── reports
│   ├── beir_fiqa_eval.json
│   ├── cuad_eval.json
│   ├── qasper_eval.json
│   └── scifact_eval.json
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
│       ├── __init__.py
│       ├── cli.py
│       ├── metrics.py
│       └── schemas.py
├── stubs
│   ├── datasets
│   │   └── __init__.pyi
│   ├── fastembed
│   │   └── __init__.pyi
│   └── transformers
│       └── __init__.pyi
├── tests
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_baseline.py
│   ├── test_cli.py
│   ├── test_datasets.py
│   ├── test_metrics.py
│   └── test_schemas.py
├── .gitignore
├── .python-version
├── GEMINI.md
├── Makefile
├── README.md
├── main.py
├── pyproject.toml
└── uv.lock
```
<!-- DIR_TREE_END -->
