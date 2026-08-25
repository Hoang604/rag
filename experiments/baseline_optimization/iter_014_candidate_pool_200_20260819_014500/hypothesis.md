# Iteration 014: Candidate Pool Expansion ($N=150 \rightarrow 200$)

- **Timestamp**: 20260819_014500
- **Directory**: `experiments/baseline_optimization/iter_014_candidate_pool_200_20260819_014500/`
- **Target Failure Mode**: Recall boundary of 150 candidates in dense candidate re-ranking.

---

## 1. Context & Rationale

Iteration 013 proved that expanding the candidate pool to 150 delivered substantial metric gains on BEIR/FiQA (+0.0213 NDCG, +0.0370 Recall@10) without degrading CUAD or SciFact. Expanding to $N=200$ tests whether further depth in Stage 2 dense candidate re-scoring continues to improve multi-hop and complex query retrieval.

## 2. Single Variable Mutation (Ablation)

- **Variable Modified**: Candidate pool size:
  $$\text{candidate\_pool\_size} = 150 \rightarrow 200$$
- **Control Variables**: Active baseline (Stopword-filtered Porter BM25, `BAAI/bge-small-en-v1.5` FP16, chunk size $512/64$, Dense-Weighted RRF $k=20, w_{dense}=2.0, w_{bm25}=1.0$).

## 3. Clean-Room IR Verification

- Candidate pool size parameter applied symmetrically across all queries. Zero `qrels` access.
