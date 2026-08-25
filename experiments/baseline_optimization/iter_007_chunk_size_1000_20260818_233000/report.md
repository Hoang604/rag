# Iteration 007: Paragraph Chunk Window Expansion ($1000/150$) Report

- **Timestamp**: 2026-08-18 23:30:00
- **Directory**: `experiments/baseline_optimization/iter_007_chunk_size_1000_20260818_233000/`
- **Tested Mutation**: Increased chunk window from 512 to 1000 characters (`chunk_size=1000, chunk_overlap=150`).

---

## 1. Quantitative Delta vs Active Baseline (Iteration 003)

| Benchmark Dataset | Metric | Iteration 003 Baseline | Iteration 007 ($1000/150$) | Delta ($\Delta$) | Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **BEIR/FiQA** | NDCG@10 | 0.2766 | **0.3186** | **+0.0420** | **Massive Gain (+15%)** |
| | MRR@10 | 0.3499 | **0.4142** | **+0.0643** | **Massive Gain (+18%)** |
| | HitRate@1 | 0.2400 | **0.3200** | **+0.0800** | **Massive Gain (+33%)** |
| | HitRate@10 | 0.5600 | **0.6400** | **+0.0800** | **Massive Gain (+14%)** |
| | Recall@10 | 0.3304 | **0.3807** | **+0.0503** | **Massive Gain (+15%)** |
| **SciFact** | NDCG@10 | 0.8263 | 0.8131 | -0.0132 | High Plateau (Hit@10=94%) |
| | HitRate@10 | 0.9400 | 0.9400 | 0.0000 | Identical (94%) |
| **QASPER** | NDCG@10 | 0.3473 | 0.3389 | -0.0084 | Trade-off |
| | HitRate@10 | 0.4400 | 0.4400 | 0.0000 | Identical (44%) |
| **CUAD** | NDCG@10 | 0.0404 | 0.0304 | -0.0100 | Regressed |

---

## 2. Decision & Delta Gate Evaluation

- **Delta Gate Outcome**: **TRADE-OFF / REVERT TO ABLATE INTERMEDIATE**.
- **Rationale**: 1000 characters drove historic breakthroughs on FiQA (NDCG 0.3186, Hit@10 64%), but slightly oversized chunks diluted concise single-clause contracts in CUAD.
- **Action**: Test intermediate balanced window size (`chunk_size=750, chunk_overlap=100`) in Iteration 008.
