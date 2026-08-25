# Iteration 013: Candidate Pool Expansion ($N=100 \rightarrow 150$)

- **Timestamp**: 20260819_013000
- **Directory**: `experiments/baseline_optimization/iter_013_candidate_pool_150_20260819_013000/`
- **Target Failure Mode**: Recall ceiling of 100 candidates truncating valid semantic matches before Stage 2 dense re-ranking.

---

## 1. Context & Rationale

Expanding the candidate passage pool from $N=100$ to $N=150$ allows 50 additional candidate passages from BM25 to enter Stage 2 dense candidate re-scoring, increasing the likelihood that low-lexical-overlap but high-semantic-similarity chunks are scored and promoted by Dense-Weighted RRF.

## 2. Single Variable Mutation (Ablation)

- **Variable Modified**: Candidate pool size:
  $$\text{candidate\_pool\_size} = 100 \rightarrow 150$$
- **Control Variables**: Active baseline (Stopword-filtered Porter BM25, `BAAI/bge-small-en-v1.5` FP16, chunk size $512/64$, Dense-Weighted RRF $k=20, w_{dense}=2.0, w_{bm25}=1.0$).

## 3. Clean-Room IR Verification

- Candidate pool size parameter applied symmetrically across all queries. Zero `qrels` access.
