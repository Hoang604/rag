# Retrieval ablation: road-traffic-law search

Measured 2026-10-14 on worktree `D:/rw/int` (branch `task/thesis-integration`, HEAD `db0b7cc` = main + PRs #15, #16, #17), database `rag_legal_int` (fresh snapshot import: 6,775 chunks, all embedded with Qwen3-Embedding-0.6B at 512 dims). Eval set `data/eval/retrieval.jsonl`: dev 592 cases, holdout 123 cases. Machine: Xeon W-10855M (6 cores), 32 GB RAM, Quadro T2000 (4 GB). The project's torch build is CPU-only, so every query embedding below ran on the CPU.

## Main table

| # | Configuration | Dev found | Holdout found | Dev Hit@1 / Hit@5 / MRR | Holdout Hit@1 / Hit@5 / MRR | Latency p50 / p95 (ms) | of which DB p50 / p95 |
|---|---|---|---|---|---|---|---|
| 1 | Dense only (Qwen3-0.6B, query prompt) | 496/592 (83.8%) | 106/123 (86.2%) | 50.0 / 78.4 / 0.617 | 56.9 / 83.7 / 0.673 | 364 / 515 | 38 / 54 |
| 1b | Dense only, no query prompt | 484/592 (81.8%) | 107/123 (87.0%) | 47.6 / 74.8 / 0.586 | 52.8 / 79.7 / 0.633 | 278 / 399 | 38 / 52 |
| 2 | Sparse only: BM25 (`chunk_terms`, migration 022) | 525/592 (88.7%) | 114/123 (92.7%) | 57.8 / 80.9 / 0.681 | 61.8 / 88.6 / 0.734 | 50 / 85 | 50 / 85 |
| 3 | Sparse only: old `ts_rank` branch (main before #15) | 398/592 (67.2%) | 86/123 (69.9%) | 13.7 / 45.8 / 0.275 | 16.3 / 50.4 / 0.286 | 38 / 78 | 38 / 78 |
| 4 | Hybrid: dense + BM25, RRF k=20, no verbatim branch | 539/592 (91.0%) | 117/123 (95.1%) | 59.3 / 82.6 / 0.695 | 63.4 / 88.6 / 0.742 | 406 / 573 | 80 / 123 |
| 4b | Hybrid as on main: dense (no prompt) + `ts_rank`, RRF k=60 | 516/592 (87.2%) | 112/123 (91.1%) | 54.7 / 80.2 / 0.655 | 60.2 / 86.2 / 0.720 | 312 / 460 | 71 / 117 |
| **5** | **Full `search` as shipped** (hybrid + verbatim pattern branch, query prompt, RRF k=20, verbatim ordered by query vector) | **553/592 (93.4%)** | **120/123 (97.6%)** | 58.6 / 83.8 / 0.692 | 64.2 / 88.6 / 0.751 | 501 / 690 | 170 / 245 |
| 6a | 5 without the query prompt | 549/592 (92.7%) | 119/123 (96.7%) | 56.2 / 84.5 / 0.679 | 64.2 / 89.4 / 0.751 | 414 / 561 | 170 / 236 |
| 6b | 5 with RRF k=60 | 549/592 (92.7%) | 120/123 (97.6%) | 58.4 / 83.3 / 0.690 | 64.2 / 87.8 / 0.750 | 500 / 678 | 170 / 240 |
| 6c | 5 with verbatim matches in document order | 549/592 (92.7%) | 120/123 (97.6%) | 58.6 / 83.8 / 0.692 | 64.2 / 88.6 / 0.751 | 501 / 689 | 171 / 234 |
| 6d | Full `search` as on main before #15 (ts_rank, no prompt, k=60, document-order verbatim) | 538/592 (90.9%) | 116/123 (94.3%) | 56.1 / 82.4 / 0.670 | 61.0 / 85.4 / 0.720 | 404 / 562 | 162 / 235 |
| 7 | Qwen3-Embedding-4B (512 dims) | not measured | not measured | — | — | — | — |

Bucket split for the full-search rows (dev; holdout):

| Row | both | semantic only | verbatim only | missed |
|---|---|---|---|---|
| 5 shipped | 432; 99 | 107; 18 | 14; 3 | 39; 3 |
| 6a no prompt | 433; 99 | 104; 17 | 12; 3 | 43; 4 |
| 6b k=60 | 429; 99 | 105; 18 | 15; 3 | 43; 3 |
| 6c doc-order verbatim | 432; 99 | 107; 18 | 10; 3 | 43; 3 |
| 6d main before #15 | 412; 96 | 104; 16 | 22; 4 | 54; 7 |

### Check against the shipped evaluation

Row 5 reproduces `uv run rag-eval legal-eval` exactly: dev 553/592 (432 / 107 / 14 / 39), holdout 120/123 (99 / 18 / 3 / 3), output in `legal_eval_cli.txt`. The harness also ran the unmodified `run_all` path (live `SentenceTransformerQueryEmbedder`) in the same process and compared every case's bucket with row 5: 0 disagreements out of 715.

## Definitions

- **Same for every row.** Each case replays its recorded first `search` call (`query`, `pattern`, `is_regex`, `temporal_violation_date` or today, `doc_codes`) with `limit=10`. All rows use the same corpus, the same validity-date and `doc_codes` filters, and the same answer rule as `legal-eval`: a returned path answers the case if it equals one of `expected` or lies under one (`path == e or path.startswith(e + ".")`). None of the 715 queries is unaccented, so the production rule "unaccented query → no dense vector" never fires.
- **found.** Rows 1–4b return one ranked list of 10. A case counts as found if an answering path is in that list, so found equals Hit@10. Rows 5–6d return the `search` result: up to 10 hybrid hits, plus up to 10 verbatim-only hits that the hybrid list did not already contain, so at most 20 provisions. These rows are scored by the repo's own `eval.retrieval.score`, with buckets both / semantic_only / verbatim_only / missed.
- **Hit@k / MRR.** These use the rank of the first answering provision. Rows 1–4b use the position in the list (1–10). Rows 5–6d use the `rank` field of the `search` result, which is global over all 20 slots: every `both` hit first, then `semantic_only`, then `verbatim_only`. MRR counts a miss as 0. Hit@1 and Hit@5 are therefore comparable across all rows. "found" is not quite comparable: the full-search rows get up to 10 extra verbatim slots (ranks 11–20). For those rows Hit@10 is 91.0% dev / 95.1% holdout, identical to row 4.
- **Latency.** Wall-clock time per case, run sequentially with nothing else running, after a 5-case warm-up. It is DB/composition time plus that case's measured query-embedding time (one `compute_chunk_embeddings([query])` call on the CPU, about 325 ms with the prompt and 240 ms without). BM25 and ts_rank rows embed nothing. p50 and p95 are taken over all 715 cases. The full rows include `annotate_amendments` and `paths_matching_pattern`, as in production.

### How each row is produced (`ablation.py`)

| Row | Code path | Differs from shipped by |
|---|---|---|
| 1 | shipped SQL `hybrid_search(query_text='', vector, …, k=20)`; an empty text gives no BM25 terms, so the order is the dense order | sparse branch removed |
| 1b | same, vector embedded without `prompt_name="query"` | also no prompt |
| 2 | shipped SQL `hybrid_search(query, NULL vector, …)` | dense branch removed |
| 3 | main's 017 `hybrid_search` body, copied verbatim into `pg_temp.old_hybrid_search`, called with a NULL vector. Its `tsv_content` is rebuilt exactly as main's trigger built it (`vietnamese_legal` = simple + unaccent; contextualized text weight A, verbatim text weight B, `unglue_footnote_markers`), into a temp table with a GIN index. The text-search configuration, temp table and temp function are created inside one transaction that is **rolled back** at the end. The only change to the function body is `c.tsv_content` → `JOIN old_tsv o … o.tsv_content`. | ranking function = main's |
| 4 | shipped SQL `hybrid_search(query, vector, …, k=20)`, top 10 | verbatim branch removed |
| 4b | the temp old function with a no-prompt vector and k=60 | main's hybrid |
| 5 | unmodified `LegalRuntimeSensors.search`; its embedder returns the precomputed vector (same call as the live embedder) | none (verified above) |
| 6a | as 5, embedder returns the no-prompt vector | no prompt (hybrid and verbatim ordering both use it) |
| 6b | as 5, module constant `sensors.RRF_K` set to 60 for the call | k=60 |
| 6c | as 5, but the repository's `verbatim_grep` is wrapped to pass `query_vector=None`, so SQL falls back to `ORDER BY doc_code, start_line, path` | verbatim order |
| 6d | as 5 with all three main-era choices plus the old ts_rank function in place of `hybrid_search` | everything PR #15 changed in retrieval |

Row 6d approximates main on today's corpus. The corpus, amendment notes (#16) and the verbatim SQL are today's, and only the ranking choices are main's. Main's verbatim SQL differs only in ordering, which 6d reproduces.

## Discussion per factor

- **Sparse ranking function: BM25 vs ts_rank (rows 2, 3).** This is the largest single effect. Sparse-only Hit@1 goes from 13.7% to 57.8% (dev) and found from 67.2% to 88.7%. Paired exact McNemar on all 715 cases: found +163 / −8 (p ≈ 1e−38), Hit@1 +335 / −18. Main's ts_rank with cover-density normalisation (32) and a bonus for the full AND query puts long multi-provision chunks first. BM25 over syllables and syllable bigrams, with length normalisation, ranks the specific provision.
- **Dense vs sparse vs hybrid (rows 1, 2, 4).** On this eval set BM25 alone beats dense alone (Hit@1 57.8 vs 50.0 dev; found +71 / −34 over all cases, p < 0.001). The case queries are written in statutory wording, which suits lexical matching, so this should not be read as a claim about colloquial user questions. Fusion beats both. Against dense, hybrid gains found +64 / −10 (p ≈ 1e−10) and Hit@1 +98 / −35. Against BM25, hybrid gains found +29 / −12 (p = 0.01), but Hit@1 is not significantly different (+71 / −60, p = 0.38).
- **Verbatim pattern branch (row 4 → 5).** It adds recall only: found +17 / −0 over all cases (dev 91.0 → 93.4%, p ≈ 1.5e−5; holdout 95.1 → 97.6%). These cases are the `verbatim_only` bucket at ranks 11–20. Hit@1 does not improve (dev 59.3 → 58.6; +24 / −27, n.s.), because promoting `both` hits ahead of `semantic_only` hits reorders the top. It costs about 90 ms DB time at p50.
- **Query prompt (5 vs 6a; 1 vs 1b).** The prompt is a small but consistent gain. On full search, found +7 / −2 (n.s.) and Hit@1 +27 / −13 (p = 0.04, all cases; p = 0.016 dev). Holdout shows no difference. It costs about 85 ms of CPU embedding time per query, because the instruction prefix lengthens the input.
- **RRF k = 20 vs 60 (5 vs 6b).** 4 dev cases are found only with k=20, none only with k=60, and holdout is unchanged. Hit@1 is equal within noise (+3 / −2). Neither difference is statistically meaningful (p = 0.125). It does not affect latency.
- **Verbatim ordering by query vector vs document order (5 vs 6c).** It only matters when a pattern has more than 10 matches. Ordering by query vector recovers 4 dev cases (verbatim_only 10 → 14) and changes nothing in the top ranks (Hit@1 identical). p = 0.125 and latency is unchanged.
- **Everything in PR #15 together (6d → 5).** found +26 / −7 over all cases (p = 0.001): dev 90.9 → 93.4%, holdout 94.3 → 97.6%, and dev misses fall from 54 to 39. Hit@1 rises 56.1 → 58.6 dev and 61.0 → 64.2 holdout (+68 / −49, p = 0.096). Most of the gain comes from BM25 replacing ts_rank (row 4b → 4: found 87.2 → 91.0% dev). The other three factors each add a few cases.
- **Embedding model size (row 7): not run.** The worktree's torch build is CPU-only, and the 4 GB T2000 cannot hold Qwen3-Embedding-4B in fp16 (8.0 GB of weights). On the CPU, a timed 50-chunk random sample with the **0.6B** model took 333 s (`estimate_4b.py`, `estimate_4b.json`). Scaled by corpus size that is about 11.5 h for 0.6B, and scaling by parameter count (4.02B / 0.60B = 6.75×) gives about 77 h for 4B, far beyond the 1-hour budget. No usable 4B vectors exist for this corpus either. The 4B vectors computed on Kaggle on 2026-10-02 (`rag/.cache/kaggle/out/chunks_qwen4b_512.npy`) cover an older ingestion of 6,735 chunks, and only 129 of today's 6,775 chunk texts match them exactly (`overlap_4b.py`). No historical evaluated 4B result was found in the repo history, `docs/`, or the local reports: `BAO_CAO_2026-10-01.md` only records the plan to embed on Kaggle. **There is therefore no 4B number to report, comparable or not.** The only related historical number is 0.6B dense-only Hit@1 on the old eval sets and corpus (dev 65.5 / holdout 70.0, `BAO_CAO_2026-10-01.md`), which is not comparable with this table.

Caveats:
- The eval queries are agent-style statutory queries, not raw user questions.
- The dense branch runs through the HNSW index, as shipped, so dense ranks are approximate nearest neighbours.
- With n = 123, holdout differences of 1–4 cases are not significant.
- Row 3's ordering has no path tie-break, exactly as on main, so ties among equal ts_rank scores come in arbitrary order.

## Files

- `ablation.py`: the harness for all rows. It prints a summary, writes `per_case.json` and `summary.json`, and runs the live `run_all` check.
- `per_case.json`: for each case id, the split, query and expected paths. For each configuration: `found`, `found_in`, `rank`, `matched_path`, `result_size`, `returned` (the ranked paths), `db_ms`, `embed_ms`, `total_ms`.
- `summary.json`: per configuration and split, found, Hit@1/5/10, MRR and buckets, plus latency percentiles and the live-path check.
- `paired.py` / `paired.json`: exact McNemar tests (found and Hit@1) for the pairs discussed, with the case ids that flip.
- `legal_eval_cli.txt`: output of the shipped `rag-eval legal-eval`.
- `estimate_4b.py` / `estimate_4b.json`, `overlap_4b.py`: the 4B feasibility check.
- `run.log`: console log of the main run.

## Reproduction

```bash
cd D:/rw/int
export DATABASE_URL=postgresql://postgres:postgres@localhost:15432/rag_legal_int PYTHONIOENCODING=utf-8
uv run rag-eval legal-eval                                   # shipped totals (row 5)
uv run python D:/rw/ablation/ablation.py                     # all rows, about 45 min on CPU; --limit-cases N for a smoke run, --skip-live to skip the live check
uv run python D:/rw/ablation/paired.py                       # paired McNemar tests
uv run python D:/rw/ablation/estimate_4b.py                  # 4B feasibility (CPU timing)
uv run python D:/rw/ablation/overlap_4b.py "<path to rag/.cache/kaggle>"
```

`ablation.py` writes nothing to the database. Its text-search configuration, temp table and temp function live inside one transaction that it rolls back. No `embedding_cache` rows were added.
