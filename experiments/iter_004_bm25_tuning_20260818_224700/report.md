# Iteration 004: BM25 Passage Parameter Tuning ($k_1=1.2, b=0.40$) Report

- **Timestamp**: 2026-08-18 22:47:00
- **Directory**: `experiments/iter_004_bm25_tuning_20260818_224700/`
- **Tested Mutation**: Modified BM25 parameters $k_1=1.5 \rightarrow 1.2, b=0.75 \rightarrow 0.40$.

---

## 1. Quantitative Delta vs Active Baseline (Iteration 003)

| Benchmark Dataset | Metric | Iteration 003 Baseline | Iteration 004 ($k_1=1.2, b=0.40$) | Delta ($\Delta$) | Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **BEIR/FiQA** | NDCG@10 | 0.2766 | **0.2883** | **+0.0117** | **Improved** |
| | MRR@10 | 0.3499 | **0.3709** | **+0.0210** | **Improved** |
| | HitRate@10 | 0.5600 | **0.5800** | **+0.0200** | **Improved** |
| **SciFact** | NDCG@10 | 0.8263 | 0.8248 | -0.0015 | Minor drop |
| | HitRate@10 | 0.9400 | 0.9400 | 0.0000 | Neutral (94%) |
| **QASPER** | NDCG@10 | 0.3473 | 0.3363 | -0.0110 | **Regressed** |
| | HitRate@10 | 0.4400 | 0.4200 | -0.0200 | Regressed |
| **CUAD** | NDCG@10 | 0.0404 | 0.0338 | -0.0066 | **Regressed** |
| | HitRate@10 | 0.0800 | 0.0600 | -0.0200 | Regressed |

---

## 2. Decision & Delta Gate Evaluation

- **Delta Gate Outcome**: **FAIL / REVERT**.
- **Rationale**: While lower $b$ improved FiQA, it caused measurable cross-domain regressions on QASPER (-0.0110 NDCG) and CUAD (-0.0066 NDCG) where length normalization is critical to suppress noisy oversized contract/paper segments.
- **Action**: Immediately revert BM25 parameters back to reference baseline ($k_1=1.5, b=0.75$).
