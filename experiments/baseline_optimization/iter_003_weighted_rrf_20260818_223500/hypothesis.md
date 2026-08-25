# Iteration 003: Dense-Weighted Reciprocal Rank Fusion ($k=20, w_{dense}=2.0$)

- **Timestamp**: 20260818_223500
- **Directory**: `experiments/baseline_optimization/iter_003_weighted_rrf_20260818_223500/`
- **Target Failure Mode**: Fusion Rank Dilution where noisy sparse matches dilute high-confidence neural semantic rankings.

---

## 1. Context & Rationale

Standard RRF ($k=60$) flattens the contribution of top ranks and assigns equal weight to sparse and dense retrievers ($w_{bm25}=w_{dense}=1.0$). Because BM25 operates purely lexically, spurious term overlaps often outrank semantically superior dense passages. Shifting RRF smoothing to $k=20$ and weighting dense ranks ($w_{dense}=2.0$) amplifies top-tier neural matches while retaining lexical support.

## 2. Single Variable Mutation (Ablation)

- **Variable Modified**: Fusion Formula:
  $$\text{Score}(d) = \frac{1.0}{20 + \text{rank}_{bm25}} + \frac{2.0}{20 + \text{rank}_{dense}}$$
- **Control Variables**: Porter Stemmed BM25, candidate pool $N=100$, chunking $512/64$, dense model `BAAI/bge-small-en-v1.5` FP16.

## 3. Clean-Room IR Verification

- Zero `qrels` leakage. Pure algorithmic rank weighting applied globally across all datasets.
