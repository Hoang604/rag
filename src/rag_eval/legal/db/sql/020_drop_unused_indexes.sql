-- The BM25 term index (008_bm25_sparse.sql) is maintained on every chunk write and read by nothing:
-- hybrid_search ranks its keyword branch on tsv_content (017_search_contract.sql).
DROP TRIGGER IF EXISTS trg_chunks_terms ON chunks;
DROP TRIGGER IF EXISTS trg_chunks_term_count ON chunks;
DROP FUNCTION IF EXISTS index_chunk_terms();
DROP FUNCTION IF EXISTS count_chunk_terms();
DROP TABLE IF EXISTS chunk_terms;
ALTER TABLE chunks DROP COLUMN IF EXISTS term_count;
DROP FUNCTION IF EXISTS legal_terms(TEXT);
DROP FUNCTION IF EXISTS legal_syllables(TEXT);

-- chunk_matches_pattern wraps its test in a CASE, which no trigram index can serve.
DROP INDEX IF EXISTS idx_chunks_verbatim_trgm;
DROP INDEX IF EXISTS idx_chunks_context_trgm;
