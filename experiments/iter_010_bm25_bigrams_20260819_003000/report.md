# Iteration 010: BM25 Unigram + Bigram Compound Phrase Postings Report

- **Timestamp**: 2026-08-19 00:30:00
- **Directory**: `experiments/iter_010_bm25_bigrams_20260819_003000/`
- **Tested Mutation**: Appended adjacent word bigrams to BM25 inverted index postings (`include_bigrams=True`).

---

## 1. Quantitative Delta vs Active Baseline (Iteration 003)

| Benchmark Dataset | Metric | Iteration 003 Baseline | Iteration 010 (Bigrams) | Delta ($\Delta$) | Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **SciFact** | NDCG@10 | 0.8263 | 0.7738 | -0.0525 | Regressed |
| | MRR@10 | 0.7942 | 0.7230 | -0.0712 | Regressed |
| | HitRate@1 | 0.7000 | 0.5800 | -0.1200 | Regressed |
| **BEIR/FiQA** | NDCG@10 | 0.2766 | 0.2744 | -0.0022 | Regressed |
| | MRR@10 | 0.3499 | 0.3395 | -0.0104 | Regressed |
| **QASPER** | NDCG@10 | 0.3473 | 0.3285 | -0.0188 | Regressed |
| **CUAD** | NDCG@10 | 0.0404 | 0.0120 | -0.0284 | Regressed |

---

## 2. Decision & Delta Gate Evaluation

- **Delta Gate Outcome**: **FAIL / REVERT**.
- **Rationale**: Bigrams bloated the vocabulary and distorted document length normalization. Rare accidental bigram matches received excessive IDF weight and displaced true unigram matches.
- **Action**: Immediately revert `bm25.py` to unigram-only tokenization (`include_bigrams=False`).
