# Iteration 006: Canonical BGE Query Instruction Prefix

- **Timestamp**: 20260818_231500
- **Directory**: `experiments/iter_006_bge_query_instruction_20260818_231500/`
- **Target Failure Mode**: Query-Passage embedding space misalignment in dense cosine scoring.

---

## 1. Context & Rationale

BAAI's BGE embedding architecture is pre-trained with asymmetric task-specific instruction prefixes on the query side (`"Represent this sentence for searching relevant passages: {query}"`) to map question representations into the same vector subspace as answer passages. In prior iterations, raw query text was embedded without this prefix.

## 2. Single Variable Mutation (Ablation)

- **Variable Modified**: In `DenseCandidateScorer`, prefix queries with canonical BGE retrieval prompt:
  $$\text{Query}_{\text{dense}} = \text{"Represent this sentence for searching relevant passages: "} + \text{query}$$
- **Control Variables**: Active baseline (Strict Max-Pooling, Porter Stemmed BM25, Dense-Weighted RRF $k=20, w_{dense}=2.0$, candidate pool $N=100$).

## 3. Clean-Room IR Verification

- Canonical model instruction applied universally across all queries. Zero dataset-specific heuristics, zero `qrels` access.
