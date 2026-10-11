-- src/rag_eval/legal/db/sql/014_ingest_and_curation.sql
-- Ingest ghi thẳng vào DB, agent tự chỉnh cạnh trên DB: bỏ lớp staging.

-- 1. Bảng dấu vết viện dẫn của staging không còn ai đọc
DROP TABLE IF EXISTS chunk_context_refs;

-- 2. Cạnh mang nguồn gốc (INGEST do code sinh, AGENT do agent thêm) và bắt buộc có căn cứ chữ
DELETE FROM graph_edges;
ALTER TABLE graph_edges ALTER COLUMN citation_text SET NOT NULL;
ALTER TABLE graph_edges ADD COLUMN origin VARCHAR(16) NOT NULL
    CONSTRAINT chk_graph_edges_origin CHECK (origin IN ('INGEST', 'AGENT'));
ALTER TABLE graph_edges DROP CONSTRAINT graph_edges_target_chunk_id_fkey;
ALTER TABLE graph_edges ADD CONSTRAINT graph_edges_target_chunk_id_fkey
    FOREIGN KEY (target_chunk_id) REFERENCES chunks(id) ON DELETE CASCADE;
CREATE INDEX idx_graph_edges_origin ON graph_edges(origin);

-- 3. Nhật ký mọi thay đổi cạnh của agent, khóa theo path vì chunk có thể biến mất khi nạp lại
CREATE TABLE graph_edge_log (
    id UUID PRIMARY KEY,
    action VARCHAR(16) NOT NULL CHECK (action IN ('ADDED', 'REMOVED', 'INVALIDATED')),
    source_path LTREE NOT NULL,
    target_path LTREE NOT NULL,
    relation_type VARCHAR(32) NOT NULL REFERENCES relation_types(code),
    citation_text TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_graph_edge_log_source ON graph_edge_log USING gist(source_path);

-- 4. Bỏ finalization_state: xóa các hàm dùng nó trước, rồi tới cột.
-- Xóa theo tên vì bản hybrid_search còn lại phụ thuộc vào thứ tự đã áp 008_bm25_sparse
-- (áp trước 010 trên DB mới: còn bản 9 tham số; áp sau 013: còn bản 6 tham số).
DROP FUNCTION hybrid_search;
DROP FUNCTION verbatim_grep;
DROP FUNCTION verbatim_grep_count;
ALTER TABLE chunks DROP CONSTRAINT chk_chunks_finalization_state;
DROP INDEX IF EXISTS idx_chunks_finalization_state;
ALTER TABLE chunks DROP COLUMN finalization_state;

-- hybrid_search (8 tham số, ZERO DEFAULT)
CREATE FUNCTION hybrid_search(
    query_text TEXT,
    query_vector VECTOR(512),
    t_violation DATE,
    match_limit INT,
    rrf_k INT,
    doc_codes TEXT[],
    path_prefix LTREE,
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

-- verbatim_grep (7 tham số, ZERO DEFAULT)
CREATE FUNCTION verbatim_grep(
    query_pattern TEXT,
    target_documents TEXT[],
    path_prefix LTREE,
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
        ORDER BY similarity_score DESC
        LIMIT match_limit;
    END IF;
END;
$$ LANGUAGE plpgsql STABLE;
