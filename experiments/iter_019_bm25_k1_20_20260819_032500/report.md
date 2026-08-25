# Iteration 019: Higher BM25 Term Frequency Saturation ($k_1=2.0$) Report

- **Timestamp**: 2026-08-19 03:25:00
- **Directory**: `experiments/iter_019_bm25_k1_20_20260819_032500/`
- **Tested Mutation**: Increased BM25 term frequency saturation parameter from $k_1=1.5$ to $k_1=2.0$ (`k1=2.0`).

---

## 1. Quantitative Delta vs Active Baseline (Iteration 013)

| Benchmark Dataset | Metric | Iteration 013 Baseline ($k_1=1.5$) | Iteration 019 ($k_1=2.0$) | Delta ($\Delta$) | Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SciFact** | NDCG@10 | 0.8172 | 0.8144 | -0.0028 | Stable |
| **QASPER** | NDCG@10 | 0.3354 | 0.3348 | -0.0006 | Stable |
| **CUAD** | NDCG@10 | 0.0460 | 0.0386 | -0.0074 | Regressed |
| | HitRate@1 | 0.0400 | 0.0200 | -0.0200 | Regressed |
| **BEIR/FiQA** | NDCG@10 | 0.2997 | 0.2882 | -0.0115 | Regressed |
| | HitRate@10 | 0.6400 | 0.6200 | -0.0200 | Regressed |

---

## 2. Decision & Delta Gate Evaluation

- **Delta Gate Outcome**: **FAIL / REVERT**.
- **Rationale**: Setting $k_1=2.0$ excessively rewarded passages with high term repetition at the expense of query term coverage, dropping CUAD NDCG from 0.0460 to 0.0386 and FiQA NDCG from 0.2997 to 0.2882. $k_1=1.5$ is preserved as the optimal term saturation parameter.
- **Action**: Immediately revert $k_1$ back to 1.5.
