# Iteration 021: Boilerplate Domain-Agnostic Entity/Citation Stopword Extension

- **Timestamp**: 20260819_040500
- **Directory**: `experiments/iter_021_extended_stopwords_20260819_040500/`
- **Target Failure Mode**: Ubiquitous boilerplate corporate/citation suffix tokens causing spurious lexical candidate retrieval in contracts and scientific papers.

---

## 1. Context & Rationale

Tokens like `"inc"`, `"corp"`, `"co"`, `"ltd"`, `"llc"`, `"page"`, `"section"`, `"paragraph"`, `"et"`, `"al"` appear in nearly every corporate contract (CUAD), scientific paper (SciFact/QASPER), and financial disclosure (FiQA). When queries contain these terms, BM25 assigns substantial candidate priority to passages with repeated boilerplate rather than topical legal/scientific clauses. Adding them to `ENGLISH_STOPWORDS` eliminates this noise.

## 2. Single Variable Mutation (Ablation)

- **Variable Modified**: `ENGLISH_STOPWORDS` static set:
  $$\text{Add } \{\text{"inc"}, \text{"corp"}, \text{"co"}, \text{"ltd"}, \text{"llc"}, \text{"page"}, \text{"section"}, \text{"paragraph"}, \text{"et"}, \text{"al"}\}$$
- **Control Variables**: Active baseline (Clean title prefix, Candidate pool $N=150$, Dense-Weighted RRF $k=20, w_{dense}=2.0, w_{bm25}=1.0$, Porter BM25 $k_1=1.5, b=0.75$, `BAAI/bge-small-en-v1.5` FP16, chunk size $512/64$).

## 3. Clean-Room IR Verification

- Stopwords applied symmetrically to both indexing and queries. Zero `qrels` access.
