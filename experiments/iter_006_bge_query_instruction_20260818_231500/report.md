# Iteration 006: Canonical BGE Query Instruction Prefix Report

- **Timestamp**: 2026-08-18 23:15:00
- **Directory**: `experiments/iter_006_bge_query_instruction_20260818_231500/`
- **Tested Mutation**: Prepending canonical BGE instruction prefix (`"Represent this sentence for searching relevant passages: "`) to query embeddings.

---

## 1. Quantitative Delta vs Active Baseline (Iteration 003)

| Benchmark Dataset | Metric | Iteration 003 Baseline | Iteration 006 (Query Prefix) | Delta ($\Delta$) | Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **QASPER** | NDCG@10 | 0.3473 | **0.3579** | **+0.0106** | **Improved** |
| | MRR@10 | 0.3173 | **0.3321** | **+0.0148** | **Improved** |
| **SciFact** | NDCG@10 | 0.8263 | 0.8106 | -0.0157 | Regressed |
| | MRR@10 | 0.7942 | 0.7834 | -0.0108 | Regressed |
| **BEIR/FiQA** | NDCG@10 | 0.2766 | 0.2689 | -0.0077 | Regressed |
| | MRR@10 | 0.3499 | 0.3224 | -0.0275 | Regressed |
| **CUAD** | NDCG@10 | 0.0404 | 0.0246 | -0.0158 | Regressed |

---

## 2. Decision & Delta Gate Evaluation

- **Delta Gate Outcome**: **FAIL / REVERT**.
- **Rationale**: BGE-v1.5 models do not require fixed query prompts for symmetric/asymmetric retrieval; the static prompt diluted exact entity and terminology representations on SciFact, FiQA, and CUAD.
- **Action**: Immediately revert `dense.py` back to direct query embedding without instruction prefix.
