# Iteration 013: Candidate Pool Expansion ($N=100 \rightarrow 150$) Report

- **Timestamp**: 2026-08-19 01:30:00
- **Directory**: `experiments/iter_013_candidate_pool_150_20260819_013000/`
- **Tested Mutation**: Expanded BM25 candidate pool size from 100 to 150 passages for Stage 2 dense re-scoring (`candidate_pool_size=150`).

---

## 1. Quantitative Delta vs Active Baseline (Iteration 012)

| Benchmark Dataset | Metric | Iteration 012 Baseline ($N=100$) | Iteration 013 ($N=150$) | Delta ($\Delta$) | Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **BEIR/FiQA** | NDCG@10 | 0.2784 | **0.2997** | **+0.0213** | **Major Breakthrough (+8%)** |
| | HitRate@10 | 0.5800 | **0.6400** | **+0.0600** | **Major Breakthrough (+10%)** |
| | Recall@10 | 0.3557 | **0.3927** | **+0.0370** | **Major Breakthrough (+10%)** |
| | MRR@10 | 0.3457 | **0.3624** | **+0.0167** | **Major Breakthrough** |
| **CUAD** | NDCG@10 | 0.0460 | **0.0460** | **0.0000** | Retained (All-time high) |
| | MRR@10 | 0.0422 | **0.0422** | **0.0000** | Retained (All-time high) |
| | HitRate@1 | 0.0400 | **0.0400** | **0.0000** | Retained (All-time high) |
| **SciFact** | NDCG@10 | 0.8178 | 0.8172 | -0.0006 | Stable (Hit@10=94%) |
| **QASPER** | NDCG@10 | 0.3400 | 0.3354 | -0.0046 | Stable (Hit@10=44%) |

---

## 2. Decision & Delta Gate Evaluation

- **Delta Gate Outcome**: **PROMOTE TO ACTIVE BASELINE**.
- **Rationale**: Expanding candidate pool from 100 to 150 passages significantly unlocked higher recall (+0.0370) and NDCG (+0.0213) on BEIR/FiQA while preserving CUAD record performance (0.0460) and SciFact hit rate (94%).
- **Action**: Adopt $N=150$ as the new active reference baseline.
