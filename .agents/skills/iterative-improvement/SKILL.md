---
name: iterative-improvement
description: Autonomous, continuous data-driven optimization loop for IR/RAG systems producing timestamped, non-destructive experiment artifacts in ./experiments/ with in-turn self-healing verification.
disable-model-invocation: true
---

# Iterative Improvement Workflow

An autonomous, non-interactive execution protocol for optimizing Information Retrieval and RAG pipelines toward their empirical performance ceiling. The agent executes consecutive iteration cycles continuously without pausing or prompting the user, preserving every run's reports and predictions in timestamped folders under `./experiments/`.

## Core Terminology & Leading Words

- **Autonomous loop**: Continuous, unattended cycle execution (Hypothesis $\rightarrow$ Mutate $\rightarrow$ Self-heal $\rightarrow$ Benchmark $\rightarrow$ Evaluate $\rightarrow$ Ledger $\rightarrow$ Next Iteration) until empirical ceiling termination.
- **Self-healing green gate**: Mandatory in-turn repair loop where the agent immediately resolves all linter, typecheck, or test failures in-flight until `./scripts/check.sh` exits 0 before launching benchmarks.
- **Timestamped isolation**: Every iteration writes to its own non-destructive directory (`iter_NNN_<name>_<YYYYMMDD_HHMMSS>/`) containing its isolated reports, predictions, hypothesis, and failure triage.
- **Experiment ledger**: The central immutable log (`./experiments/ledger.md`) indexing every timestamped iteration, hypothesis, metric delta, and promotion decision.
- **Clean room**: Absolute isolation of ground truth (`qrels`) and test queries from indexing, candidate selection, and ranking logic.
- **Ablation**: Mutating exactly one isolated variable (e.g., scoring function, chunk size, fusion weight) per iteration cycle.
- **Delta gate**: The binary threshold requiring cross-dataset metric gain ($\Delta > 0$) to promote code to the active baseline.
- **Plateau**: Successive orthogonal iterations yielding negligible gain ($\Delta \text{NDCG@10} \le 0.005$), signaling the empirical ceiling.

---

## Directory & Artifact Structure

All experiment artifacts must be preserved with timestamps inside `./experiments/` to prevent overwrites:

```text
experiments/
├── ledger.md                                     # Master index of all iterations, decisions & metric trends
├── iter_000_baseline_<YYYYMMDD_HHMMSS>/
│   ├── hypothesis.md                             # Baseline architecture definition
│   ├── report.md                                 # Quantitative baseline metrics across all 4 datasets
│   ├── failures.md                               # Categorized error triage (Recall vs Precision vs Fusion)
│   ├── predictions/                              # Raw JSONL predictions per dataset
│   └── reports/                                  # Structured JSON metric reports per dataset
└── iter_NNN_<hypothesis_name>_<YYYYMMDD_HHMMSS>/
    ├── hypothesis.md                             # Single isolated variable, rationale, clean-room check
    ├── report.md                                 # Delta comparison table vs baseline, decision (PROMOTE/REVERT)
    ├── failures.md                               # Remaining error triage driving next iteration
    ├── predictions/                              # Prediction outputs for this run
    └── reports/                                  # Structured evaluation JSON reports for this run
```

---

## The Autonomous Optimization Steps

### Step 1: Establish Frozen Baseline (Run 0)
1. Generate current timestamp `TS=$(date +%Y%m%d_%H%M%S)`.
2. Create directory `./experiments/iter_000_baseline_${TS}/`.
3. Run baseline benchmark across all target datasets; save predictions and reports inside `./experiments/iter_000_baseline_${TS}/`.
4. Write `./experiments/iter_000_baseline_${TS}/report.md` and initialize `./experiments/ledger.md`.
- **Completion Criterion**: Baseline metrics recorded across all 4 datasets; ledger initialized.

### Step 2: Error Triage & Failure Traceability
1. Extract all queries where ground truth was missed or ranked below top-$K$ from the active baseline.
2. Classify each failed query into exactly one failure mode:
   - **Recall Miss (Candidate Absence)**: Ground truth passage was never retrieved in the initial candidate pool.
   - **Precision Miss (Ranking Inversion)**: Ground truth was present in candidate pool but outranked by irrelevant chunks.
   - **Fusion Conflict**: Sparse and dense retrievers assigned conflicting ranks.
3. Determine the single largest failure mode across the benchmark suite.
- **Completion Criterion**: 100% of missed queries classified; dominant bottleneck identified.

### Step 3: Formulate Hypothesis & Implement Single Variable Mutation
1. Formulate a testable hypothesis targeting the dominant failure mode.
2. Generate timestamp `TS=$(date +%Y%m%d_%H%M%S)` and create directory `./experiments/iter_NNN_<name>_${TS}/`.
3. Write `./experiments/iter_NNN_<name>_${TS}/hypothesis.md` documenting:
   - Target failure mode
   - Single isolated code variable to mutate
   - Clean-room verification (zero test query memorization, zero `qrels` leakage)
4. Apply the code modification.
5. **Self-Healing Green Gate**: Run `./scripts/check.sh`. If any linter, typecheck, or test error occurs, fix it immediately in the same turn without yielding or prompting until `./scripts/check.sh` passes cleanly (code 0).
- **Completion Criterion**: `hypothesis.md` written; `./scripts/check.sh` passes cleanly (0 errors, 0 warnings, 0 test failures).

### Step 4: Run Controlled Benchmark & Calculate Metric Deltas
1. Execute the benchmark suite saving predictions to `./experiments/iter_NNN_<name>_${TS}/predictions/` and reports to `./experiments/iter_NNN_<name>_${TS}/reports/`.
2. Calculate delta for each metric against the active reference baseline:
   $$\Delta \text{Metric} = \text{Metric}_{\text{new}} - \text{Metric}_{\text{baseline}}$$
3. Write `./experiments/iter_NNN_<name>_${TS}/report.md` with side-by-side metric tables and delta columns.
- **Completion Criterion**: `report.md` written with complete $\Delta \text{MRR@10}$, $\Delta \text{NDCG@10}$, and $\Delta \text{HitRate@5}$ across all datasets.

### Step 5: Delta Gate Decision & Autonomous Promotion/Reversion
1. Evaluate results against the **Delta gate**:
   - **Pass ($\Delta > 0$ without domain regression)**: Mark as **PROMOTE**; retain code changes as the new active baseline.
   - **Fail ($\Delta \le 0$ or significant cross-domain regression)**: Mark as **REVERT**; immediately revert code changes to previous baseline state.
2. Document decision in `report.md` and append entry to `./experiments/ledger.md`.
- **Completion Criterion**: Decision recorded in ledger; codebase state matches decision.

### Step 6: Empirical Ceiling Check & Autonomous Loop Continuation
1. Check for the **Plateau**: Verify if at least 2 consecutive orthogonal optimization techniques yielded $\Delta \text{NDCG@10} \le 0.005$.
2. If ceiling reached: Document formal termination in `./experiments/ledger.md` and conclude.
3. If ceiling NOT reached: **Immediately proceed to Step 2 for the next iteration without pausing or asking questions.**
- **Completion Criterion**: Formal termination if plateau verified; otherwise, next iteration loop launched immediately.

---

## Reference: Anti-Cheating & Data-Leakage Guardrails

The following operations constitute data leakage and are strictly prohibited:

### 1. Ground Truth (`qrels`) Peeking
- Reading or referencing `qrels.jsonl` or `GroundTruth.relevant_doc_ids` anywhere inside indexing, chunking, retrieval, scoring, or fusion logic.
- Inspecting test answers or gold rationale text to alter query phrasing or expand candidate sets.

### 2. Transductive & Query-Dependent Indexing
- Building corpus indexes (sparse inverted index, vocabulary IDF, or dense embeddings) conditionally on the evaluation query distribution.
- Tuning global index parameters using information derived from the query set.

### 3. Hardcoded Rules & Memorization
- Hardcoding conditional logic for specific benchmark query IDs or exact query substrings (e.g., `if "notice" in query: boost("doc_12")`).
- Constructing lookup tables mapping benchmark questions to known document IDs.

### 4. Evaluation Split Fine-Tuning
- Training or fine-tuning local model weights on test query-document pairs from the evaluated benchmarks.
- Only zero-shot pretrained models or domain-agnostic unsupervised ranking functions are permitted.
