# Iteration 012: BM25 Lexical English Stopword Filtering

- **Timestamp**: 20260819_011500
- **Directory**: `experiments/iter_012_bm25_stopwords_20260819_011500/`
- **Target Failure Mode**: Boilerplate functional English stopwords bloating document lengths and diluting query keyword IDF in BM25.

---

## 1. Context & Rationale

CUAD and FiQA queries frequently contain long boilerplate prefixes (e.g. `"Highlight the parts (if any) of this contract related to..."`, `"What is considered a..."`). Discarding high-frequency functional English stopwords concentrates BM25 postings and term frequencies strictly onto substantive domain concepts, preventing length penalty distortion.

## 2. Single Variable Mutation (Ablation)

- **Variable Modified**: In `src/rag_eval/baseline/bm25.py`, filter tokens using standard English stopword set during BM25 indexing and query tokenization.
- **Control Variables**: Active baseline (`BAAI/bge-small-en-v1.5` FP16, Strict Max-Pooling, Porter Stemming, Candidate pool $N=100$, chunk size $512/64$, Dense-Weighted RRF $k=20, w_{dense}=2.0, w_{bm25}=1.0$).

## 3. Clean-Room IR Verification

- Standard static English stopword set applied universally across all corpus documents and queries. Zero `qrels` access.
