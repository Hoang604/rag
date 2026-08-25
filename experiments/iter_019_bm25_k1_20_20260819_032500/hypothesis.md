# Iteration 019: Higher BM25 Term Frequency Saturation ($k_1=2.0$)

- **Timestamp**: 20260819_032500
- **Directory**: `experiments/iter_019_bm25_k1_20_20260819_032500/`
- **Target Failure Mode**: Fast saturation of high-frequency informative keywords in technical contracts and scientific abstracts.

---

## 1. Context & Rationale

BM25 parameter $k_1$ dictates the rate of term frequency saturation:
$$S(q, d) = \sum_{t \in q} \text{IDF}(t) \cdot \frac{f(t, d) \cdot (k_1 + 1)}{f(t, d) + k_1 \cdot (1 - b + b \cdot \frac{|d|}{\text{avgdl}})}$$
With stopwords filtered, repeated terms in a chunk indicate high topic relevance rather than grammatical repetition. Increasing $k_1=1.5 \rightarrow 2.0$ rewards passages that discuss a core keyword multiple times.

## 2. Single Variable Mutation (Ablation)

- **Variable Modified**: BM25 term frequency saturation parameter:
  $$k_1 = 1.5 \rightarrow 2.0$$
- **Control Variables**: Active baseline (Candidate pool $N=150$, Dense-Weighted RRF $k=20, w_{dense}=2.0, w_{bm25}=1.0$, `BAAI/bge-small-en-v1.5` FP16, chunk size $512/64$, stopword filtering active, $b=0.75$).

## 3. Clean-Room IR Verification

- BM25 scoring parameter applied uniformly across all corpus documents. Zero `qrels` access.
