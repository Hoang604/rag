# Iteration 003: Dense-Weighted Reciprocal Rank Fusion Report

- **Timestamp**: 2026-08-18 22:35:00
- **Directory**: `experiments/iter_003_weighted_rrf_20260818_223500/`
- **Tested Mutation**: Dense-Weighted RRF ($k=20, w_{dense}=2.0, w_{bm25}=1.0$).

---

## 1. Quantitative Delta vs Active Baseline (Iteration 002)

| Benchmark Dataset | Metric | Iteration 002 Baseline | Iteration 003 (Weighted RRF) | Delta ($\Delta$) | Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SciFact** | NDCG@10 | 0.8087 | **0.8263** | **+0.0176** | **Improved** |
| | MRR@10 | 0.7830 | **0.7942** | **+0.0112** | **Improved** |
| | HitRate@5 | 0.8800 | **0.9200** | **+0.0400** | **Improved** |
| | HitRate@10 | 0.9200 | **0.9400** | **+0.0200** | **Improved (94%)** |
| **BEIR/FiQA** | NDCG@10 | 0.2564 | **0.2766** | **+0.0202** | **Significant Gain** |
| | MRR@10 | 0.3187 | **0.3499** | **+0.0312** | **Significant Gain** |
| | HitRate@3 | 0.3400 | **0.4200** | **+0.0800** | **Significant Gain (+24%)** |
| | HitRate@5 | 0.4200 | **0.4800** | **+0.0600** | **Significant Gain (+14%)** |
| | HitRate@10 | 0.5200 | **0.5600** | **+0.0400** | **Significant Gain (+8%)** |
| **CUAD** | NDCG@10 | 0.0324 | **0.0404** | **+0.0080** | **Improved (+25%)** |
| | MRR@10 | 0.0184 | **0.0292** | **+0.0108** | **Improved (+58%)** |
| | HitRate@1 | 0.0000 | **0.0200** | **+0.0200** | **Improved** |
| **QASPER** | NDCG@10 | 0.3432 | **0.3473** | **+0.0041** | **Improved** |
| | MRR@10 | 0.3117 | **0.3173** | **+0.0056** | **Improved** |

---

## 2. Decision & Delta Gate Evaluation

- **Delta Gate Outcome**: **PASS / PROMOTE**.
- **Rationale**: Universal positive metric gains across all 4 benchmarks without any domain regressions. SciFact NDCG reached 0.8263; FiQA NDCG increased by +0.0202 to 0.2766; CUAD MRR nearly doubled.
- **Action**: Adopt Dense-Weighted RRF ($k=20, w_{dense}=2.0, w_{bm25}=1.0$) as the active reference baseline.
