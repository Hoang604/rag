-- src/rag_eval/legal/db/sql/010_statutory_stored_procs_v2.sql

-- Tạo traverse_knowledge_graph v2 (4 tham số, ZERO DEFAULT)
CREATE OR REPLACE FUNCTION traverse_knowledge_graph(
    source_id UUID,
    nav_direction TEXT,
    depth_limit INT,
    filter_relations VARCHAR(32)[]
)
RETURNS TABLE (
    id UUID,
    source_chunk_id UUID,
    target_chunk_id UUID,
    relation_type VARCHAR(32),
    citation_text TEXT,
    depth INT,
    target_path TEXT,
    target_text TEXT
) AS $$
BEGIN
    IF source_id IS NULL THEN
        RAISE EXCEPTION 'source_id cannot be null';
    END IF;
    IF depth_limit IS NULL OR depth_limit <= 0 THEN
        RAISE EXCEPTION 'depth_limit must be a positive integer';
    END IF;
    IF nav_direction NOT IN ('OUTGOING', 'INCOMING', 'BOTH') THEN
        RAISE EXCEPTION 'Invalid nav_direction: %. Must be OUTGOING, INCOMING, or BOTH', nav_direction;
    END IF;

    RETURN QUERY
    WITH RECURSIVE graph_walk AS (
        SELECT 
            ge.id,
            CASE WHEN ge.source_chunk_id = source_id THEN ge.source_chunk_id ELSE ge.target_chunk_id END AS step_from_id,
            CASE WHEN ge.source_chunk_id = source_id THEN ge.target_chunk_id ELSE ge.source_chunk_id END AS step_to_id,
            ge.relation_type,
            ge.citation_text,
            1 AS depth,
            ARRAY[source_id, CASE WHEN ge.source_chunk_id = source_id THEN ge.target_chunk_id ELSE ge.source_chunk_id END] AS visited_nodes
        FROM graph_edges ge
        JOIN relation_types rt ON ge.relation_type = rt.code
        WHERE ge.target_chunk_id IS NOT NULL
          AND (filter_relations IS NULL OR cardinality(filter_relations) = 0 OR ge.relation_type = ANY(filter_relations))
          AND (
            (ge.source_chunk_id = source_id AND (nav_direction IN ('OUTGOING', 'BOTH') OR rt.is_symmetric = TRUE))
            OR
            (ge.target_chunk_id = source_id AND (nav_direction IN ('INCOMING', 'BOTH') OR rt.is_symmetric = TRUE))
          )

        UNION ALL

        SELECT 
            ge.id,
            gw.step_to_id AS step_from_id,
            CASE WHEN ge.source_chunk_id = gw.step_to_id THEN ge.target_chunk_id ELSE ge.source_chunk_id END AS step_to_id,
            ge.relation_type,
            ge.citation_text,
            gw.depth + 1 AS depth,
            gw.visited_nodes || CASE WHEN ge.source_chunk_id = gw.step_to_id THEN ge.target_chunk_id ELSE ge.source_chunk_id END AS visited_nodes
        FROM graph_edges ge
        JOIN relation_types rt ON ge.relation_type = rt.code
        JOIN graph_walk gw ON (
            (ge.source_chunk_id = gw.step_to_id AND (nav_direction IN ('OUTGOING', 'BOTH') OR rt.is_symmetric = TRUE))
            OR
            (ge.target_chunk_id = gw.step_to_id AND (nav_direction IN ('INCOMING', 'BOTH') OR rt.is_symmetric = TRUE))
        )
        WHERE gw.depth < depth_limit
          AND ge.target_chunk_id IS NOT NULL
          AND (filter_relations IS NULL OR cardinality(filter_relations) = 0 OR ge.relation_type = ANY(filter_relations))
          AND CASE 
                WHEN ge.source_chunk_id = gw.step_to_id THEN ge.target_chunk_id 
                ELSE ge.source_chunk_id 
              END != ALL(gw.visited_nodes)
    ),
    deduplicated AS (
        SELECT DISTINCT ON (gw.id, gw.step_from_id, gw.step_to_id)
            gw.id,
            gw.step_from_id AS source_chunk_id,
            gw.step_to_id AS target_chunk_id,
            gw.relation_type,
            gw.citation_text,
            gw.depth
        FROM graph_walk gw
        ORDER BY gw.id, gw.step_from_id, gw.step_to_id, gw.depth ASC
    )
    SELECT
        d.id,
        d.source_chunk_id,
        d.target_chunk_id,
        d.relation_type,
        d.citation_text,
        d.depth,
        c.path::text AS target_path,
        c.verbatim_text AS target_text
    FROM deduplicated d
    JOIN chunks c ON d.target_chunk_id = c.id
    ORDER BY d.depth ASC, d.relation_type ASC;
END;
$$ LANGUAGE plpgsql STABLE;

-- Tạo hybrid_search v2 (9 tham số, ZERO DEFAULT)
CREATE OR REPLACE FUNCTION hybrid_search(
    query_text TEXT,
    query_vector VECTOR(512),
    t_violation DATE,
    match_limit INT,
    rrf_k INT,
    doc_codes TEXT[],
    path_prefix LTREE,
    only_resolved BOOLEAN,
    ts_config TEXT
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
    finalization_state VARCHAR,
    rrf_score DOUBLE PRECISION,
    dense_rank BIGINT,
    sparse_rank BIGINT,
    dense_similarity DOUBLE PRECISION
) AS $$
DECLARE
    clean_query TEXT := trim(COALESCE(query_text, ''));
    resolved_config regconfig;
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
    IF ts_config IS NULL OR trim(ts_config) = '' THEN
        RAISE EXCEPTION 'ts_config cannot be null or empty';
    END IF;

    resolved_config := ts_config::regconfig;
    ts_query := CASE WHEN clean_query != '' THEN plainto_tsquery(resolved_config, clean_query) ELSE NULL END;
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
          AND (only_resolved IS NULL OR NOT only_resolved OR c.finalization_state LIKE 'FINALIZED_%')
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
          AND (only_resolved IS NULL OR NOT only_resolved OR c.finalization_state LIKE 'FINALIZED_%')
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
        c.finalization_state,
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

-- Tạo verbatim_grep v2 (8 tham số, ZERO DEFAULT)
CREATE OR REPLACE FUNCTION verbatim_grep(
    query_pattern TEXT,
    target_documents TEXT[],
    path_prefix LTREE,
    only_resolved BOOLEAN,
    is_regex BOOLEAN,
    case_sensitive BOOLEAN,
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
    finalization_state VARCHAR,
    similarity_score FLOAT,
    full_count BIGINT
) AS $$
DECLARE
    clean_pattern TEXT := trim(query_pattern);
BEGIN
    IF clean_pattern IS NULL OR clean_pattern = '' THEN
        RETURN;
    END IF;
    IF match_limit IS NULL OR match_limit <= 0 THEN
        RAISE EXCEPTION 'match_limit must be a positive integer';
    END IF;
    IF t_violation IS NULL THEN
        RAISE EXCEPTION 't_violation cannot be null';
    END IF;

    IF is_regex THEN
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
            c.finalization_state,
            GREATEST(
                word_similarity(clean_pattern, c.verbatim_text),
                word_similarity(clean_pattern, c.contextualized_text)
            )::FLOAT AS similarity_score,
            COUNT(*) OVER()::BIGINT AS full_count
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE c.effective_date <= t_violation
          AND (c.expiration_date IS NULL OR c.expiration_date > t_violation)
          AND (
              (case_sensitive AND (c.verbatim_text ~ clean_pattern OR c.contextualized_text ~ clean_pattern))
              OR (NOT case_sensitive AND (c.verbatim_text ~* clean_pattern OR c.contextualized_text ~* clean_pattern))
          )
          AND (target_documents IS NULL OR cardinality(target_documents) = 0 OR d.doc_code = ANY(target_documents))
          AND (path_prefix IS NULL OR c.path <@ path_prefix)
          AND (only_resolved IS NULL OR NOT only_resolved OR c.finalization_state LIKE 'FINALIZED_%')
        ORDER BY similarity_score DESC
        LIMIT match_limit;
    ELSE
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
            c.finalization_state,
            GREATEST(
                word_similarity(clean_pattern, c.verbatim_text),
                word_similarity(clean_pattern, c.contextualized_text)
            )::FLOAT AS similarity_score,
            COUNT(*) OVER()::BIGINT AS full_count
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
          AND (target_documents IS NULL OR cardinality(target_documents) = 0 OR d.doc_code = ANY(target_documents))
          AND (path_prefix IS NULL OR c.path <@ path_prefix)
          AND (only_resolved IS NULL OR NOT only_resolved OR c.finalization_state LIKE 'FINALIZED_%')
        ORDER BY similarity_score DESC
        LIMIT match_limit;
    END IF;
END;
$$ LANGUAGE plpgsql STABLE;

CREATE OR REPLACE FUNCTION verbatim_grep_count(
    query_pattern TEXT,
    target_documents TEXT[],
    path_prefix LTREE,
    only_resolved BOOLEAN,
    is_regex BOOLEAN,
    case_sensitive BOOLEAN,
    t_violation DATE
)
RETURNS BIGINT AS $$
DECLARE
    clean_pattern TEXT := trim(query_pattern);
    total BIGINT;
BEGIN
    IF clean_pattern IS NULL OR clean_pattern = '' THEN
        RETURN 0;
    END IF;
    IF t_violation IS NULL THEN
        RAISE EXCEPTION 't_violation cannot be null';
    END IF;

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
      AND (target_documents IS NULL OR cardinality(target_documents) = 0 OR d.doc_code = ANY(target_documents))
      AND (path_prefix IS NULL OR c.path <@ path_prefix)
      AND (only_resolved IS NULL OR NOT only_resolved OR c.finalization_state LIKE 'FINALIZED_%');

    RETURN COALESCE(total, 0);
END;
$$ LANGUAGE plpgsql STABLE;
