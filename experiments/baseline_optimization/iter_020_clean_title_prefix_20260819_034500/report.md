# Iteration 020: Clean Document Header Context Injection Report

- **Timestamp**: 2026-08-19 03:45:00
- **Directory**: `experiments/baseline_optimization/iter_020_clean_title_prefix_20260819_034500/`
- **Tested Mutation**: Injected direct title context `{title}\n\n` without the static boilerplate `"Title: "` prompt token (`chunk_text()`).

---

## 1. Quantitative Delta vs Active Baseline (Iteration 013)

| Benchmark Dataset | Metric | Iteration 013 Baseline | Iteration 020 (Clean Title) | Delta ($\Delta$) | Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SciFact** | NDCG@10 | 0.8172 | **0.8238** | **+0.0066** | **Improved** |
| | MRR@10 | 0.7865 | **0.7942** | **+0.0077** | **Improved** |
| | HitRate@1 | 0.7000 | **0.7200** | **+0.0200** | **Improved** |
| | Recall@1 | 0.6867 | **0.7067** | **+0.0200** | **Improved** |
| **QASPER** | NDCG@10 | 0.3354 | **0.3417** | **+0.0063** | **Improved** |
| | MRR@10 | 0.3024 | **0.3107** | **+0.0083** | **Improved** |
| | HitRate@1 | 0.2400 | **0.2600** | **+0.0200** | **Improved** |
| | Recall@1 | 0.2400 | **0.2600** | **+0.0200** | **Improved** |
| **CUAD** | HitRate@10 | 0.0600 | **0.0800** | **+0.0200** | **All-Time High (+33%)** |
| | Recall@10 | 0.0600 | **0.0800** | **+0.0200** | **All-Time High (+33%)** |
| | NDCG@10 | 0.0460 | 0.0444 | -0.0016 | Competitive |
| **BEIR/FiQA** | NDCG@10 | 0.2997 | 0.2997 | 0.0000 | Identical (64% Hit@10) |
| | MRR@10 | 0.3624 | 0.3624 | 0.0000 | Identical |

---

## 2. Decision & Delta Gate Evaluation

- **Delta Gate Outcome**: **PROMOTE TO ACTIVE BASELINE**.
- **Rationale**: Eliminating the artificial `"Title: "` prompt token removed structural embedding distortion in `BAAI/bge-small-en-v1.5`, delivering consistent improvements across SciFact (+0.0066 NDCG, +0.0077 MRR, 72% Hit@1), QASPER (+0.0063 NDCG, 26% Hit@1), and an all-time record on CUAD deep recall (Hit@10 reaching 8.0%, a +33% increase).
- **Action**: Adopt clean title context injection as the new active reference baseline.
