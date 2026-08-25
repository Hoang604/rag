# Iteration 017: Dense Rank Weight Scaling in RRF ($w_{dense}=3.0, w_{bm25}=1.0$)

- **Timestamp**: 20260819_024500
- **Directory**: `experiments/iter_017_dense_weight_3_20260819_024500/`
- **Target Failure Mode**: Insufficient ranking advantage given to high-scoring neural embeddings over unigram BM25 matches in domain-specific queries.

---

## 1. Context & Rationale

Dense neural embeddings (`BAAI/bge-small-en-v1.5`) provide high semantic alignment for abstract scientific queries (SciFact) and paraphrased financial queries (FiQA). Increasing the dense weight from $w_{dense}=2.0 \rightarrow 3.0$ allocates $75\%$ of RRF weight to dense rankings, granting unanimous neural candidate selections a stronger push into the top-3.

## 2. Single Variable Mutation (Ablation)

- **Variable Modified**: Dense RRF weight:
  $$w_{dense} = 2.0 \rightarrow 3.0$$
- **Control Variables**: Active baseline (Candidate pool $N=150$, Stopword-filtered Porter BM25 $k_1=1.5, b=0.75$, `BAAI/bge-small-en-v1.5` FP16, chunk size $512/64$, RRF $k=20, w_{bm25}=1.0$).

## 3. Clean-Room IR Verification

- RRF weighting applied uniformly across all queries. Zero `qrels` access.
