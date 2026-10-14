CREATE FUNCTION legal_syllables(txt TEXT)
RETURNS TEXT[] AS $$
    SELECT COALESCE(
        array_remove(
            regexp_split_to_array(
                lower(unaccent('unaccent', unglue_footnote_markers(txt))),
                '[^0-9a-z]+'
            ),
            ''
        ),
        '{}'
    );
$$ LANGUAGE sql IMMUTABLE;

CREATE FUNCTION legal_terms(txt TEXT)
RETURNS TABLE (term TEXT, tf INT) AS $$
    WITH s AS (SELECT legal_syllables(txt) AS a)
    SELECT t, count(*)::INT
    FROM (
        SELECT unnest(s.a) AS t FROM s
        UNION ALL
        SELECT s.a[i] || '_' || s.a[i + 1]
        FROM s, generate_subscripts(s.a, 1) AS i
        WHERE i < cardinality(s.a)
    ) grams
    GROUP BY t;
$$ LANGUAGE sql IMMUTABLE;

ALTER TABLE chunks ADD COLUMN syllable_count INT;
UPDATE chunks SET syllable_count = cardinality(legal_syllables(contextualized_text));
ALTER TABLE chunks ALTER COLUMN syllable_count SET NOT NULL;

CREATE TABLE chunk_terms (
    term TEXT NOT NULL,
    chunk_id UUID NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    tf INT NOT NULL CHECK (tf > 0),
    syllable_count INT NOT NULL,
    PRIMARY KEY (term, chunk_id) INCLUDE (tf, syllable_count)
);

CREATE INDEX idx_chunk_terms_chunk ON chunk_terms (chunk_id);

CREATE FUNCTION count_chunk_syllables()
RETURNS TRIGGER AS $$
BEGIN
    NEW.syllable_count := cardinality(legal_syllables(NEW.contextualized_text));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE FUNCTION index_chunk_terms()
RETURNS TRIGGER AS $$
BEGIN
    DELETE FROM chunk_terms WHERE chunk_id = NEW.id;
    INSERT INTO chunk_terms (term, chunk_id, tf, syllable_count)
    SELECT t.term, NEW.id, t.tf, NEW.syllable_count FROM legal_terms(NEW.contextualized_text) t;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_chunks_syllable_count
BEFORE INSERT OR UPDATE OF contextualized_text ON chunks
FOR EACH ROW EXECUTE FUNCTION count_chunk_syllables();

CREATE TRIGGER trg_chunks_terms
AFTER INSERT OR UPDATE OF contextualized_text ON chunks
FOR EACH ROW EXECUTE FUNCTION index_chunk_terms();

INSERT INTO chunk_terms (term, chunk_id, tf, syllable_count)
SELECT t.term, c.id, t.tf, c.syllable_count FROM chunks c, legal_terms(c.contextualized_text) t;

ANALYZE chunk_terms;

DROP TRIGGER trg_chunks_tsv_update ON chunks;
DROP FUNCTION update_chunks_tsv();
DROP INDEX idx_chunks_tsv;
ALTER TABLE chunks DROP COLUMN tsv_content;
DROP TEXT SEARCH CONFIGURATION vietnamese_legal;

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
    dense_similarity DOUBLE PRECISION,
    phrase_matched BOOLEAN
) AS $$
DECLARE
    k1 CONSTANT DOUBLE PRECISION := 1.2;
    b CONSTANT DOUBLE PRECISION := 0.75;
    candidate_limit INT;
    query_terms TEXT[];
    query_has_bigram BOOLEAN;
    corpus_size DOUBLE PRECISION;
    mean_length DOUBLE PRECISION;
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

    candidate_limit := GREATEST(match_limit * 6, 120);

    IF doc_codes IS NOT NULL AND cardinality(doc_codes) > 0 THEN
        SELECT array_agg(id) INTO scope_ids
        FROM documents WHERE documents.doc_code = ANY(doc_codes);
        IF scope_ids IS NULL THEN
            RETURN;
        END IF;
    END IF;

    SELECT COALESCE(array_agg(t.term), '{}') INTO query_terms FROM legal_terms(COALESCE(query_text, '')) t;
    query_has_bigram := EXISTS (SELECT 1 FROM unnest(query_terms) q WHERE strpos(q, '_') > 0);
    SELECT count(*), GREATEST(avg(c.syllable_count), 1) INTO corpus_size, mean_length FROM chunks c;

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
    term_weights AS (
        SELECT
            ct.term,
            ln(1.0 + (corpus_size - count(*) + 0.5) / (count(*) + 0.5)) AS idf,
            strpos(ct.term, '_') > 0 AS is_bigram
        FROM chunk_terms ct
        WHERE ct.term = ANY(query_terms)
        GROUP BY ct.term
    ),
    term_scores AS (
        SELECT
            ct.chunk_id AS id,
            sum(
                w.idf * ct.tf * (k1 + 1.0)
                / (ct.tf + k1 * (1.0 - b + b * ct.syllable_count / mean_length))
            ) AS bm25,
            bool_or(w.is_bigram) OR NOT query_has_bigram AS on_phrase
        FROM chunk_terms ct
        JOIN term_weights w ON w.term = ct.term
        WHERE ct.term = ANY(query_terms)
        GROUP BY ct.chunk_id
    ),
    sparse_scored AS (
        SELECT ts.id, ts.bm25, ts.on_phrase
        FROM term_scores ts
        JOIN chunks c ON c.id = ts.id
        WHERE c.effective_date <= t_violation
          AND (c.expiration_date IS NULL OR c.expiration_date > t_violation)
          AND (scope_ids IS NULL OR c.document_id = ANY(scope_ids))
          AND (path_prefix IS NULL OR c.path <@ path_prefix)
        ORDER BY ts.bm25 DESC
        LIMIT candidate_limit
    ),
    sparse_search AS (
        SELECT
            sc.id,
            sc.on_phrase,
            ROW_NUMBER() OVER (ORDER BY sc.bm25 DESC) AS rank_sparse
        FROM sparse_scored sc
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
        (COALESCE(1.0 / (rrf_k + d_s.rank_dense), 0.0)
         + COALESCE(1.0 / (rrf_k + s.rank_sparse), 0.0))::DOUBLE PRECISION AS rrf_score,
        COALESCE(d_s.rank_dense, 999)::BIGINT AS dense_rank,
        COALESCE(s.rank_sparse, 999)::BIGINT AS sparse_rank,
        COALESCE(d_s.similarity, 0.0)::DOUBLE PRECISION AS dense_similarity,
        COALESCE(s.on_phrase, FALSE) AS phrase_matched
    FROM dense_search d_s
    FULL OUTER JOIN sparse_search s ON d_s.id = s.id
    JOIN chunks c ON c.id = COALESCE(d_s.id, s.id)
    JOIN documents d ON c.document_id = d.id
    ORDER BY rrf_score DESC, c.path
    LIMIT match_limit;
END;
$$ LANGUAGE plpgsql STABLE;

CREATE FUNCTION verbatim_grep(
    query_pattern TEXT,
    target_documents TEXT[],
    path_prefix LTREE,
    is_regex BOOLEAN,
    t_violation DATE,
    match_limit INT,
    query_vector VECTOR(512)
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
    ORDER BY
        CASE WHEN query_vector IS NULL OR c.embedding IS NULL THEN NULL ELSE c.embedding <=> query_vector END ASC NULLS LAST,
        d.doc_code, c.start_line, c.path
    LIMIT match_limit;
END;
$$ LANGUAGE plpgsql STABLE;
