# Iteration 011: Local Neural Embedding Capacity Scaling (`bge-base-en-v1.5`) Report

- **Timestamp**: 2026-08-19 00:45:00
- **Directory**: `experiments/baseline_optimization/iter_011_bge_base_20260819_004500/`
- **Tested Mutation**: Upgraded bi-encoder neural architecture from `BAAI/bge-small-en-v1.5` (33M params, 384-d) to `BAAI/bge-base-en-v1.5` (110M params, 768-d).

---

## 1. Quantitative Delta vs Active Baseline (Iteration 003)

| Benchmark Dataset | Metric | Iteration 003 Baseline (`bge-small`) | Iteration 011 (`bge-base`) | Delta ($\Delta$) | Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SciFact** | NDCG@10 | 0.8263 | **0.8296** | **+0.0033** | **Improved** |
| | MRR@10 | 0.7942 | **0.8183** | **+0.0241** | **Improved** |
| | HitRate@1 | 0.7000 | **0.7400** | **+0.0400** | **Improved** |
| **BEIR/FiQA** | NDCG@10 | 0.2766 | 0.2616 | -0.0150 | Regressed |
| | MRR@10 | 0.3499 | 0.3318 | -0.0181 | Regressed |
| **QASPER** | NDCG@10 | 0.3473 | 0.3298 | -0.0175 | Regressed |
| **CUAD** | NDCG@10 | 0.0404 | 0.0144 | -0.0260 | Regressed |

---

## 2. Decision & Delta Gate Evaluation

- **Delta Gate Outcome**: **FAIL / REVERT**.
- **Rationale**: While `bge-base` improved SciFact MRR to 0.8183, it tripled latency (8.36s/query vs 2.50s/query) and caused regressions across FiQA, QASPER, and CUAD.
- **Action**: Immediately revert default model back to `BAAI/bge-small-en-v1.5`.
