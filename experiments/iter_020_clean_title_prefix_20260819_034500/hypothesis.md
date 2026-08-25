# Iteration 020: Clean Document Header Context Injection

- **Timestamp**: 20260819_034500
- **Directory**: `experiments/iter_020_clean_title_prefix_20260819_034500/`
- **Target Failure Mode**: Boilerplate `"Title: "` keyword adding repetitive token noise and embedding centroid distortion across all chunks.

---

## 1. Context & Rationale

Currently, `chunk_text()` prepends `Title: {title}\n\n` to every chunk. The static string `"Title: "` creates two issues:
1. In BM25, the token `"title"` appears universally across the corpus, diluting term frequency statistics.
2. In Transformer bi-encoders (`BAAI/bge-small-en-v1.5`), the static prompt token occupies attention heads at the beginning of the sequence.
Replacing `Title: {title}\n\n` with direct `{title}\n\n` provides clean semantic title conditioning.

## 2. Single Variable Mutation (Ablation)

- **Variable Modified**: Title prefix format:
  $$\text{title\_prefix} = f"\{title\}\backslash n\backslash n" \text{ if } title \text{ else } ""$$
- **Control Variables**: Active baseline (Candidate pool $N=150$, Dense-Weighted RRF $k=20, w_{dense}=2.0, w_{bm25}=1.0$, Stopword-filtered Porter BM25 $k_1=1.5, b=0.75$, `BAAI/bge-small-en-v1.5` FP16, chunk size $512/64$).

## 3. Clean-Room IR Verification

- Header formatting applied universally across all corpus documents. Zero `qrels` access.
