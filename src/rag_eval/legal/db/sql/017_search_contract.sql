-- One search contract: the sparse branch queries the same text configuration the
-- index is built with, and the verbatim branch is an exact (case-insensitive)
-- substring or POSIX regex over a chunk's contextualized text.

DROP FUNCTION hybrid_search;
DROP FUNCTION verbatim_grep;

CREATE FUNCTION hybrid_search(
    query_text TEXT,
    query_vector VECTOR(512),
    t_violation DATE,
    match_limit INT,
    rrf_k INT,
    doc_codes TEXT[],
    path_prefix LTREE
)
RETURNS TABLE (
    chunk_id UUID,
    doc_code VARCHAR,
    doc_title TEXT,
    path TEXT,
    start_line INT,
    end_line INT,
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
    ts_query TSQUERY;
    lexemes TEXT[];
    ts_any TSQUERY;
    candidate_limit INT;
    scope_ids UUID[];
BEGIN
    IF match_limit IS NULL OR match_limit <= 0 THEN
        RAISE EXCEPTION 'match_limit must be a positive integer';
    END IF;
    IF rrf_k IS NULL OR rrf_k <= 0 THEN
        RAISE EXCEPTION 'rrf_k must be a positive integer';
    END IF;
    IF t_violation IS NULL THEN
        RAISE EXCEPTION 't_violation cannot be null';
    END IF;

    ts_query := CASE WHEN clean_query != '' THEN plainto_tsquery('vietnamese_legal', clean_query) ELSE NULL END;
    candidate_limit := GREATEST(match_limit * 6, 120);

    IF doc_codes IS NOT NULL AND cardinality(doc_codes) > 0 THEN
        SELECT array_agg(id) INTO scope_ids
        FROM documents WHERE documents.doc_code = ANY(doc_codes);
        IF scope_ids IS NULL THEN
            RETURN;
        END IF;
    END IF;

    IF clean_query != '' AND ts_query IS NOT NULL AND ts_query::text != '' THEN
        BEGIN
            lexemes := string_to_array(replace(ts_query::text, '''', ''), ' & ');
            IF lexemes IS NOT NULL AND array_length(lexemes, 1) >= 2 THEN
                SELECT string_agg(format('''%s'' <-> ''%s''', replace(lexemes[i], '''', ''''''), replace(lexemes[i + 1], '''', '''''')), ' | ')::tsquery
                INTO ts_any
                FROM generate_subscripts(lexemes, 1) AS i
                WHERE i < array_length(lexemes, 1);
            ELSIF lexemes IS NOT NULL AND array_length(lexemes, 1) = 1 THEN
                ts_any := format('''%s''', replace(lexemes[1], '''', ''''''))::tsquery;
            END IF;
        EXCEPTION WHEN OTHERS THEN
            ts_any := NULL;
        END;
    END IF;

    RETURN QUERY
    WITH dense_search AS (
        SELECT
            c.id,
            ROW_NUMBER() OVER (ORDER BY c.embedding <=> query_vector) AS rank_dense,
            (1.0 - (c.embedding <=> query_vector))::DOUBLE PRECISION AS similarity
        FROM chunks c
        WHERE query_vector IS NOT NULL
          AND c.embedding IS NOT NULL
          AND c.effective_date <= t_violation
          AND (c.expiration_date IS NULL OR c.expiration_date > t_violation)
          AND (scope_ids IS NULL OR c.document_id = ANY(scope_ids))
          AND (path_prefix IS NULL OR c.path <@ path_prefix)
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
          AND (path_prefix IS NULL OR c.path <@ path_prefix)
        ORDER BY base_score DESC
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
        c.start_line,
        c.end_line,
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

CREATE FUNCTION chunk_matches_pattern(content TEXT, pattern TEXT, is_regex BOOLEAN)
RETURNS BOOLEAN AS $$
    SELECT CASE
        WHEN is_regex THEN content ~* pattern
        ELSE strpos(lower(content), lower(pattern)) > 0
    END;
$$ LANGUAGE sql IMMUTABLE STRICT;

CREATE FUNCTION verbatim_grep(
    query_pattern TEXT,
    target_documents TEXT[],
    path_prefix LTREE,
    is_regex BOOLEAN,
    t_violation DATE,
    match_limit INT
)
RETURNS TABLE (
    chunk_id UUID,
    doc_code VARCHAR,
    doc_title TEXT,
    path TEXT,
    start_line INT,
    end_line INT,
    verbatim_text TEXT,
    contextualized_text TEXT,
    metadata JSONB,
    effective_date DATE,
    expiration_date DATE,
    full_count BIGINT
) AS $$
BEGIN
    IF query_pattern IS NULL OR trim(query_pattern) = '' THEN
        RAISE EXCEPTION 'query_pattern cannot be empty';
    END IF;
    IF is_regex IS NULL THEN
        RAISE EXCEPTION 'is_regex cannot be null';
    END IF;
    IF match_limit IS NULL OR match_limit <= 0 THEN
        RAISE EXCEPTION 'match_limit must be a positive integer';
    END IF;
    IF t_violation IS NULL THEN
        RAISE EXCEPTION 't_violation cannot be null';
    END IF;

    RETURN QUERY
    SELECT
        c.id AS chunk_id,
        d.doc_code,
        d.title AS doc_title,
        c.path::text AS path,
        c.start_line,
        c.end_line,
        c.verbatim_text,
        c.contextualized_text,
        c.metadata,
        c.effective_date,
        c.expiration_date,
        COUNT(*) OVER()::BIGINT AS full_count
    FROM chunks c
    JOIN documents d ON c.document_id = d.id
    WHERE c.effective_date <= t_violation
      AND (c.expiration_date IS NULL OR c.expiration_date > t_violation)
      AND (target_documents IS NULL OR cardinality(target_documents) = 0 OR d.doc_code = ANY(target_documents))
      AND (path_prefix IS NULL OR c.path <@ path_prefix)
      AND chunk_matches_pattern(c.contextualized_text, query_pattern, is_regex)
    ORDER BY d.doc_code, c.start_line, c.path
    LIMIT match_limit;
END;
$$ LANGUAGE plpgsql STABLE;
