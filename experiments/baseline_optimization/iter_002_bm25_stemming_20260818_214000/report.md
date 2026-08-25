# Iteration 002: BM25 Morphological Stemming Report

- **Timestamp**: 2026-08-18 21:40:00
- **Directory**: `experiments/baseline_optimization/iter_002_bm25_stemming_20260818_214000/`
- **Tested Mutation**: Integrated English Porter Stemmer into BM25 tokenization.

---

## 1. Quantitative Delta vs Active Baseline (Iteration 001)

| Benchmark Dataset | Metric | Iteration 001 Baseline | Iteration 002 (+Porter Stem) | Delta ($\Delta$) | Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SciFact** | NDCG@10 | 0.7674 | **0.8087** | **+0.0413** | **Significant Gain** |
| | MRR@10 | 0.7407 | **0.7830** | **+0.0423** | **Significant Gain** |
| | HitRate@1 | 0.6400 | **0.7000** | **+0.0600** | **Significant Gain** |
| | HitRate@10 | 0.8800 | **0.9200** | **+0.0400** | **Significant Gain** |
| **BEIR/FiQA** | NDCG@10 | 0.2048 | **0.2564** | **+0.0516** | **Massive Gain (+25%)** |
| | MRR@10 | 0.2462 | **0.3187** | **+0.0725** | **Massive Gain (+29%)** |
| | HitRate@5 | 0.3000 | **0.4200** | **+0.1200** | **Massive Gain (+40%)** |
| | HitRate@10 | 0.4000 | **0.5200** | **+0.1200** | **Massive Gain (+30%)** |
| | Recall@10 | 0.2510 | **0.3364** | **+0.0854** | **Massive Gain (+34%)** |
| **CUAD** | NDCG@10 | 0.0227 | **0.0324** | **+0.0097** | **Improved (+43%)** |
| | MRR@10 | 0.0117 | **0.0184** | **+0.0067** | **Improved (+57%)** |
| | HitRate@5 | 0.0200 | **0.0400** | **+0.0200** | **Improved** |
| **QASPER** | NDCG@10 | 0.3516 | 0.3432 | -0.0084 | Minor trade-off |
| | HitRate@3 | 0.3600 | **0.4000** | **+0.0400** | **Improved** |
| | HitRate@10 | 0.4400 | 0.4400 | 0.0000 | Neutral |

---

## 2. Decision & Delta Gate Evaluation

- **Delta Gate Outcome**: **PASS / PROMOTE**.
- **Rationale**: Dramatic improvements across SciFact ($\Delta \text{NDCG}=+0.0413$, Hit@10=92%), BEIR/FiQA ($\Delta \text{NDCG}=+0.0516$, Hit@5 +12%), and CUAD ($\Delta \text{NDCG}=+0.0097$).
- **Action**: Adopt Porter Stemming as active reference baseline.
