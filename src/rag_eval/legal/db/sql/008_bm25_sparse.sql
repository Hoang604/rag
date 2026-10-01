ALTER TABLE chunks ADD COLUMN IF NOT EXISTS term_count INT NOT NULL DEFAULT 0;

CREATE OR REPLACE FUNCTION legal_syllables(txt TEXT)
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

CREATE OR REPLACE FUNCTION legal_terms(txt TEXT)
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

CREATE TABLE IF NOT EXISTS chunk_terms (
    term TEXT NOT NULL,
    chunk_id UUID NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    tf INT NOT NULL,
    PRIMARY KEY (term, chunk_id)
);

CREATE INDEX IF NOT EXISTS idx_chunk_terms_chunk ON chunk_terms (chunk_id);

CREATE OR REPLACE FUNCTION count_chunk_terms()
RETURNS TRIGGER AS $$
BEGIN
    NEW.term_count := COALESCE((SELECT sum(tf) FROM legal_terms(NEW.contextualized_text)), 0);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION index_chunk_terms()
RETURNS TRIGGER AS $$
BEGIN
    DELETE FROM chunk_terms WHERE chunk_id = NEW.id;
    INSERT INTO chunk_terms (term, chunk_id, tf)
    SELECT t.term, NEW.id, t.tf FROM legal_terms(NEW.contextualized_text) t;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_chunks_term_count ON chunks;
CREATE TRIGGER trg_chunks_term_count
BEFORE INSERT OR UPDATE OF contextualized_text ON chunks
FOR EACH ROW EXECUTE FUNCTION count_chunk_terms();

DROP TRIGGER IF EXISTS trg_chunks_terms ON chunks;
CREATE TRIGGER trg_chunks_terms
AFTER INSERT OR UPDATE OF contextualized_text ON chunks
FOR EACH ROW EXECUTE FUNCTION index_chunk_terms();

INSERT INTO chunk_terms (term, chunk_id, tf)
SELECT t.term, c.id, t.tf FROM chunks c, legal_terms(c.contextualized_text) t
ON CONFLICT DO NOTHING;

UPDATE chunks c SET term_count = s.n
FROM (SELECT chunk_id, sum(tf) AS n FROM chunk_terms GROUP BY chunk_id) s
WHERE s.chunk_id = c.id;

ANALYZE chunk_terms;

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
    k1 CONSTANT DOUBLE PRECISION := 1.2;
    b CONSTANT DOUBLE PRECISION := 0.75;
    candidate_limit INT := GREATEST(match_limit * 6, 120);
    query_terms TEXT[];
    corpus_size DOUBLE PRECISION;
    mean_length DOUBLE PRECISION;
    scope_ids UUID[];
BEGIN
    IF doc_codes IS NOT NULL AND cardinality(doc_codes) > 0 THEN
        SELECT array_agg(id) INTO scope_ids
        FROM documents WHERE documents.doc_code = ANY(doc_codes);
        IF scope_ids IS NULL THEN
            RETURN;
        END IF;
    END IF;

    SELECT array_agg(t.term) INTO query_terms FROM legal_terms(query_text) t;
    SELECT count(*), GREATEST(avg(term_count), 1) INTO corpus_size, mean_length FROM chunks;

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
        ORDER BY (c.embedding <=> query_vector) ASC
        LIMIT candidate_limit
    ),
    term_weights AS (
        SELECT
            ct.term,
            ln(1.0 + (corpus_size - count(*) + 0.5) / (count(*) + 0.5)) AS idf
        FROM chunk_terms ct
        WHERE ct.term = ANY(query_terms)
        GROUP BY ct.term
    ),
    sparse_scored AS (
        SELECT
            ct.chunk_id AS id,
            sum(
                w.idf * ct.tf * (k1 + 1.0)
                / (ct.tf + k1 * (1.0 - b + b * c.term_count / mean_length))
            ) AS bm25
        FROM chunk_terms ct
        JOIN term_weights w ON w.term = ct.term
        JOIN chunks c ON c.id = ct.chunk_id
        WHERE ct.term = ANY(query_terms)
          AND c.effective_date <= t_violation
          AND (c.expiration_date IS NULL OR c.expiration_date > t_violation)
          AND (scope_ids IS NULL OR c.document_id = ANY(scope_ids))
        GROUP BY ct.chunk_id
        ORDER BY bm25 DESC
        LIMIT candidate_limit
    ),
    sparse_search AS (
        SELECT
            sc.id,
            ROW_NUMBER() OVER (ORDER BY sc.bm25 DESC) AS rank_sparse
        FROM sparse_scored sc
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
        (COALESCE(1.0 / (rrf_k + d_s.rank_dense), 0.0)
         + COALESCE(1.0 / (rrf_k + s.rank_sparse), 0.0))::DOUBLE PRECISION AS rrf_score,
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
