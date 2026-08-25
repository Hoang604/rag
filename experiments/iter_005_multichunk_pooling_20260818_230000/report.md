# Iteration 005: Multi-Chunk Evidence Accumulation Report

- **Timestamp**: 2026-08-18 23:00:00
- **Directory**: `experiments/iter_005_multichunk_pooling_20260818_230000/`
- **Tested Mutation**: Document Score Pooling: Strict Max-Pooling $\rightarrow$ Decayed Multi-Chunk Accumulation ($\alpha=0.25$).

---

## 1. Quantitative Delta vs Active Baseline (Iteration 003)

| Benchmark Dataset | Metric | Iteration 003 Baseline | Iteration 005 (Multi-Chunk) | Delta ($\Delta$) | Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **BEIR/FiQA** | NDCG@10 | 0.2766 | **0.2874** | **+0.0108** | **Improved** |
| | Recall@10 | 0.3304 | **0.3404** | **+0.0100** | **Improved** |
| | HitRate@10 | 0.5600 | **0.5800** | **+0.0200** | **Improved** |
| **SciFact** | NDCG@10 | 0.8263 | 0.7647 | -0.0616 | **Severe Regression** |
| | MRR@10 | 0.7942 | 0.7242 | -0.0700 | **Severe Regression** |
| | HitRate@1 | 0.7000 | 0.6000 | -0.1000 | **Severe Regression** |
| **QASPER** | NDCG@10 | 0.3473 | 0.3282 | -0.0191 | **Regression** |
| **CUAD** | NDCG@10 | 0.0404 | 0.0340 | -0.0064 | **Regression** |

---

## 2. Decision & Delta Gate Evaluation

- **Delta Gate Outcome**: **FAIL / REVERT**.
- **Rationale**: While multi-chunk sum accumulation boosted FiQA (+0.0108 NDCG), it caused a catastrophic drop on SciFact (-0.0616 NDCG) and QASPER (-0.0191 NDCG). Summing candidate chunks allows noisy background documents with multiple weak matches to overtake documents containing the single precise gold paragraph.
- **Action**: Immediately revert `pipeline.py` back to strict Max-Pooling.
