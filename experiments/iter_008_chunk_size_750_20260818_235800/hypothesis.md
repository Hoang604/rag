# Iteration 008: Balanced Paragraph Chunk Window ($chunk\_size=750, chunk\_overlap=100$)

- **Timestamp**: 20260818_235800
- **Directory**: `experiments/iter_008_chunk_size_750_20260818_235800/`
- **Target Failure Mode**: Finding optimal chunk window resolution balancing multi-sentence reasoning (FiQA) and single-clause precision (CUAD/SciFact).

---

## 1. Context & Rationale

Iteration 007 demonstrated that 1000-character chunks significantly boosted FiQA (+0.0420 NDCG, Hit@10=64%) but caused minor clause boundary dilution on legal agreements (CUAD). A 750-character window (~115 words, ~160 tokens) provides enough context for complete explanations without crossing unrelated contract clause boundaries.

## 2. Single Variable Mutation (Ablation)

- **Variable Modified**: Chunk parameters in baseline retrieval:
  $$\text{chunk\_size} = 512 \rightarrow 750, \quad \text{chunk\_overlap} = 64 \rightarrow 100$$
- **Control Variables**: Active baseline (Strict Max-Pooling, Porter Stemmed BM25 $k_1=1.5, b=0.75$, Dense-Weighted RRF $k=20, w_{dense}=2.0, w_{bm25}=1.0$, Candidate pool $N=100$).

## 3. Clean-Room IR Verification

- Zero `qrels` access. Uniform slicing applied universally across all corpus documents.
