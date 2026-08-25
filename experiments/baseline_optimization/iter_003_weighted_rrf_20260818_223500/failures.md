# Iteration 003: Failure Triage & Error Analysis

Analysis of residual errors after Iteration 003 (Dense-Weighted RRF):

---

## 1. Categorized Remaining Failure Modes

| Benchmark | Total Evaluated | Failed Queries (NDCG < 0.5) | Dominant Failure Mode | Diagnostic Summary |
| :--- | :--- | :--- | :--- | :--- |
| **BEIR/FiQA** | 50 | 25 (down from 27) | Document Length Penalty Distortion | Default BM25 $b=0.75$ heavily penalizes chunks containing detailed multi-sentence explanations, favoring short uninformative chunks. |
| **QASPER** | 50 | 26 (down from 28) | Passage Length Normalization | Academic sections vary in length; high $b$ reduces scores of comprehensive discussion paragraphs. |
| **SciFact** | 50 | 3 (down from 4) | High Precision Plateau | Hit@10 reached 94.0%, approaching theoretical oracle ceiling for abstracts. |
| **CUAD** | 50 | 45 (down from 46) | Structural contract ambiguity | Identical standard provisions across contracts. |

---

## 2. Target for Iteration 004

- **Proposed Intervention**: Optimize BM25 Passage Parameters ($k_1=1.2, b=0.40$) to alleviate length penalties on dense informational chunks.
