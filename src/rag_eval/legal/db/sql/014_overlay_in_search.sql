-- ----------------------------------------------------------------------------
-- APPLY THE LEARNED OVERLAY, WHEN A CALLER ASKS FOR IT
--
-- One new parameter: the topic key of the incoming question, or NULL. NULL is
-- the default and means the overlay contributes nothing, so every existing
-- caller keeps the behaviour it had and the feature ships switched off.
--
-- The boost is a multiplier bounded at 1.10, below the vehicle facet's 1.12.
-- That ordering is deliberate and is the whole safety argument: a facet reads
-- what the statute says about itself, an annotation reports what one agent
-- once believed about one question. Feedback may reorder provisions that
-- retrieval already found comparable; it may not overturn what the text says.
--
-- Only the activated build is consulted, so an evaluation can name the overlay
-- state it ran against, and switching the overlay off is one UPDATE.
-- ----------------------------------------------------------------------------

DROP FUNCTION IF EXISTS hybrid_search(TEXT, VECTOR(384), DATE, INT, INT, TEXT, TEXT, TEXT[], DOUBLE PRECISION);
DROP FUNCTION IF EXISTS hybrid_search(TEXT, VECTOR(384), DATE, INT, INT, TEXT, TEXT, TEXT[], DOUBLE PRECISION, TEXT);

CREATE OR REPLACE FUNCTION hybrid_search(
    query_text TEXT,
    query_vector VECTOR(384),
    t_violation DATE DEFAULT CURRENT_DATE,
    match_limit INT DEFAULT 10,
    rrf_k INT DEFAULT 60,
    vehicle_class TEXT DEFAULT NULL,
    provision_role TEXT DEFAULT NULL,
    phrase_variants TEXT[] DEFAULT NULL,
    dense_weight DOUBLE PRECISION DEFAULT 1.0,
    overlay_topic TEXT DEFAULT NULL
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
    ts_phrase TSQUERY;
    ts_query TSQUERY := CASE WHEN clean_query != '' THEN plainto_tsquery('vietnamese_legal', clean_query) ELSE NULL END;
    lexemes TEXT[];
    ts_any TSQUERY;
    candidate_limit INT := GREATEST(match_limit * 6, 120);
    class_penalty DOUBLE PRECISION := 0.35;
    class_bonus DOUBLE PRECISION := 1.12;
    role_penalty DOUBLE PRECISION := 0.55;
    role_bonus DOUBLE PRECISION := 1.15;
    phrase_bonus DOUBLE PRECISION := 1.20;
    active_overlay INT;
BEGIN
    IF overlay_topic IS NOT NULL THEN
        SELECT build_version INTO active_overlay FROM overlay_active WHERE id;
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

    SELECT string_agg(format('(%s)', phraseto_tsquery('vietnamese_legal', v)::text), ' | ')::tsquery
    INTO ts_phrase
    FROM unnest(COALESCE(phrase_variants, ARRAY[clean_query])) AS v
    WHERE trim(v) != '' AND phraseto_tsquery('vietnamese_legal', v)::text != '';

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
        ORDER BY (c.embedding <=> query_vector) ASC
        LIMIT candidate_limit
    ),
    sparse_pool AS (
        SELECT
            c.id,
            c.tsv_content,
            COALESCE(ts_rank(c.tsv_content, ts_any, 32), 0.0) AS base_score,
            (ts_phrase IS NOT NULL AND c.tsv_content @@ ts_phrase) AS is_phrase
        FROM chunks c
        WHERE (
                (ts_any IS NOT NULL AND c.tsv_content @@ ts_any)
                OR (ts_phrase IS NOT NULL AND c.tsv_content @@ ts_phrase)
              )
          AND c.effective_date <= t_violation
          AND (c.expiration_date IS NULL OR c.expiration_date > t_violation)
        ORDER BY is_phrase DESC, base_score DESC
        LIMIT candidate_limit * 2
    ),
    sparse_search AS (
        SELECT
            p.id,
            p.is_phrase,
            ROW_NUMBER() OVER (
                ORDER BY (
                    p.base_score * 4.0
                    + CASE WHEN p.is_phrase THEN 4.0 ELSE 0.0 END
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
        ((COALESCE(dense_weight / (rrf_k + d_s.rank_dense), 0.0) +
          COALESCE(1.0 / (rrf_k + s.rank_sparse), 0.0))
         * CASE
             WHEN vehicle_class IS NULL THEN 1.0
             WHEN c.metadata->'vehicle_classes' IS NULL THEN 1.0
             WHEN c.metadata->'vehicle_classes' ? vehicle_class THEN class_bonus
             ELSE class_penalty
           END
         * CASE
             WHEN provision_role IS NULL THEN 1.0
             WHEN c.metadata->>'provision_role' IS NULL THEN 1.0
             WHEN c.metadata->>'provision_role' = provision_role THEN role_bonus
             ELSE role_penalty
           END
         * CASE WHEN COALESCE(s.is_phrase, FALSE) THEN phrase_bonus ELSE 1.0 END
         * (1.0 + COALESCE(o.weight, 0.0))
        )::DOUBLE PRECISION AS rrf_score,
        COALESCE(d_s.rank_dense, 999)::BIGINT AS dense_rank,
        COALESCE(s.rank_sparse, 999)::BIGINT AS sparse_rank,
        COALESCE(d_s.similarity, 0.0)::DOUBLE PRECISION AS dense_similarity
    FROM dense_search d_s
    FULL OUTER JOIN sparse_search s ON d_s.id = s.id
    JOIN chunks c ON c.id = COALESCE(d_s.id, s.id)
    JOIN documents d ON c.document_id = d.id
    LEFT JOIN overlay_weights o
           ON active_overlay IS NOT NULL
          AND o.build_version = active_overlay
          AND o.topic_fingerprint = overlay_topic
          AND o.chunk_id = c.id
    ORDER BY rrf_score DESC
    LIMIT match_limit;
END;
$$ LANGUAGE plpgsql STABLE;
