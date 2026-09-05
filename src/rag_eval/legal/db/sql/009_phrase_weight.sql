-- ----------------------------------------------------------------------------
-- A LITERAL STATUTORY PHRASE OUTWEIGHS A NEIGHBOUR POSITION
--
-- With phrase matches admitted to the pool, "xe máy vượt đèn đỏ" ranks its
-- answer 1st on the sparse side -- and still lost, because the dense side put
-- a clause about red markers on protruding cargo 1st and the answer 20th. The
-- embedding is reading "vượt" and "đỏ" as the query; it is wrong, and no
-- reranking of its own output can tell.
--
-- Containing the exact statutory wording is evidence of a different kind from
-- being close in vector space, so it is scored as such: a multiplier on the
-- fused score, the same soft mechanism the facets use.
-- ----------------------------------------------------------------------------

DROP FUNCTION IF EXISTS hybrid_search(TEXT, VECTOR(384), DATE, INT, INT, TEXT, TEXT, TEXT[]);

CREATE OR REPLACE FUNCTION hybrid_search(
    query_text TEXT,
    query_vector VECTOR(384),
    t_violation DATE DEFAULT CURRENT_DATE,
    match_limit INT DEFAULT 10,
    rrf_k INT DEFAULT 60,
    vehicle_class TEXT DEFAULT NULL,
    provision_role TEXT DEFAULT NULL,
    phrase_variants TEXT[] DEFAULT NULL
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
    ts_phrase TSQUERY;
    ts_query TSQUERY := CASE WHEN clean_query != '' THEN plainto_tsquery('vietnamese_legal', clean_query) ELSE NULL END;
    lexemes TEXT[];
    ts_any TSQUERY;
    candidate_limit INT := GREATEST(match_limit * 6, 120);
    -- 0.35 sinks a wrong-class chunk from rank 1 (1/61) below a right-class one
    -- at rank 40 (1/100); 1.12 lifts a right-class chunk over a class-less
    -- neighbour without displacing an exact quotation.
    class_penalty DOUBLE PRECISION := 0.35;
    class_bonus DOUBLE PRECISION := 1.12;
    -- Milder than the vehicle penalty: role is inferred from a marker in
    -- the prefix, so a miss must cost less than a miss on an explicit facet.
    role_penalty DOUBLE PRECISION := 0.55;
    role_bonus DOUBLE PRECISION := 1.15;
    -- Enough to lift a phrase hit at dense rank 20 over a non-hit at rank 1,
    -- which is the gap actually observed; not enough to beat two rankers.
    phrase_bonus DOUBLE PRECISION := 1.20;
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

    SELECT string_agg(format('(%s)', phraseto_tsquery('vietnamese_legal', v)::text), ' | ')::tsquery
    INTO ts_phrase
    FROM unnest(COALESCE(phrase_variants, ARRAY[clean_query])) AS v
    WHERE trim(v) != '' AND phraseto_tsquery('vietnamese_legal', v)::text != '';

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
    -- Ranked in two stages: ts_rank over everything the pair query matches
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
            COALESCE(ts_rank(c.tsv_content, ts_any, 32), 0.0) AS base_score,
            (ts_phrase IS NOT NULL AND c.tsv_content @@ ts_phrase) AS is_phrase
        FROM chunks c
        WHERE (
                (ts_any IS NOT NULL AND c.tsv_content @@ ts_any)
                OR (ts_phrase IS NOT NULL AND c.tsv_content @@ ts_phrase)
              )
          AND c.effective_date <= t_violation
          AND (c.expiration_date IS NULL OR c.expiration_date > t_violation)
        -- Phrase hits first: they are few and they are the only exact evidence
        -- there is, so they must not be cut before the bonus is paid.
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
        ((COALESCE(1.0 / (rrf_k + d_s.rank_dense), 0.0) +
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
        )::DOUBLE PRECISION AS rrf_score,
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
