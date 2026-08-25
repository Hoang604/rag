# Iteration 002: BM25 Morphological Stemming

- **Timestamp**: 20260818_214000
- **Directory**: `experiments/baseline_optimization/iter_002_bm25_stemming_20260818_214000/`
- **Target Failure Mode**: Lexical Morphological Gap in Stage 1 candidate retrieval (BEIR/FiQA & QASPER).

---

## 1. Context & Rationale

Error triage from Iteration 001 identified that queries frequently use morphological variants of corpus terms (e.g. *investing* vs *investment*, *mortgages* vs *mortgage*, *repaying* vs *repay*). Pure exact-token matching causes BM25 to assign 0 scores to relevant chunks, preventing them from entering the neural scoring candidate slice.

## 2. Single Variable Mutation (Ablation)

- **Variable Modified**: BM25 Tokenizer: Raw whitespace/word tokenization $\rightarrow$ Porter Stemming root normalizer.
- **Control Variables**: Candidate pool size ($N=100$), dense model (`BAAI/bge-small-en-v1.5` FP16 on CUDA), chunking ($512/64$), fusion ($RRF, k=60$), evaluation queries (50 queries, seed 42).

## 3. Clean-Room IR Verification

- Standard morphological algorithm applied symmetrically to document chunks and incoming queries.
- Zero test query memorization, zero `qrels` access.
