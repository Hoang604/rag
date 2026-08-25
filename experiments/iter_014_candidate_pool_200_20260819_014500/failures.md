# Iteration 014: Failure Triage & Error Analysis

Analysis of Iteration 014:

---

## 1. Candidate Depth Diminishing Returns

- Expanding the candidate pool beyond $N=150$ admits weak lexical candidates (ranks 151-200) that occasionally exhibit accidental high bi-encoder similarity, polluting the top-10 RRF reranking.
- $N=150$ provides the ideal precision-recall balance.

---

## 2. Target for Iteration 015

- **Sharpened RRF Smoothing**: Test $k=10$ (down from $k=20$) in Dense-Weighted RRF to boost high-confidence top-ranked passages and penalize tail candidates.
