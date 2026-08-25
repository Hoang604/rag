# Iteration 017: Dense Rank Weight Scaling ($w_{dense}=3.0$) Report

- **Timestamp**: 2026-08-19 02:45:00
- **Directory**: `experiments/baseline_optimization/iter_017_dense_weight_3_20260819_024500/`
- **Tested Mutation**: Increased dense weight to $w_{dense}=3.0$ in Dense-Weighted RRF (`dense_weight=3.0, bm25_weight=1.0`).

---

## 1. Quantitative Delta vs Active Baseline (Iteration 013)

| Benchmark Dataset | Metric | Iteration 013 Baseline ($w_{dense}=2.0$) | Iteration 017 ($w_{dense}=3.0$) | Delta ($\Delta$) | Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **BEIR/FiQA** | NDCG@10 | 0.2997 | **0.3031** | **+0.0034** | **All-Time High (+1%)** |
| | Recall@10 | 0.3927 | **0.3994** | **+0.0067** | **All-Time High** |
| | HitRate@5 | 0.5400 | **0.5600** | **+0.0200** | **Improved** |
| **CUAD** | NDCG@10 | 0.0460 | **0.0460** | **0.0000** | Retained (All-time high) |
| | MRR@10 | 0.0422 | **0.0422** | **0.0000** | Retained (All-time high) |
| | HitRate@1 | 0.0400 | **0.0400** | **0.0000** | Retained (All-time high) |
| **SciFact** | NDCG@10 | 0.8172 | 0.8136 | -0.0036 | Stable (Hit@10=94%) |
| **QASPER** | NDCG@10 | 0.3354 | 0.3251 | -0.0103 | Regressed |

---

## 2. Decision & Delta Gate Evaluation

- **Delta Gate Outcome**: **FAIL / REVERT**.
- **Rationale**: While $w_{dense}=3.0$ reached an all-time peak on BEIR/FiQA (0.3031 NDCG), it caused a -0.0103 regression on QASPER where exact lexical term matches in scientific papers require equal rank balance.
- **Action**: Immediately revert `dense_weight` back to 2.0.
