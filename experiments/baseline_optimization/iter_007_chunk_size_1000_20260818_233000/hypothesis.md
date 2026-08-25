# Iteration 007: Paragraph Chunk Window Expansion ($512 \rightarrow 1000$ chars)

- **Timestamp**: 20260818_233000
- **Directory**: `experiments/baseline_optimization/iter_007_chunk_size_1000_20260818_233000/`
- **Target Failure Mode**: Sentence/concept fragmentation from undersized (512 char / ~80 word) sliding window.

---

## 1. Context & Rationale

At 512 characters, sliding-window chunking slices coherent paragraphs in half, creating incomplete semantic fragments for the dense encoder and BM25 index. Expanding chunk size to 1000 characters with 150 character overlap (~160 words, ~220 tokens) captures complete paragraphs, preserving complete semantic concepts within the 512-token limit of `BAAI/bge-small-en-v1.5`.

## 2. Single Variable Mutation (Ablation)

- **Variable Modified**: Chunk parameters in baseline retrieval:
  $$\text{chunk\_size} = 512 \rightarrow 1000, \quad \text{chunk\_overlap} = 64 \rightarrow 150$$
- **Control Variables**: Active baseline (Strict Max-Pooling, Porter Stemmed BM25 $k_1=1.5, b=0.75$, Dense-Weighted RRF $k=20, w_{dense}=2.0, w_{bm25}=1.0$, Candidate pool $N=100$, un-prefixed dense query embedding).

## 3. Clean-Room IR Verification

- Uniform text slicing applied globally across all corpus documents. Zero test query peeking, zero `qrels` access.
