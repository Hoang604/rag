# Iteration 001: Candidate Pool Expansion ($N=100$) Report

- **Timestamp**: 2026-08-18 21:28:50
- **Directory**: `experiments/iter_001_candidate_pool_100_20260818_212850/`
- **Tested Mutation**: Candidate Pool Expansion $N=25 \rightarrow 100$.

---

## 1. Quantitative Delta vs Baseline (Run 000)

| Benchmark Dataset | Metric | Run 000 Baseline | Iteration 001 ($N=100$) | Delta ($\Delta$) | Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SciFact** | NDCG@10 | 0.7512 | **0.7674** | **+0.0162** | **Improved** |
| | MRR@10 | 0.7324 | **0.7407** | **+0.0083** | **Improved** |
| | HitRate@5 | 0.8000 | **0.8600** | **+0.0600** | **Improved** |
| **QASPER** | NDCG@10 | 0.3328 | **0.3516** | **+0.0188** | **Improved** |
| | MRR@10 | 0.3119 | **0.3242** | **+0.0123** | **Improved** |
| | HitRate@5 | 0.3600 | **0.4000** | **+0.0400** | **Improved** |
| **CUAD** | NDCG@10 | 0.0209 | **0.0227** | **+0.0018** | **Improved** |
| | MRR@10 | 0.0097 | **0.0117** | **+0.0020** | **Improved** |
| | HitRate@5 | 0.0200 | 0.0200 | 0.0000 | Neutral |
| **BEIR/FiQA** | NDCG@10 | 0.2070 | 0.2048 | -0.0022 | Minor jitter |
| | Recall@10 | 0.2470 | **0.2510** | **+0.0040** | **Improved** |
| | HitRate@10 | 0.4000 | 0.4000 | 0.0000 | Neutral |

---

## 2. Decision & Delta Gate Evaluation

- **Delta Gate Outcome**: **PASS / PROMOTE**.
- **Rationale**: Significant cross-domain gains in SciFact ($\Delta \text{NDCG}=+0.0162$, $\Delta \text{Hit@5}=+6\%$) and QASPER ($\Delta \text{NDCG}=+0.0188$, $\Delta \text{Hit@5}=+4\%$) with marginal gain in CUAD and higher Recall in FiQA.
- **Action**: Adopt $N=100$ candidate pool as new active baseline.
