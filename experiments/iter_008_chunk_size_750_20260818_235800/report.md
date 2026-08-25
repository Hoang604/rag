# Iteration 008: Balanced Paragraph Chunk Window ($750/100$) Report

- **Timestamp**: 2026-08-18 23:58:00
- **Directory**: `experiments/iter_008_chunk_size_750_20260818_235800/`
- **Tested Mutation**: Set chunk window to 750 characters with 100 character overlap (`chunk_size=750, chunk_overlap=100`).

---

## 1. Quantitative Delta vs Active Baseline (Iteration 003)

| Benchmark Dataset | Metric | Iteration 003 Baseline | Iteration 008 ($750/100$) | Delta ($\Delta$) | Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SciFact** | NDCG@10 | 0.8263 | **0.8324** | **+0.0061** | **All-Time High** |
| | MRR@10 | 0.7942 | **0.8090** | **+0.0148** | **All-Time High** |
| | HitRate@1 | 0.7000 | **0.7200** | **+0.0200** | **All-Time High** |
| | HitRate@5 | 0.9200 | **0.9400** | **+0.0200** | **All-Time High** |
| **BEIR/FiQA** | NDCG@10 | 0.2766 | **0.2860** | **+0.0094** | **Improved** |
| | MRR@10 | 0.3499 | **0.3655** | **+0.0156** | **Improved** |
| | HitRate@5 | 0.4800 | **0.5400** | **+0.0600** | **Improved** |
| | HitRate@10 | 0.5600 | **0.6000** | **+0.0400** | **Improved** |
| | Recall@10 | 0.3304 | **0.3627** | **+0.0323** | **Improved** |
| **QASPER** | NDCG@10 | 0.3473 | **0.3498** | **+0.0025** | **Improved** |
| | HitRate@10 | 0.4400 | **0.4600** | **+0.0200** | **Improved** |
| **CUAD** | NDCG@10 | 0.0404 | 0.0171 | -0.0233 | **Regressed** |

---

## 2. Decision & Delta Gate Evaluation

- **Delta Gate Outcome**: **REVERT TO AVOID CUAD REGRESSION**.
- **Rationale**: 750 chars yielded all-time peaks on SciFact (0.8324), FiQA (0.2860), and QASPER (0.3498), but degraded CUAD contract clause resolution (0.0171). To maintain strict cross-domain robustness, we revert chunking to 512/64 as reference baseline and target score-level fusion next.
- **Action**: Revert `chunk_size` to 512 and `chunk_overlap` to 64.
