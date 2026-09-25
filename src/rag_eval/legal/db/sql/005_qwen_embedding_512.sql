DROP INDEX IF EXISTS idx_chunks_embedding;
UPDATE chunks SET embedding = NULL;
ALTER TABLE chunks ALTER COLUMN embedding TYPE VECTOR(512);
CREATE INDEX idx_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);

DROP FUNCTION IF EXISTS hybrid_search CASCADE;

CREATE OR REPLACE FUNCTION hybrid_search(
    query_text TEXT,
    query_vector VECTOR(512),
    t_violation DATE DEFAULT CURRENT_DATE,
    match_limit INT DEFAULT 10,
    rrf_k INT DEFAULT 60,
    doc_codes TEXT[] DEFAULT NULL
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
    sparse_rank BIGINT,
    dense_similarity DOUBLE PRECISION
) AS $$
DECLARE
    clean_query TEXT := trim(COALESCE(query_text, ''));
    ts_query TSQUERY := CASE WHEN clean_query != '' THEN plainto_tsquery('vietnamese_legal', clean_query) ELSE NULL END;
    lexemes TEXT[];
    ts_any TSQUERY;
    candidate_limit INT := GREATEST(match_limit * 6, 120);
    scope_ids UUID[];
BEGIN
    IF doc_codes IS NOT NULL AND cardinality(doc_codes) > 0 THEN
        SELECT array_agg(id) INTO scope_ids
        FROM documents WHERE documents.doc_code = ANY(doc_codes);
        IF scope_ids IS NULL THEN
            RETURN;
        END IF;
    END IF;

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
            ROW_NUMBER() OVER (ORDER BY c.embedding <=> query_vector) AS rank_dense,
            (1.0 - (c.embedding <=> query_vector))::DOUBLE PRECISION AS similarity
        FROM chunks c
        WHERE query_vector IS NOT NULL
          AND c.effective_date <= t_violation
          AND (c.expiration_date IS NULL OR c.expiration_date > t_violation)
          AND c.embedding IS NOT NULL
          AND (scope_ids IS NULL OR c.document_id = ANY(scope_ids))
        ORDER BY (c.embedding <=> query_vector) ASC
        LIMIT candidate_limit
    ),
    sparse_pool AS (
        SELECT
            c.id,
            c.tsv_content,
            COALESCE(ts_rank(c.tsv_content, ts_any, 32), 0.0) AS base_score
        FROM chunks c
        WHERE (
                (ts_any IS NOT NULL AND c.tsv_content @@ ts_any)
                OR (ts_query IS NOT NULL AND c.tsv_content @@ ts_query)
              )
          AND c.effective_date <= t_violation
          AND (c.expiration_date IS NULL OR c.expiration_date > t_violation)
          AND (scope_ids IS NULL OR c.document_id = ANY(scope_ids))
        LIMIT candidate_limit * 2
    ),
    sparse_search AS (
        SELECT
            p.id,
            ROW_NUMBER() OVER (
                ORDER BY (
                    p.base_score * 4.0
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
        COALESCE(s.rank_sparse, 999)::BIGINT AS sparse_rank,
        COALESCE(d_s.similarity, 0.0)::DOUBLE PRECISION AS dense_similarity
    FROM dense_search d_s
    FULL OUTER JOIN sparse_search s ON d_s.id = s.id
    JOIN chunks c ON c.id = COALESCE(d_s.id, s.id)
    JOIN documents d ON c.document_id = d.id
    ORDER BY rrf_score DESC
    LIMIT match_limit;
END;
$$ LANGUAGE plpgsql STABLE;
