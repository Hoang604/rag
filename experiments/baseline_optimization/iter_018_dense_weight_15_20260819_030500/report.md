# Iteration 018: Balanced Dense-BM25 Rank Ratio ($w_{dense}=1.5, w_{bm25}=1.0$) Report

- **Timestamp**: 2026-08-19 03:05:00
- **Directory**: `experiments/baseline_optimization/iter_018_dense_weight_15_20260819_030500/`
- **Tested Mutation**: Decreased dense weight to $w_{dense}=1.5$ in Dense-Weighted RRF (`dense_weight=1.5, bm25_weight=1.0`).

---

## 1. Quantitative Delta vs Active Baseline (Iteration 013)

| Benchmark Dataset | Metric | Iteration 013 Baseline ($w=2.0$) | Iteration 018 ($w=1.5$) | Delta ($\Delta$) | Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **QASPER** | NDCG@10 | 0.3354 | **0.3418** | **+0.0064** | **Improved** |
| | HitRate@3 | 0.3600 | **0.3800** | **+0.0200** | **Improved** |
| | Recall@3 | 0.3600 | **0.3800** | **+0.0200** | **Improved** |
| | MRR@10 | 0.3024 | **0.3101** | **+0.0077** | **Improved** |
| **SciFact** | NDCG@10 | 0.8172 | 0.8172 | 0.0000 | Identical (Hit@10=94%) |
| **CUAD** | NDCG@10 | 0.0460 | 0.0460 | 0.0000 | Identical (Record preserved) |
| **BEIR/FiQA** | NDCG@10 | 0.2997 | 0.2851 | -0.0146 | Regressed |
| | HitRate@10 | 0.6400 | 0.6000 | -0.0400 | Regressed |

---

## 2. Decision & Delta Gate Evaluation

- **Delta Gate Outcome**: **FAIL / REVERT**.
- **Rationale**: Lowering dense weight reduced FiQA NDCG by -0.0146 and Hit@10 by 4.0%. $w_{dense}=2.0, w_{bm25}=1.0$ provides the superior balance across all 4 benchmark domains.
- **Action**: Immediately revert `dense_weight` back to 2.0.
