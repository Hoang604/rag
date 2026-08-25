# Iteration 011: Local Neural Embedding Capacity Scaling (`BAAI/bge-base-en-v1.5`)

- **Timestamp**: 20260819_004500
- **Directory**: `experiments/baseline_optimization/iter_011_bge_base_20260819_004500/`
- **Target Failure Mode**: Semantic capacity bottleneck of small 33M-parameter 384-dimensional bi-encoder representations on specialized domain vocabularies.

---

## 1. Context & Rationale

`BAAI/bge-small-en-v1.5` (33M params, 384-d) operates near its representation limits on domain-specialized terms. Upgrading to `BAAI/bge-base-en-v1.5` (110M params, 768-d) doubles vector expressiveness and tripling neural capacity while remaining 100% local, zero-API, and zero-LLM.

## 2. Single Variable Mutation (Ablation)

- **Variable Modified**: Dense model architecture:
  $$\text{model\_name} = \text{"BAAI/bge-small-en-v1.5"} \rightarrow \text{"BAAI/bge-base-en-v1.5"}$$
- **Control Variables**: Active baseline (Strict Max-Pooling, Porter-stemmed BM25 unigrams $k_1=1.5, b=0.75$, Candidate pool $N=100$, chunk size $512/64$, Dense-Weighted RRF $k=20, w_{dense}=2.0, w_{bm25}=1.0$).

## 3. Clean-Room IR Verification

- Fully pre-trained open-weight local transformer encoder executed symmetrically across passages and queries. Zero `qrels` access.
