# Iteration 016: Moderate BM25 Document Length Normalization ($b=0.60$)

- **Timestamp**: 20260819_022500
- **Directory**: `experiments/baseline_optimization/iter_016_bm25_b060_20260819_022500/`
- **Target Failure Mode**: Over-penalization of dense information-rich passages in stopword-filtered BM25.

---

## 1. Context & Rationale

With English functional stopwords removed from the vocabulary, document length $|d|$ reflects pure content terms. At $b=0.75$, chunks containing comprehensive multi-clause explanations or technical details incur substantial length penalties. Reducing $b=0.75 \rightarrow 0.60$ moderately softens the length penalty while maintaining resistance to raw document length inflation.

## 2. Single Variable Mutation (Ablation)

- **Variable Modified**: BM25 document length penalty parameter:
  $$b = 0.75 \rightarrow 0.60$$
- **Control Variables**: Active baseline (Candidate pool $N=150$, Dense-Weighted RRF $k=20, w_{dense}=2.0, w_{bm25}=1.0$, Stopword-filtered Porter BM25 $k_1=1.5$, `BAAI/bge-small-en-v1.5` FP16, chunk size $512/64$).

## 3. Clean-Room IR Verification

- Standard BM25 length scaling applied universally across all corpus documents. Zero `qrels` access.
