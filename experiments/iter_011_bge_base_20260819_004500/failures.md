# Iteration 011: Failure Triage & Error Analysis

Analysis of Iteration 011:

---

## 1. Bi-Encoder Scaling Trade-offs

- `bge-base` triples compute requirements per query while yielding mixed generalization without dataset-specific dense index fine-tuning.
- `bge-small-en-v1.5` offers superior out-of-the-box cross-domain balance and 3.5x lower inference latency.

---

## 2. Target for Iteration 012

- **Lexical Stopword Filtering**: Remove high-frequency functional English stopwords from BM25 index and queries to prevent boilerplate query tokens from inflating document lengths and skewing BM25 scores on CUAD and FiQA.
