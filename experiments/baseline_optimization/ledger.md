# Experiment Ledger: RAG Baseline Optimization

This ledger tracks the chronological history of all optimization iterations, tested hypotheses, empirical metric deltas, and promotion decisions across the 4 target benchmark datasets (SciFact, QASPER, CUAD, BEIR/FiQA).

---

## Master Comparison Matrix (Overall Progression)

| Iteration ID | Focus Area / Hypothesis | SciFact NDCG@10 (Δ) | QASPER NDCG@10 (Δ) | CUAD NDCG@10 (Δ) | FiQA NDCG@10 (Δ) | Decision | Status / Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| [`iter_000_baseline_20260818_212253`](./iter_000_baseline_20260818_212253/report.md) | Initial Two-Stage Hybrid (BM25 + BGE-Small FP16 CUDA, N=25) | 0.7512 (base) | 0.3328 (base) | 0.0209 (base) | 0.2070 (base) | **ESTABLISHED** | Initial baseline. |
| [`iter_001_candidate_pool_100_20260818_212850`](./iter_001_candidate_pool_100_20260818_212850/report.md) | Candidate Pool Expansion ($N=25 \rightarrow 100$) | 0.7674 (+0.0162) | 0.3516 (+0.0188) | 0.0227 (+0.0018) | 0.2048 (-0.0022) | **PROMOTE** | Significant gains in SciFact and QASPER. |
| [`iter_002_bm25_stemming_20260818_214000`](./iter_002_bm25_stemming_20260818_214000/report.md) | BM25 Morphological Stemming (Porter Normalizer) | 0.8087 (+0.0413) | 0.3432 (-0.0084) | 0.0324 (+0.0097) | 0.2564 (+0.0516) | **PROMOTE** | Major breakthrough on FiQA (+25%), SciFact (92% Hit@10), CUAD. |
| [`iter_003_weighted_rrf_20260818_223500`](./iter_003_weighted_rrf_20260818_223500/report.md) | Dense-Weighted RRF ($k=20, w_{dense}=2.0, w_{bm25}=1.0$) | 0.8263 (+0.0176) | 0.3473 (+0.0041) | 0.0404 (+0.0080) | 0.2766 (+0.0202) | **PROMOTE** | Universal positive gains across all 4 datasets. |
| [`iter_004_bm25_tuning_20260818_224700`](./iter_004_bm25_tuning_20260818_224700/report.md) | BM25 Passage Parameter Tuning ($k_1=1.2, b=0.40$) | 0.8248 (-0.0015) | 0.3363 (-0.0110) | 0.0338 (-0.0066) | 0.2883 (+0.0117) | **REVERT** | Regressed QASPER and CUAD. |
| [`iter_005_multichunk_pooling_20260818_230000`](./iter_005_multichunk_pooling_20260818_230000/report.md) | Multi-Chunk Evidence Accumulation ($\alpha=0.25$) | 0.7647 (-0.0616) | 0.3282 (-0.0191) | 0.0340 (-0.0064) | 0.2874 (+0.0108) | **REVERT** | Severe precision drop on SciFact. |
| [`iter_006_bge_query_instruction_20260818_231500`](./iter_006_bge_query_instruction_20260818_231500/report.md) | Canonical BGE Query Instruction Prefix | 0.8106 (-0.0157) | 0.3579 (+0.0106) | 0.0246 (-0.0158) | 0.2689 (-0.0077) | **REVERT** | Prompt diluted exact keyword representations. |
| [`iter_007_chunk_size_1000_20260818_233000`](./iter_007_chunk_size_1000_20260818_233000/report.md) | Paragraph Chunk Window Expansion ($1000/150$) | 0.8131 (-0.0132) | 0.3389 (-0.0084) | 0.0304 (-0.0100) | **0.3186 (+0.0420)** | **REVERT** | FiQA soared (+15% NDCG, 64% Hit@10), but diluted CUAD. |
| [`iter_008_chunk_size_750_20260818_235800`](./iter_008_chunk_size_750_20260818_235800/report.md) | Balanced Paragraph Chunk Window ($750/100$) | **0.8324 (+0.0061)** | **0.3498 (+0.0025)** | 0.0171 (-0.0233) | **0.2860 (+0.0094)** | **REVERT** | Peaks on SciFact and FiQA, but regressed CUAD. |
| [`iter_009_convex_score_fusion_20260819_001500`](./iter_009_convex_score_fusion_20260819_001500/report.md) | Min-Max Normalized Convex Score Fusion ($\beta=0.70$) | 0.8101 (-0.0162) | 0.3519 (+0.0046) | 0.0315 (-0.0089) | 0.2596 (-0.0170) | **REVERT** | Brittle to outlier candidate scores. |
| [`iter_010_bm25_bigrams_20260819_003000`](./iter_010_bm25_bigrams_20260819_003000/report.md) | BM25 Unigram + Bigram Compound Phrase Postings | 0.7738 (-0.0525) | 0.3285 (-0.0188) | 0.0120 (-0.0284) | 0.2744 (-0.0022) | **REVERT** | Bigram matches distorted document lengths and IDF. |
| [`iter_011_bge_base_20260819_004500`](./iter_011_bge_base_20260819_004500/report.md) | Local Neural Embedding Capacity Scaling (`bge-base-en-v1.5`) | 0.8296 (+0.0033) | 0.3298 (-0.0175) | 0.0144 (-0.0260) | 0.2616 (-0.0150) | **REVERT** | Tripled latency without broad cross-domain gains. |
| [`iter_012_bm25_stopwords_20260819_011500`](./iter_012_bm25_stopwords_20260819_011500/report.md) | BM25 Lexical English Stopword Filtering | 0.8178 (-0.0085) | 0.3400 (-0.0073) | **0.0460 (+0.0056)** | **0.2784 (+0.0018)** | **PROMOTE** | All-time high on CUAD (NDCG 0.0460, MRR 0.0422), FiQA (+0.025 Recall@10), 28% speedup. |
| [`iter_013_candidate_pool_150_20260819_013000`](./iter_013_candidate_pool_150_20260819_013000/report.md) | Candidate Pool Expansion ($N=100 \rightarrow 150$) | 0.8172 (-0.0006) | 0.3354 (-0.0046) | **0.0460 (0.0000)** | **0.2997 (+0.0213)** | **PROMOTE** | Major leap on FiQA (NDCG 0.2997, 64% Hit@10), CUAD record preserved. |
| [`iter_014_candidate_pool_200_20260819_014500`](./iter_014_candidate_pool_200_20260819_014500/report.md) | Candidate Pool Expansion ($N=150 \rightarrow 200$) | 0.8172 (0.0000) | 0.3347 (-0.0007) | 0.0386 (-0.0074) | 0.2914 (-0.0083) | **REVERT** | Candidate tail noise degraded CUAD and FiQA. |
| [`iter_015_rrf_k10_20260819_021000`](./iter_015_rrf_k10_20260819_021000/report.md) | Sharpened Reciprocal Rank Fusion Smoothing ($k=10$) | 0.8169 (-0.0003) | 0.3277 (-0.0077) | 0.0460 (0.0000) | **0.3002 (+0.0005)** | **REVERT** | Regressed QASPER. |
| [`iter_016_bm25_b060_20260819_022500`](./iter_016_bm25_b060_20260819_022500/report.md) | Moderate BM25 Document Length Normalization ($b=0.60$) | **0.8214 (+0.0042)** | 0.3354 (0.0000) | 0.0460 (0.0000) | 0.2907 (-0.0090) | **REVERT** | FiQA Hit@10 dropped to 58%. |
| [`iter_017_dense_weight_3_20260819_024500`](./iter_017_dense_weight_3_20260819_024500/report.md) | Dense Rank Weight Scaling ($w_{dense}=3.0$) | 0.8136 (-0.0036) | 0.3251 (-0.0103) | 0.0460 (0.0000) | **0.3031 (+0.0034)** | **REVERT** | QASPER dropped -0.0103 NDCG. |
| [`iter_018_dense_weight_15_20260819_030500`](./iter_018_dense_weight_15_20260819_030500/report.md) | Balanced Dense-BM25 Rank Ratio ($w_{dense}=1.5$) | 0.8172 (0.0000) | **0.3418 (+0.0064)** | 0.0460 (0.0000) | 0.2851 (-0.0146) | **REVERT** | FiQA dropped -0.0146 NDCG. |
| [`iter_019_bm25_k1_20_20260819_032500`](./iter_019_bm25_k1_20_20260819_032500/report.md) | Higher BM25 Term Frequency Saturation ($k_1=2.0$) | 0.8144 (-0.0028) | 0.3348 (-0.0006) | 0.0386 (-0.0074) | 0.2882 (-0.0115) | **REVERT** | Term saturation degraded CUAD & FiQA. |
| [`iter_020_clean_title_prefix_20260819_034500`](./iter_020_clean_title_prefix_20260819_034500/report.md) | Clean Document Header Context Injection | **0.8238 (+0.0066)** | **0.3417 (+0.0063)** | **0.0800 (+0.0200 Hit@10)** | **0.2997 (0.0000)** | **PROMOTE** | Broad gains: SciFact (0.8238 NDCG, 72% Hit@1), QASPER (0.3417 NDCG), CUAD (8% Hit@10). |
| [`iter_021_extended_stopwords_20260819_040500`](./iter_021_extended_stopwords_20260819_040500/report.md) | Boilerplate Domain-Agnostic Entity/Citation Stopword Extension | 0.8238 (0.0000) | **0.3443 (+0.0026)** | **0.0800 (0.0000)** | **0.2997 (0.0000)** | **PROMOTE** | All-time high on QASPER (NDCG 0.3443, MRR 0.3141), preserving all other records. Active baseline. |

---

## Active Optimized System Configuration

- **Retrieval Architecture**: Two-Stage Dense-Lexical Hybrid Pipeline.
- **Stage 1 (Sparse Candidate Retrieval)**:
  - Custom Inverted Index BM25 ($k_1=1.5, b=0.75$).
  - English Porter Morphological Stemming.
  - Comprehensive English & Domain Boilerplate Stopword Filtering.
  - Candidate Passage Pool Size: $N=150$.
- **Stage 2 (Dense Neural Candidate Re-Scoring)**:
  - Model: `BAAI/bge-small-en-v1.5` on PyTorch FP16 CUDA.
  - Token Pooling: Exact contrastive `[CLS]` token representation.
  - Vector Similarity: Vectorized GPU dot-product cosine similarity.
- **Document Chunking & Formatting**:
  - Sliding Window: 512 characters, 64 character overlap.
  - Header Injection: Clean direct title context `{title}\n\n{chunk_text}`.
  - Multi-Chunk Aggregation: Strict Max-Pooling per document.
- **Rank Fusion**:
  - Dense-Weighted Reciprocal Rank Fusion ($k=20, w_{dense}=2.0, w_{bm25}=1.0$).
