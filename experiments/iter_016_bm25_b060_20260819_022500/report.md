# Iteration 016: Moderate BM25 Length Normalization ($b=0.60$) Report

- **Timestamp**: 2026-08-19 02:25:00
- **Directory**: `experiments/iter_016_bm25_b060_20260819_022500/`
- **Tested Mutation**: Softened document length penalty from $b=0.75$ to $b=0.60$ in BM25 with stopwords removed (`b=0.60`).

---

## 1. Quantitative Delta vs Active Baseline (Iteration 013)

| Benchmark Dataset | Metric | Iteration 013 Baseline ($b=0.75$) | Iteration 016 ($b=0.60$) | Delta ($\Delta$) | Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SciFact** | NDCG@10 | 0.8172 | **0.8214** | **+0.0042** | **Improved** |
| | Recall@1 | 0.6867 | **0.7000** | **+0.0133** | **Improved** |
| **QASPER** | NDCG@10 | 0.3354 | 0.3354 | 0.0000 | Identical |
| **CUAD** | NDCG@10 | 0.0460 | 0.0460 | 0.0000 | Identical (Record preserved) |
| **BEIR/FiQA** | NDCG@10 | 0.2997 | 0.2907 | -0.0090 | Regressed |
| | HitRate@10 | 0.6400 | 0.5800 | -0.0600 | Regressed |

---

## 2. Decision & Delta Gate Evaluation

- **Delta Gate Outcome**: **FAIL / REVERT**.
- **Rationale**: Softening length normalization caused verbose conversational documents in BEIR/FiQA to outrank concise relevant answers, decreasing FiQA Hit@10 from 64% to 58%. Standard $b=0.75$ length penalty is essential for cross-domain stability.
- **Action**: Immediately revert $b$ back to 0.75.
