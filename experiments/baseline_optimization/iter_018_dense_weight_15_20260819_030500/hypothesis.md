# Iteration 018: Balanced Dense-BM25 Rank Ratio ($w_{dense}=1.5, w_{bm25}=1.0$)

- **Timestamp**: 20260819_030500
- **Directory**: `experiments/baseline_optimization/iter_018_dense_weight_15_20260819_030500/`
- **Target Failure Mode**: Over-weighting dense ranks degrading exact technical keyword precision in QASPER and SciFact.

---

## 1. Context & Rationale

Iteration 017 showed that $w_{dense}=3.0$ degraded QASPER (-0.0103 NDCG). Setting $w_{dense}=1.5, w_{bm25}=1.0$ (60% dense, 40% lexical) tests whether a more balanced hybrid weighting preserves full lexical fidelity for technical terms while maintaining neural embedding advantages.

## 2. Single Variable Mutation (Ablation)

- **Variable Modified**: Dense RRF weight:
  $$w_{dense} = 2.0 \rightarrow 1.5$$
- **Control Variables**: Active baseline (Candidate pool $N=150$, Stopword-filtered Porter BM25 $k_1=1.5, b=0.75$, `BAAI/bge-small-en-v1.5` FP16, chunk size $512/64$, RRF $k=20, w_{bm25}=1.0$).

## 3. Clean-Room IR Verification

- RRF weighting applied uniformly across all queries. Zero `qrels` access.
