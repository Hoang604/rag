# Iteration 004: Failure Triage & Error Analysis

Analysis of Iteration 004 (BM25 Parameter Tuning):

---

## 1. Root Cause of Cross-Domain Regression

- In CUAD and QASPER, documents are large and have high variance in clause/paragraph lengths.
- Lowering $b$ from 0.75 to 0.40 deactivated length normalization, causing long irrelevant background chunks to accumulate disproportionate BM25 score mass, displacing true answers from the candidate pool.

---

## 2. Target for Iteration 005

- **Alternative Non-Conflicting Intervention**: Multi-Chunk Evidence Accumulation with discount factor $\alpha=0.25$ to reward documents whose relevant content is distributed across multiple candidate chunks without altering Stage 1 candidate generation.
