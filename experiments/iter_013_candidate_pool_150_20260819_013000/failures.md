# Iteration 013: Failure Triage & Error Analysis

Analysis of Iteration 013:

---

## 1. Candidate Pool Scaling Efficacy

- FiQA retrieval heavily relies on dense neural embeddings capturing vocabulary mismatch questions.
- Expanding candidate pool to 150 chunks admitted crucial semantic answers that had low exact BM25 keyword overlap into Stage 2 dense re-ranking.

---

## 2. Target for Iteration 014

- **Further Candidate Pool Scaling**: Test $N=200$ to check if the recall boundary can be expanded further without introducing ranking noise.
