# Iteration 021: Boilerplate Domain-Agnostic Entity/Citation Stopword Extension Report

- **Timestamp**: 2026-08-19 04:05:00
- **Directory**: `experiments/iter_021_extended_stopwords_20260819_040500/`
- **Tested Mutation**: Added corporate entity suffixes (`"inc"`, `"corp"`, `"co"`, `"ltd"`, `"llc"`) and academic citation/structure markers (`"page"`, `"section"`, `"paragraph"`, `"et"`, `"al"`) to BM25 stopwords.

---

## 1. Quantitative Delta vs Active Baseline (Iteration 020)

| Benchmark Dataset | Metric | Iteration 020 Baseline | Iteration 021 (Extended Stopwords) | Delta ($\Delta$) | Outcome |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **QASPER** | NDCG@10 | 0.3417 | **0.3443** | **+0.0026** | **All-Time High (+1%)** |
| | MRR@10 | 0.3107 | **0.3141** | **+0.0034** | **All-Time High (+1%)** |
| **SciFact** | NDCG@10 | 0.8238 | 0.8238 | 0.0000 | Identical (72% Hit@1) |
| | MRR@10 | 0.7942 | 0.7942 | 0.0000 | Identical |
| **CUAD** | HitRate@10 | 0.0800 | 0.0800 | 0.0000 | Identical (8% Record) |
| | NDCG@10 | 0.0444 | 0.0444 | 0.0000 | Identical |
| **BEIR/FiQA** | NDCG@10 | 0.2997 | 0.2997 | 0.0000 | Identical (64% Hit@10) |
| | MRR@10 | 0.3624 | 0.3624 | 0.0000 | Identical |

---

## 2. Decision & Delta Gate Evaluation

- **Delta Gate Outcome**: **PROMOTE TO ACTIVE BASELINE**.
- **Rationale**: Eliminating boilerplate academic citations and legal entity noise yielded an all-time peak on QASPER (NDCG 0.3443, MRR 0.3141) while retaining full performance across SciFact, CUAD, and FiQA.
- **Action**: Adopt extended domain-agnostic stopword set as active baseline.
