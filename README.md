# RAG Evaluation Suite

A standardized benchmarking framework and CLI tool for evaluating Retrieval-Augmented Generation (RAG) pipelines across domain-specific datasets.

---

## What This Does

- **Automated Dataset Ingestion**: Downloads and normalizes raw benchmark datasets into standardized JSONL format (`documents.jsonl`, `queries.jsonl`, `qrels.jsonl`).
- **Domain Coverage**: Supports 4 distinct benchmark domains: Law (CUAD), Academic Research (QASPER), Science (SciFact), and Finance (BEIR/FiQA).
- **RAG Evaluation**: Evaluates retrieval accuracy (ranking, recall, hit rate) and generation quality (exact match, token F1, ROUGE-L) from RAG prediction outputs.
- **Strict Typing**: Zero-`Any` typing architecture enforced via `basedpyright`.

---

## Quickstart

### 1. Prerequisites & Installation

Ensure [`uv`](https://docs.astral.sh/uv/) is installed. Run all commands via `uv run`:

```bash
# Clone the repository
git clone <repo-url>
cd rag

# Run tests and type checker
uv run pytest -v
uv run basedpyright
```

---

## CLI Usage

### Download Datasets

Download and normalize raw benchmark data into `./data/<dataset_name>/`:

```bash
# Download all 4 benchmarks
uv run rag-eval download --dataset all

# Or download a specific dataset
uv run rag-eval download --dataset cuad
uv run rag-eval download --dataset qasper
uv run rag-eval download --dataset scifact
uv run rag-eval download --dataset beir_fiqa
```

Options:
- `--dataset`, `-d`: Dataset name (`cuad` | `qasper` | `scifact` | `beir_fiqa` | `all`)
- `--output-dir`, `-o`: Output directory (default: `./data`)

---

### Evaluate Predictions

Evaluate your RAG system's prediction file against ground truths:

```bash
# Evaluate on CUAD predictions (defaults to timestamped subfolder: ./reports/<timestamp>/cuad_eval.json)
uv run rag-eval evaluate --dataset cuad --predictions ./predictions.jsonl

# Explicitly override report destination to a specific file or custom directory
uv run rag-eval evaluate \
  --dataset scifact \
  --predictions ./predictions.json \
  --output-report ./reports/scifact_eval.json
```

Options:
- `--dataset`, `-d`: Dataset to benchmark against (`cuad` | `qasper` | `scifact` | `beir_fiqa`)
- `--predictions`, `-p`: Path to predictions JSON or JSONL file
- `--data-dir`: Directory containing cached datasets (default: `./data`)
- `--output-report`, `-r`: Optional explicit file or directory path to save JSON report. Overrides the default timestamped path.
- `--output-dir`, `-o`: Base directory for default timestamped reports (default: `./reports`)

---

## Benchmark Datasets

| Dataset | Domain | Documents | Test Queries | Ground Truth Annotations |
| :--- | :--- | :--- | :--- | :--- |
| **CUAD** | Legal Contracts | 510 full contracts | 6,702 clause queries | Document IDs, clause answers, character spans |
| **QASPER** | Academic Papers | 416 research papers | 1,451 paper questions | Document IDs, answer strings, evidence spans |
| **SciFact** | Science / BioMed | 5,183 scientific abstracts | 300 claims | Document IDs (evidence abstracts) |
| **BEIR/FiQA** | Financial QA & IR | 57,600 forum posts | 648 financial queries | Document IDs (relevant contexts) |

---

## Prediction Input Format

Your RAG system should output predictions in JSON or JSONL format. Each entry supports both retrieval doc IDs and generated answer strings:

### JSONL Format (`predictions.jsonl`)
```json
{"query_id": "1", "retrieved_doc_ids": ["31715818", "14717500"], "generated_answer": "Yes, 0-dimensional materials show inductive properties."}
{"query_id": "3", "retrieved_doc_ids": ["14717500"], "generated_answer": null}
```

### JSON Format (`predictions.json`)
```json
[
  {
    "query_id": "1",
    "retrieved_doc_ids": ["31715818", "14717500"],
    "generated_answer": "Yes, 0-dimensional materials show inductive properties.",
    "latency_ms": 42.5
  }
]
```

---

## Evaluation Metrics

### Retrieval (IR) Metrics
- **Hit Rate @ K** ($K \in \{1, 3, 5, 10\}$): Binary indicator of whether at least one relevant document appears in the top-$K$ results.
- **Recall @ K** ($K \in \{1, 3, 5, 10\}$): Proportion of all relevant documents retrieved within the top-$K$.
- **Precision @ K** ($K \in \{1, 3, 5, 10\}$): Proportion of retrieved documents in the top-$K$ that are relevant.
- **MRR @ 10** (Mean Reciprocal Rank): Reciprocal rank ($1/\text{rank}$) of the first relevant document found within the top-10.
- **NDCG @ 10** (Normalized Discounted Cumulative Gain): Measures ranking quality with logarithmic position discounting.

### Generation Metrics
- **Exact Match (EM)**: Normalized binary match between generated text and ground-truth answers (ignoring casing, punctuation, and articles).
- **Token F1**: Harmonic mean of token-level unigram precision and recall against reference answers.
- **ROUGE-L**: Longest Common Subsequence (LCS) F1 score measuring sentence-level structural similarity.

---

## Repository Structure

```text
rag/
├── data/                       # Normalized local benchmark datasets (JSONL)
│   ├── beir_fiqa/
│   ├── cuad/
│   ├── qasper/
│   └── scifact/
├── src/
│   └── rag_eval/
│       ├── datasets/           # Benchmark downloaders and parsers
│       │   ├── base.py         # In-memory benchmark container and JSONL serialiser
│       │   ├── beir_fiqa.py    # BEIR/FiQA financial IR parser
│       │   ├── cuad.py         # CUAD legal contract parser
│       │   ├── qasper.py       # QASPER academic paper QA parser
│       │   └── scifact.py      # SciFact claim verification parser
│       ├── cli.py              # CLI commands (`download`, `evaluate`)
│       ├── metrics.py          # Pure IR and lexical evaluation algorithms
│       └── schemas.py          # Strictly typed Pydantic models (zero Any)
├── stubs/                      # Custom type stubs for third-party libraries
├── tests/                      # Unit test suite for metrics, schemas, and datasets
├── pyproject.toml              # Build backend and dependency configuration
└── README.md
```

---

## Development

```bash
# Run unit tests
uv run pytest -v

# Run static type checker
uv run basedpyright
```
