# Iteration 004: BM25 Passage Parameter Tuning ($k_1=1.2, b=0.40$)

- **Timestamp**: 20260818_224700
- **Directory**: `experiments/baseline_optimization/iter_004_bm25_tuning_20260818_224700/`
- **Target Failure Mode**: Length normalization penalty distortion on detailed passage chunks in BM25.

---

## 1. Context & Rationale

Default BM25 length normalization ($b=0.75$) penalizes chunks that exceed the average corpus length. In passage retrieval with fixed sliding windows, chunks with higher token density (often rich in semantic context) are penalized compared to short fragments. Relaxing length normalization to $b=0.40$ and term saturation to $k_1=1.2$ prevents under-scoring of dense descriptive chunks during initial candidate retrieval.

## 2. Single Variable Mutation (Ablation)

- **Variable Modified**: BM25 Hyperparameters: $k_1=1.5 \rightarrow 1.2$, $b=0.75 \rightarrow 0.40$.
- **Control Variables**: Porter Stemming, Dense-Weighted RRF ($k=20, w_{dense}=2.0$), Candidate pool $N=100$, Dense model `BAAI/bge-small-en-v1.5` FP16.

## 3. Clean-Room IR Verification

- Zero `qrels` leakage. Pure algorithmic tuning applied uniformly across all datasets.
