# Iteration 015: Sharpened Reciprocal Rank Fusion Smoothing ($k=10$) Report

- **Timestamp**: 2026-08-19 02:10:00
- **Directory**: `experiments/iter_015_rrf_k10_20260819_021000/`
- **Tested Mutation**: Decreased RRF rank smoothing constant from 20 to 10 (`rrf_k=10`).

---

## 1. Quantitative Delta vs Active Baseline (Iteration 013)

| Benchmark Dataset | Metric | Iteration 013 Baseline ($k=20$) | Iteration 015 ($k=10$) | Delta ($\Delta$) | Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **BEIR/FiQA** | NDCG@10 | 0.2997 | **0.3002** | **+0.0005** | **Improved** |
| | Recall@10 | 0.3927 | **0.3994** | **+0.0067** | **Improved** |
| | HitRate@5 | 0.5400 | **0.5600** | **+0.0200** | **Improved** |
| **CUAD** | NDCG@10 | 0.0460 | **0.0460** | **0.0000** | Retained (All-time high) |
| | MRR@10 | 0.0422 | **0.0422** | **0.0000** | Retained (All-time high) |
| | HitRate@1 | 0.0400 | **0.0400** | **0.0000** | Retained (All-time high) |
| **SciFact** | NDCG@10 | 0.8172 | 0.8169 | -0.0003 | Flat (Hit@10=94%) |
| **QASPER** | NDCG@10 | 0.3354 | 0.3277 | -0.0077 | Regressed |

---

## 2. Decision & Delta Gate Evaluation

- **Delta Gate Outcome**: **FAIL / REVERT**.
- **Rationale**: While $k=10$ slightly boosted FiQA Recall@10 (+0.0067), it regressed QASPER (-0.0077 NDCG) due to over-penalizing complementary second-stage evidence chunks. $k=20$ remains the optimal universal smoothing constant.
- **Action**: Immediately revert `rrf_k` back to 20.
