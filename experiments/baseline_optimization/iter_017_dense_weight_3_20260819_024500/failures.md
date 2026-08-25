# Iteration 017: Failure Triage & Error Analysis

Analysis of Iteration 017:

---

## 1. Modality Balancing in Academic Papers

- Scientific Q&A (QASPER) contains specialized technical jargon (e.g. dataset names, architectural modules).
- Drowning BM25 rank under $3\times$ dense weighting causes exact term matches to lose priority to generic semantic summaries.

---

## 2. Target for Iteration 018

- **Balanced Dense Ratio**: Test $w_{dense}=1.5$ (vs $2.0$) to explore whether a more balanced ratio protects QASPER while preserving FiQA gains.
