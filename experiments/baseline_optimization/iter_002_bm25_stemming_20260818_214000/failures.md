# Iteration 002: Failure Triage & Error Analysis

Analysis of errors following Iteration 002 (BM25 Morphological Stemming):

---

## 1. Categorized Remaining Failure Modes

| Benchmark | Total Evaluated | Failed Queries (NDCG < 0.5) | Dominant Failure Mode | Diagnostic Summary |
| :--- | :--- | :--- | :--- | :--- |
| **BEIR/FiQA** | 50 | 27 (down from 33) | Fusion Rank Weighting | Dense neural model has high cosine similarity on semantic answers, but BM25 rank dilution pulls true documents down due to equal RRF weighting ($k=60$). |
| **QASPER** | 50 | 28 | Long-context section dispersion | Complex multi-paragraph sections require sharper top-rank weighting. |
| **SciFact** | 50 | 4 (down from 7) | Fine-grained ranking precision | Only 4 queries missed top-10; near empirical ceiling for abstracts. |
| **CUAD** | 50 | 46 | Cross-contract boilerplate collisions | Clause queries match standard provisions across hundreds of contracts equally. |

---

## 2. Target for Iteration 003

- **Dominant Bottleneck**: Equal RRF rank fusion treats noisy sparse matches on par with high-confidence neural embeddings.
- **Proposed Intervention**: Implement Dense-Weighted Reciprocal Rank Fusion ($k=20, w_{dense}=2.0, w_{bm25}=1.0$) to amplify confident neural semantic matches while preserving lexical grounding.
