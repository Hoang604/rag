# Iteration 020: Failure Triage & Error Analysis

Analysis of Iteration 020:

---

## 1. Transformer Attention Dynamics

- Prefixing artificial prompt tokens like `"Title: "` consumes position-0 self-attention weights in dense bi-encoders, altering the centroid vector of document chunks.
- Natural header concatenation (`{title}\n\n{text}`) allows pre-trained language models to attend seamlessly across the title boundary.

---

## 2. Target for Iteration 021

- **Boilerplate Stopword Extension**: Add domain-agnostic corporate/citation suffix tokens (`"inc"`, `"corp"`, `"co"`, `"llc"`, `"page"`, `"section"`, `"paragraph"`, `"et"`, `"al"`) to BM25 stopwords to eliminate high-frequency false positive collisions.
