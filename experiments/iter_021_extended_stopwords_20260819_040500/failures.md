# Iteration 021: Failure Triage & Error Analysis

Analysis of Iteration 021:

---

## 1. Domain Noise Elimination

- Academic documents frequently contain citation markers like `et al.` and section pointers like `page 4` or `section 3.2`.
- Removing these non-discriminative terms eliminates false-positive BM25 postings intersections, yielding higher precision candidate pools for dense neural re-ranking.
