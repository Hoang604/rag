# Iteration 010: BM25 Unigram + Bigram Compound Phrase Postings

- **Timestamp**: 20260819_003000
- **Directory**: `experiments/baseline_optimization/iter_010_bm25_bigrams_20260819_003000/`
- **Target Failure Mode**: Spurious disconnected unigram matches in BM25 displacing multi-word technical and legal terms.

---

## 1. Context & Rationale

In unigram-only BM25, a chunk matching separate words `"effective"` and `"date"` across distant sentences scores equally to an exact adjacent phrase `"Effective Date"`. Indexing contiguous word bigrams (`w1_w2`) alongside unigrams assigns high inverted document frequency (IDF) weights to exact phrase co-occurrences, dramatically improving candidate filtering precision on CUAD legal clauses and FiQA financial terms.

## 2. Single Variable Mutation (Ablation)

- **Variable Modified**: In `BM25Index.tokenize()`, append adjacent bigrams to token stream:
  $$\text{Tokens}(T) = [w_1, w_2, \dots, w_m] \cup [w_1\_w_2, w_2\_w_3, \dots, w_{m-1}\_w_m]$$
- **Control Variables**: Active baseline (Strict Max-Pooling, Dense-Weighted RRF $k=20, w_{dense}=2.0, w_{bm25}=1.0$, Candidate pool $N=100$, chunk size $512/64$, dense model `BAAI/bge-small-en-v1.5` FP16).

## 3. Clean-Room IR Verification

- Standard n-gram tokenization applied symmetrically across corpus passages and queries. Zero `qrels` access.
