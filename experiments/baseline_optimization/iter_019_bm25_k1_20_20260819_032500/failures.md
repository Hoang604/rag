# Iteration 019: Failure Triage & Error Analysis

Analysis of Iteration 019:

---

## 1. Term Saturation Dynamics

- $k_1=2.0$ causes repetitive keyword passages to dominate BM25 candidate selection, reducing candidate diversity and hurting dense stage re-ranking.
- $k_1=1.5$ maintains balanced multi-term matching across distinct query keywords.

---

## 2. Target for Iteration 020

- **Clean Document Header Context**: Eliminate artificial boilerplate `"Title: "` token prefix in `chunk_text()`, injecting pure `{title}\n\n` to prevent dense embedding bias.
