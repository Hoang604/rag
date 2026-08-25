# Iteration 012: Failure Triage & Error Analysis

Analysis of Iteration 012:

---

## 1. Breakthrough Mechanism

- Eliminating non-informative functional stopwords (`"the"`, `"of"`, `"this"`, `"is"`, `"to"`, `"that"`, `"should"`) allowed legal clause keywords (`"Effective Date"`, `"Governing Law"`, `"Termination"`) to dominate BM25 candidate selection.
- BM25 index creation time on BEIR/FiQA dropped from 27.4s to 19.3s (-29.5%) due to reduced inverted index postings density.

---

## 2. Target for Iteration 013

- **Candidate Pool Scaling**: Expand candidate pool size $N=100 \rightarrow 150$ to capture long-tail semantic candidates in Stage 2 dense re-ranking.
