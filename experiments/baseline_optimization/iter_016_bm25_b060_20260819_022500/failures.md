# Iteration 016: Failure Triage & Error Analysis

Analysis of Iteration 016:

---

## 1. Document Length Dynamics

- In financial Q&A (FiQA), documents exhibit high variance in paragraph length.
- Setting $b=0.60$ provides insufficient length dampening for verbose off-topic passages, leading to BM25 candidate degradation.
- $b=0.75$ remains the robust universal standard.

---

## 2. Target for Iteration 017

- **Dense Rank Weight Scaling**: Scale $w_{dense} = 2.0 \rightarrow 3.0$ in Dense-Weighted RRF to test whether increasing neural semantic priority further improves complex multi-domain retrieval.
