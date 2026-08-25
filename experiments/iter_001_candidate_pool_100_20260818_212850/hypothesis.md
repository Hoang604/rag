# Iteration 001: Candidate Pool Expansion ($N=100$)

- **Timestamp**: 20260818_212850
- **Directory**: `experiments/iter_001_candidate_pool_100_20260818_212850/`
- **Target Failure Mode**: Recall Miss due to Stage 1 Candidate Pool Constriction.

---

## 1. Context & Rationale

In Run 0 (Baseline), candidate pool size was constrained to $N=25$. In large corpora such as BEIR/FiQA (118,531 chunks) and CUAD (60,024 chunks), 25 candidate chunks represent at most 0.02% to 0.04% of the corpus. When lexical surface forms partially match non-target chunks, the true relevant documents are truncated before the neural bi-encoder ever scores them.

## 2. Single Variable Mutation (Ablation)

- **Variable Modified**: Candidate pool size $N$: $25 \rightarrow 100$.
- **Control Variables**: BM25 parameters ($k_1=1.5, b=0.75$), dense model (`BAAI/bge-small-en-v1.5` FP16 on CUDA), chunking ($512/64$), fusion ($RRF, k=60$), evaluation queries (50 queries, seed 42).

## 3. Clean-Room IR Verification

- Zero `qrels.jsonl` access.
- Zero query-dependent indexing.
- Pure unsupervised candidate expansion applied uniformly across all datasets.
