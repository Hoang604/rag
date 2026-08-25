# Iteration 015: Sharpened Reciprocal Rank Fusion Smoothing ($k=10$)

- **Timestamp**: 20260819_021000
- **Directory**: `experiments/iter_015_rrf_k10_20260819_021000/`
- **Target Failure Mode**: Flat rank smoothing ($k=20$) failing to give adequate priority to unanimous top-ranked neural candidates.

---

## 1. Context & Rationale

Reciprocal Rank Fusion formula $\frac{w}{k + \text{rank}}$ uses constant $k$ to smooth the rank decay. Decreasing $k=20 \rightarrow 10$ sharpens the penalty for lower ranks: rank 1 receives $2.7\times$ the score weight of rank 20 (compared to only $1.9\times$ with $k=20$), boosting high-confidence top-3 predictions to the top of the final output.

## 2. Single Variable Mutation (Ablation)

- **Variable Modified**: RRF smoothing constant:
  $$\text{rrf\_k} = 20 \rightarrow 10$$
- **Control Variables**: Active baseline (Candidate pool $N=150$, Stopword-filtered Porter BM25, `BAAI/bge-small-en-v1.5` FP16, chunk size $512/64$, $w_{dense}=2.0, w_{bm25}=1.0$).

## 3. Clean-Room IR Verification

- RRF mathematical formulation applied identically across all queries. Zero `qrels` access.
