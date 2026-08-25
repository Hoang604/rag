# Iteration 001: Failure Triage & Error Analysis

Analysis of remaining errors across 50 queries per benchmark with candidate pool $N=100$:

---

## 1. Categorized Failure Modes

| Benchmark | Total Evaluated | Failed Queries (NDCG < 0.5) | Dominant Failure Mode | Diagnostic Summary |
| :--- | :--- | :--- | :--- | :--- |
| **BEIR/FiQA** | 50 | 33 | Lexical Morphological Gap | Layperson queries use terms like "mortgages", "investing", "repay", whereas documents contain "mortgage", "investment", "repayment". BM25 exact-token matching misses valid candidates. |
| **QASPER** | 50 | 28 | Term Variation & Technical Jargon | Inverted index lacks stemming; morphological variants of scientific verbs/nouns split BM25 frequency mass. |
| **SciFact** | 50 | 7 | Subtle Semantic Negation | Remaining misses are claims where evidence uses antonymous or refutational phrases not separated by bi-encoder dot product. |
| **CUAD** | 50 | 47 | Cross-Document Identical Clause Collisions | Standard boilerplate clauses ("Governing Law", "Effective Date") collide across all 510 contracts. |

---

## 2. Target for Iteration 002

- **Dominant Cross-Domain Issue**: Lexical term inflection and morphological fragmentation in BM25 (impacting FiQA and QASPER).
- **Proposed Intervention**: Implement lightweight Porter Stemming / morphological normalization inside BM25 tokenization.
