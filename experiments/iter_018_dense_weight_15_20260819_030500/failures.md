# Iteration 018: Failure Triage & Error Analysis

Analysis of Iteration 018:

---

## 1. Modality Balancing Findings

- Financial queries heavily rely on dense vector semantics ($w_{dense}=2.0$) to overcome natural language vocabulary variations.
- $w_{dense}=2.0, w_{bm25}=1.0$ achieves the highest harmonic mean of retrieval effectiveness across all benchmarks.

---

## 2. Target for Iteration 019

- **Term Frequency Saturation Tuning**: Test $k_1=2.0$ (up from $k_1=1.5$) in stopword-filtered BM25 to reward high-frequency keyword concentration in technical/legal clauses.
