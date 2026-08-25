# Iteration 009: Min-Max Normalized Convex Score Fusion Report

- **Timestamp**: 2026-08-19 00:15:00
- **Directory**: `experiments/iter_009_convex_score_fusion_20260819_001500/`
- **Tested Mutation**: Replaced rank RRF with Min-Max Normalized Convex Score Combination ($\beta=0.70 \cdot \text{Dense}_{\text{norm}} + 0.30 \cdot \text{BM25}_{\text{norm}}$).

---

## 1. Quantitative Delta vs Active Baseline (Iteration 003)

| Benchmark Dataset | Metric | Iteration 003 Baseline | Iteration 009 (Convex Fusion) | Delta ($\Delta$) | Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **QASPER** | NDCG@10 | 0.3473 | **0.3519** | **+0.0046** | **Improved** |
| | HitRate@1 | 0.2400 | **0.2800** | **+0.0400** | **Improved** |
| | MRR@10 | 0.3173 | **0.3245** | **+0.0072** | **Improved** |
| **SciFact** | NDCG@10 | 0.8263 | 0.8101 | -0.0162 | Regressed |
| | MRR@10 | 0.7942 | 0.7764 | -0.0178 | Regressed |
| **BEIR/FiQA** | NDCG@10 | 0.2766 | 0.2596 | -0.0170 | Regressed |
| | MRR@10 | 0.3499 | 0.3254 | -0.0245 | Regressed |
| **CUAD** | NDCG@10 | 0.0404 | 0.0315 | -0.0089 | Regressed |

---

## 2. Decision & Delta Gate Evaluation

- **Delta Gate Outcome**: **FAIL / REVERT**.
- **Rationale**: Linear score normalization is sensitive to outlier candidate scores from BM25 and dense encoders, degrading rankings on SciFact and FiQA. Rank-based Reciprocal Rank Fusion ($k=20, w_{dense}=2.0$) provides strictly superior rank stability.
- **Action**: Immediately revert `pipeline.py` back to Dense-Weighted RRF.
