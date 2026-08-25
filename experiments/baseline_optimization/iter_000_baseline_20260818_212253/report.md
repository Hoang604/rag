# Iteration 000: Frozen Baseline Evaluation Report

- **Date / Timestamp**: 2026-08-18 21:22:53
- **Directory**: `experiments/baseline_optimization/iter_000_baseline_20260818_212253/`
- **Retriever Pipeline**: Two-Stage Hybrid (BM25 top 25 candidate filter $\rightarrow$ PyTorch `BAAI/bge-small-en-v1.5` FP16 on CUDA $\rightarrow$ Reciprocal Rank Fusion $k=60$).
- **Evaluation Protocol**: 50-query representative sample per benchmark (seed: 42, top_k: 10).

---

## 1. Quantitative Benchmark Results

| Metric | SciFact (Scientific) | QASPER (Academic) | CUAD (Legal) | BEIR/FiQA (Financial) |
| :--- | :--- | :--- | :--- | :--- |
| **HitRate@1** | 0.6600 | 0.2800 | 0.0000 | 0.2200 |
| **HitRate@3** | 0.8000 | 0.3200 | 0.0000 | 0.2800 |
| **HitRate@5** | 0.8000 | 0.3600 | 0.0200 | 0.3000 |
| **HitRate@10** | 0.8800 | 0.4000 | 0.0600 | 0.4000 |
| **Recall@10** | 0.8467 | 0.4000 | 0.0600 | 0.2470 |
| **MRR@10** | 0.7324 | 0.3119 | 0.0097 | 0.2625 |
| **NDCG@10** | **0.7512** | **0.3328** | **0.0209** | **0.2070** |

---

## 2. Primary Failure Diagnoses

1. **CUAD Domain Collapse (NDCG 0.0209, Hit@10 6.0%)**:
   - Queries are generic clause categories (`"Effective Date"`, `"Governing Law"`).
   - Corpus has 510 large contracts (60,000+ chunks).
   - Without document title or section context inside each chunk, BM25 scores identical clause text across all contracts equally, burying the target contract.
2. **BEIR/FiQA Vocabulary Gap (NDCG 0.2070, Hit@10 40.0%)**:
   - Layperson queries fail to match formal financial filing terminology during initial BM25 candidate selection.
3. **QASPER Complex Structure (NDCG 0.3328, Hit@10 40.0%)**:
   - Multi-paragraph academic papers with dense tabular and experimental sections.

---

## 3. Autonomous Next Action

- Launch Iteration 1 targeting **Context-Aware Document Header Prepending** in document chunking.
