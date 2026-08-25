# Iteration 009: Min-Max Normalized Convex Score Fusion ($\beta=0.70$)

- **Timestamp**: 20260819_001500
- **Directory**: `experiments/baseline_optimization/iter_009_convex_score_fusion_20260819_001500/`
- **Target Failure Mode**: Loss of continuous confidence margins caused by rank-only Reciprocal Rank Fusion.

---

## 1. Context & Rationale

Rank-based fusion (RRF) collapses real-valued cosine similarity scores into integer ranks ($1, 2, \dots$), treating a high-confidence semantic match (cosine similarity $0.85$) identically to a borderline candidate (cosine similarity $0.45$). Min-Max Normalized Convex Score Fusion scales both sparse BM25 scores and dense cosine scores into $[0, 1]$ over the candidate pool and computes:
$$\text{Score}(c) = \beta \cdot \text{Score}_{\text{dense}}(c) + (1-\beta) \cdot \text{Score}_{\text{bm25}}(c)$$
with $\beta = 0.70$.

## 2. Single Variable Mutation (Ablation)

- **Variable Modified**: Fusion mechanism in Two-Stage Hybrid retrieval: Rank RRF $\rightarrow$ Min-Max Normalized Convex Score Combination ($\beta=0.70$).
- **Control Variables**: Active baseline (Strict Max-Pooling, Porter Stemmed BM25 $k_1=1.5, b=0.75$, Candidate pool $N=100$, chunk size $512/64$, dense model `BAAI/bge-small-en-v1.5` FP16).

## 3. Clean-Room IR Verification

- Continuous mathematical normalization per candidate query pool. Zero `qrels` access.
