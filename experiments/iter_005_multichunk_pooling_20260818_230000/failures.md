# Iteration 005: Failure Triage & Error Analysis

Analysis of Iteration 005 failure:

---

## 1. Root Cause of Multi-Chunk Pooling Failure

- Single-claim abstracts (SciFact) and targeted paper facts (QASPER) reside in exactly one concise paragraph.
- Any additive multi-chunk accumulation penalizes single-chunk precision by inflating documents that happen to generate multiple weak lexical matches.
- Strict Max-Pooling remains optimal for precision-critical IR.

---

## 2. Target for Iteration 006

- **Neural Alignment Optimization**: Apply the canonical BGE instruction prefix (`"Represent this sentence for searching relevant passages: "`) to queries before dense embedding to align query representations with passage embeddings in the vector space.
