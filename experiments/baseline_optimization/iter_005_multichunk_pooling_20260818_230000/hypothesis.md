# Iteration 005: Multi-Chunk Evidence Accumulation ($\alpha=0.25$)

- **Timestamp**: 20260818_230000
- **Directory**: `experiments/baseline_optimization/iter_005_multichunk_pooling_20260818_230000/`
- **Target Failure Mode**: Loss of distributed document evidence under strict single-chunk max-pooling.

---

## 1. Context & Rationale

In long documents (e.g. QASPER multi-paragraph papers, CUAD multi-page agreements, FiQA detailed analyses), an answer's relevance is often distributed across multiple distinct chunks. Strict max-pooling ($\max_{c} \text{score}(c)$) discards all chunks except the single highest, ignoring the aggregate probability mass of documents with multiple candidate matches. Using decayed accumulation:
$$\text{Score}(doc) = \max_{c \in doc} \text{score}(c) + 0.25 \times \sum_{c \in doc \setminus \{c_{max}\}} \text{score}(c)$$
rewards documents with dense multi-passage relevance.

## 2. Single Variable Mutation (Ablation)

- **Variable Modified**: Document score pooling: Strict $\max$ pooling $\rightarrow$ Multi-chunk decayed accumulation ($\alpha=0.25$).
- **Control Variables**: Active baseline (Porter Stemmed BM25 with $k_1=1.5, b=0.75$, Dense-Weighted RRF $k=20, w_{dense}=2.0$, candidate pool $N=100$, dense model `BAAI/bge-small-en-v1.5` FP16).

## 3. Clean-Room IR Verification

- Zero `qrels` access. Universal document-level pooling applied uniformly across all datasets.
