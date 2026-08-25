# Iteration 015: Failure Triage & Error Analysis

Analysis of Iteration 015:

---

## 1. RRF Decay Trade-off

- $k=10$ provides steeper decay, prioritizing rank-1 items but penalizing candidates that appear at rank 4-10 in one modality.
- For datasets requiring complementary multi-passage evidence (QASPER), $k=20$ yields better cross-modal consensus.

---

## 2. Target for Iteration 016

- **Moderate Length Normalization**: Tune BM25 document length normalization parameter $b = 0.75 \rightarrow 0.60$ under stopword filtering.
