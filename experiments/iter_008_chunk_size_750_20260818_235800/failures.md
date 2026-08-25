# Iteration 008: Failure Triage & Error Analysis

Analysis of Iteration 008:

---

## 1. Finding

- Paragraph chunking beyond 512 characters dilutes contract clause retrieval in legal documents because clauses are concise and localized.
- SciFact, QASPER, and FiQA consistently benefit from neural score fidelity.

---

## 2. Target for Iteration 009

- **Score-Preserving Fusion**: Replace rank-only RRF with Min-Max Normalized Convex Score Fusion ($\beta=0.70 \cdot \text{Dense}_{\text{norm}} + 0.30 \cdot \text{BM25}_{\text{norm}}$) to retain continuous neural semantic confidence margins instead of collapsing them into discrete rank integers.
