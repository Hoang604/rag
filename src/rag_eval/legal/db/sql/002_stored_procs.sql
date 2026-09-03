-- ============================================================================
-- STORED PROCEDURES & DATABASE REASONING FUNCTIONS
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. HYBRID LEGAL SEARCH WITH RECIPROCAL RANK FUSION (RRF k=60)
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
    candidate_limit INT := GREATEST(match_limit * 6, 120);
BEGIN
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
    sparse_search AS (
        SELECT 
            c.id,
            ROW_NUMBER() OVER (
                ORDER BY (
                    CASE WHEN ts_phrase IS NOT NULL AND c.tsv_content @@ ts_phrase THEN 4.0 ELSE 0.0 END
                    + CASE WHEN ts_query IS NOT NULL AND c.tsv_content @@ ts_query THEN 2.0 + COALESCE(ts_rank(c.tsv_content, ts_query, 1), 0.0) * 2.0 ELSE 0.0 END
                ) DESC
            ) AS rank_sparse
        FROM chunks c
        WHERE query_text IS NOT NULL
          AND clean_query != ''
          AND c.effective_date <= t_violation
          AND (c.expiration_date IS NULL OR c.expiration_date > t_violation)
          AND (
              (ts_phrase IS NOT NULL AND c.tsv_content @@ ts_phrase)
              OR (ts_query IS NOT NULL AND c.tsv_content @@ ts_query)
          )
        ORDER BY rank_sparse ASC
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

-- ----------------------------------------------------------------------------
-- 2. VERBATIM GREP (Trigram GIN Accelerated Exact & Word Similarity Substring Search)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION verbatim_grep(
    query_pattern TEXT,
    target_documents TEXT[] DEFAULT NULL,
    is_regex BOOLEAN DEFAULT FALSE,
    case_sensitive BOOLEAN DEFAULT FALSE,
    t_violation DATE DEFAULT CURRENT_DATE,
    match_limit INT DEFAULT 20
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
    similarity_score FLOAT
) AS $$
DECLARE
    clean_pattern TEXT := trim(query_pattern);
BEGIN
    IF is_regex THEN
        RETURN QUERY
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
            GREATEST(
                word_similarity(clean_pattern, c.verbatim_text),
                word_similarity(clean_pattern, c.contextualized_text)
            )::FLOAT AS similarity_score
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE c.effective_date <= t_violation
          AND (c.expiration_date IS NULL OR c.expiration_date > t_violation)
          AND (
              (case_sensitive AND (c.verbatim_text ~ clean_pattern OR c.contextualized_text ~ clean_pattern))
              OR (NOT case_sensitive AND (c.verbatim_text ~* clean_pattern OR c.contextualized_text ~* clean_pattern))
          )
          AND (
              target_documents IS NULL 
              OR cardinality(target_documents) = 0 
              OR d.doc_code = ANY(target_documents)
          )
        ORDER BY similarity_score DESC
        LIMIT match_limit;
    ELSE
        RETURN QUERY
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
            GREATEST(
                word_similarity(clean_pattern, c.verbatim_text),
                word_similarity(clean_pattern, c.contextualized_text)
            )::FLOAT AS similarity_score
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE c.effective_date <= t_violation
          AND (c.expiration_date IS NULL OR c.expiration_date > t_violation)
          AND (
              (case_sensitive AND (c.verbatim_text LIKE '%' || clean_pattern || '%' OR c.contextualized_text LIKE '%' || clean_pattern || '%'))
              OR (NOT case_sensitive AND (
                  c.verbatim_text ILIKE '%' || clean_pattern || '%' 
                  OR c.contextualized_text ILIKE '%' || clean_pattern || '%'
                  OR c.verbatim_text % clean_pattern
                  OR c.contextualized_text % clean_pattern
              ))
          )
          AND (
              target_documents IS NULL 
              OR cardinality(target_documents) = 0 
              OR d.doc_code = ANY(target_documents)
          )
        ORDER BY similarity_score DESC
        LIMIT match_limit;
    END IF;
END;
$$ LANGUAGE plpgsql STABLE;


-- ============================================================================
-- verbatim_grep_count: true corpus-wide match count for exhaustive queries.
--
-- verbatim_grep applies LIMIT, so the number of returned rows cannot be used to
-- report how many matches exist. Silently capping the reported total makes an
-- agent conclude the corpus contains only `limit` occurrences of a term, which
-- is a correctness failure for legal exhaustiveness questions ("every clause
-- mentioning X"). This function mirrors the predicates of verbatim_grep exactly
-- and returns the uncapped count.
-- ============================================================================
CREATE OR REPLACE FUNCTION verbatim_grep_count(
    query_pattern TEXT,
    target_documents TEXT[] DEFAULT NULL,
    is_regex BOOLEAN DEFAULT FALSE,
    case_sensitive BOOLEAN DEFAULT FALSE,
    t_violation DATE DEFAULT CURRENT_DATE
)
RETURNS BIGINT AS $$
DECLARE
    clean_pattern TEXT := trim(query_pattern);
    total BIGINT;
BEGIN
    SELECT COUNT(*) INTO total
    FROM chunks c
    JOIN documents d ON c.document_id = d.id
    WHERE c.effective_date <= t_violation
      AND (c.expiration_date IS NULL OR c.expiration_date > t_violation)
      AND (
          (is_regex AND (
              (case_sensitive AND (c.verbatim_text ~ clean_pattern OR c.contextualized_text ~ clean_pattern))
              OR (NOT case_sensitive AND (c.verbatim_text ~* clean_pattern OR c.contextualized_text ~* clean_pattern))
          ))
          OR (NOT is_regex AND (
              (case_sensitive AND (c.verbatim_text LIKE '%' || clean_pattern || '%' OR c.contextualized_text LIKE '%' || clean_pattern || '%'))
              OR (NOT case_sensitive AND (
                  c.verbatim_text ILIKE '%' || clean_pattern || '%'
                  OR c.contextualized_text ILIKE '%' || clean_pattern || '%'
                  OR c.verbatim_text % clean_pattern
                  OR c.contextualized_text % clean_pattern
              ))
          ))
      )
      AND (
          target_documents IS NULL
          OR cardinality(target_documents) = 0
          OR d.doc_code = ANY(target_documents)
      );

    RETURN COALESCE(total, 0);
END;
$$ LANGUAGE plpgsql STABLE;
