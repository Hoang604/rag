-- ----------------------------------------------------------------------------
-- SPARSE RECALL FOR NATURAL-LANGUAGE QUESTIONS
--
-- Two defects made the sparse half of hybrid search contribute nothing:
--
-- 1. plainto_tsquery ANDs every token, stopwords included, so a real question
--    ("... bị phạt bao nhiêu tiền?") matched no chunk at all -- all 30 smoke
--    queries returned zero sparse rows.
-- 2. The tokenizer splits Vietnamese syllable by syllable, so "xe ô tô" and
--    "xe mô tô" share "xe" and "to", and single syllables carry almost no
--    selectivity: "dieu" appears in 93% of chunks, "xe" in 51%.
--
-- Candidates therefore come from adjacent syllable pairs ("xe <-> o <-> to"),
-- which is where a Vietnamese compound term actually lives. The whole-phrase
-- and full-conjunction forms stay as ranking bonuses, so a literal quotation
-- still wins outright.
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION hybrid_search(
    query_text TEXT,
    query_vector VECTOR(384),
    t_violation DATE DEFAULT CURRENT_DATE,
    match_limit INT DEFAULT 10,
    rrf_k INT DEFAULT 60
)
RETURNS TABLE (
    chunk_id UUID,
    doc_code VARCHAR,
    doc_title TEXT,
    path TEXT,
    verbatim_text TEXT,
    contextualized_text TEXT,
    metadata JSONB,
    effective_date DATE,
    expiration_date DATE,
    rrf_score DOUBLE PRECISION,
    dense_rank BIGINT,
    sparse_rank BIGINT
) AS $$
DECLARE
    clean_query TEXT := trim(COALESCE(query_text, ''));
    ts_phrase TSQUERY := CASE WHEN clean_query != '' THEN phraseto_tsquery('vietnamese_legal', clean_query) ELSE NULL END;
    ts_query TSQUERY := CASE WHEN clean_query != '' THEN plainto_tsquery('vietnamese_legal', clean_query) ELSE NULL END;
    lexemes TEXT[];
    ts_any TSQUERY;
    candidate_limit INT := GREATEST(match_limit * 6, 120);
BEGIN
    IF clean_query != '' AND ts_query IS NOT NULL AND ts_query::text != '' THEN
        lexemes := string_to_array(replace(ts_query::text, '''', ''), ' & ');
    END IF;

    IF lexemes IS NOT NULL AND array_length(lexemes, 1) >= 2 THEN
        SELECT string_agg(format('%s <-> %s', lexemes[i], lexemes[i + 1]), ' | ')
        INTO ts_any
        FROM generate_subscripts(lexemes, 1) AS i
        WHERE i < array_length(lexemes, 1);
    ELSIF lexemes IS NOT NULL THEN
        ts_any := lexemes[1]::tsquery;
    END IF;

    RETURN QUERY
    WITH dense_search AS (
        SELECT
            c.id,
            ROW_NUMBER() OVER (ORDER BY c.embedding <=> query_vector) AS rank_dense
        FROM chunks c
        WHERE query_vector IS NOT NULL
          AND c.effective_date <= t_violation
          AND (c.expiration_date IS NULL OR c.expiration_date > t_violation)
          AND c.embedding IS NOT NULL
        ORDER BY (c.embedding <=> query_vector) ASC
        LIMIT candidate_limit
    ),
    -- Ranked in two stages: ts_rank_cd over everything the pair query matches
    -- (a few thousand rows), then the phrase and conjunction bonuses over the
    -- shortlist only. Evaluating those two tsqueries per matching row instead
    -- cost an order of magnitude more than the match itself.
    sparse_pool AS (
        SELECT
            c.id,
            c.tsv_content,
            -- ts_rank, not ts_rank_cd: cover density cost 470 ms against 62 ms
            -- over the few thousand rows a pair query matches, and ranked worse
            -- (Hit@1 46.7% against 66.7%) -- proximity of scattered query
            -- syllables is noise in statutory prose.
            ts_rank(c.tsv_content, ts_any, 32) AS base_score
        FROM chunks c
        WHERE ts_any IS NOT NULL
          AND c.tsv_content @@ ts_any
          AND c.effective_date <= t_violation
          AND (c.expiration_date IS NULL OR c.expiration_date > t_violation)
        ORDER BY base_score DESC
        LIMIT candidate_limit * 2
    ),
    sparse_search AS (
        SELECT
            p.id,
            ROW_NUMBER() OVER (
                ORDER BY (
                    p.base_score * 4.0
                    + CASE WHEN ts_phrase IS NOT NULL AND p.tsv_content @@ ts_phrase THEN 4.0 ELSE 0.0 END
                    + CASE WHEN ts_query IS NOT NULL AND p.tsv_content @@ ts_query THEN 2.0 ELSE 0.0 END
                ) DESC
            ) AS rank_sparse
        FROM sparse_pool p
        LIMIT candidate_limit
    )
    SELECT
        c.id AS chunk_id,
        d.doc_code,
        d.title AS doc_title,
        c.path::text AS path,
        c.verbatim_text,
        c.contextualized_text,
        c.metadata,
        c.effective_date,
        c.expiration_date,
        (COALESCE(1.0 / (rrf_k + d_s.rank_dense), 0.0) +
         COALESCE(1.0 / (rrf_k + s.rank_sparse), 0.0))::DOUBLE PRECISION AS rrf_score,
        COALESCE(d_s.rank_dense, 999)::BIGINT AS dense_rank,
        COALESCE(s.rank_sparse, 999)::BIGINT AS sparse_rank
    FROM dense_search d_s
    FULL OUTER JOIN sparse_search s ON d_s.id = s.id
    JOIN chunks c ON c.id = COALESCE(d_s.id, s.id)
    JOIN documents d ON c.document_id = d.id
    ORDER BY rrf_score DESC
    LIMIT match_limit;
END;
$$ LANGUAGE plpgsql STABLE;
