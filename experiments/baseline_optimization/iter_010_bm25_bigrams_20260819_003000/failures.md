# Iteration 010: Failure Triage & Error Analysis

Analysis of Iteration 010:

---

## 1. Bigram IDF Distortion

- In standard BM25, combining unigrams and bigrams in a flat posting list distorts document length ($L_{doc}$) by adding $N-1$ extra tokens per chunk.
- Queries matching rare 2-word combinations dominate the BM25 accumulator, causing severe false positives.

---

## 2. Target for Iteration 011

- **Local Neural Cross-Encoder Re-Ranking**: Maintain clean BM25 unigram candidate generation ($N=100$) and BGE dense scoring, but apply full cross-attention interaction (`cross-encoder/ms-marco-MiniLM-L-6-v2` or `BAAI/bge-reranker-base`) on the top-20 RRF candidate pool to perform fine-grained token-level cross-attention.
