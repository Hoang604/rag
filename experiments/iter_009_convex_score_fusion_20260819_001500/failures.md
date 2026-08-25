# Iteration 009: Failure Triage & Error Analysis

Analysis of Iteration 009:

---

## 1. Linear Score Normalization Fragility

- Min-Max scaling is brittle in candidate pools where a single document has extreme term frequency (e.g. repeated contract terms or query keyword repetition).
- Outlier scores compress the remainder of the candidate pool into $[0, 0.1]$, effectively disabling sparse lexical discernment.
- Rank RRF handles non-linear distributions robustly.

---

## 2. Target for Iteration 010

- **N-Gram Lexical Precision**: Extend BM25 tokenization with contiguous word bigrams (`w1_w2`) alongside Porter-stemmed unigrams to provide dedicated IDF weights for exact technical, financial, and legal compound phrases.
