# Iteration 014: Candidate Pool Expansion ($N=150 \rightarrow 200$) Report

- **Timestamp**: 2026-08-19 01:45:00
- **Directory**: `experiments/baseline_optimization/iter_014_candidate_pool_200_20260819_014500/`
- **Tested Mutation**: Increased BM25 candidate pool size from 150 to 200 passages (`candidate_pool_size=200`).

---

## 1. Quantitative Delta vs Active Baseline (Iteration 013)

| Benchmark Dataset | Metric | Iteration 013 Baseline ($N=150$) | Iteration 014 ($N=200$) | Delta ($\Delta$) | Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **BEIR/FiQA** | NDCG@10 | 0.2997 | 0.2914 | -0.0083 | Regressed |
| | HitRate@10 | 0.6400 | 0.6200 | -0.0200 | Regressed |
| | Recall@10 | 0.3927 | 0.3877 | -0.0050 | Regressed |
| | MRR@10 | 0.3624 | 0.3524 | -0.0100 | Regressed |
| **CUAD** | NDCG@10 | 0.0460 | 0.0386 | -0.0074 | Regressed |
| | MRR@10 | 0.0422 | 0.0322 | -0.0100 | Regressed |
| | HitRate@1 | 0.0400 | 0.0200 | -0.0200 | Regressed |
| **QASPER** | NDCG@10 | 0.3354 | 0.3347 | -0.0007 | Flat |
| **SciFact** | NDCG@10 | 0.8172 | 0.8172 | 0.0000 | Identical |

---

## 2. Decision & Delta Gate Evaluation

- **Delta Gate Outcome**: **FAIL / REVERT**.
- **Rationale**: Expanding candidate pool beyond 150 introduced noise passages from deep in the BM25 tail that caused dense false-positive matches in CUAD and FiQA. $N=150$ is established as the optimal candidate pool size.
- **Action**: Immediately revert candidate pool size back to 150.
