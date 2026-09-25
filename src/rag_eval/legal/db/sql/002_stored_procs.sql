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

CREATE OR REPLACE FUNCTION traverse_knowledge_graph(
    source_id UUID,
    nav_direction TEXT DEFAULT 'OUTGOING',
    depth_limit INT DEFAULT 2
)
RETURNS TABLE (
    id UUID,
    source_chunk_id UUID,
    target_chunk_id UUID,
    target_external_ref TEXT,
    relation_type VARCHAR(64),
    citation_text TEXT,
    depth INT,
    target_path TEXT,
    target_text TEXT
) AS $$
BEGIN
    IF nav_direction = 'OUTGOING' THEN
        RETURN QUERY
        WITH RECURSIVE graph_walk AS (
            SELECT 
                ge.id,
                ge.source_chunk_id,
                ge.target_chunk_id,
                ge.target_external_ref,
                ge.relation_type,
                ge.citation_text,
                1 AS depth,
                c.path::text AS target_path,
                c.verbatim_text AS target_text
            FROM graph_edges ge
            LEFT JOIN chunks c ON ge.target_chunk_id = c.id
            WHERE ge.source_chunk_id = source_id

            UNION ALL

            SELECT 
                ge.id,
                ge.source_chunk_id,
                ge.target_chunk_id,
                ge.target_external_ref,
                ge.relation_type,
                ge.citation_text,
                gw.depth + 1 AS depth,
                c.path::text AS target_path,
                c.verbatim_text AS target_text
            FROM graph_edges ge
            JOIN graph_walk gw ON ge.source_chunk_id = gw.target_chunk_id
            LEFT JOIN chunks c ON ge.target_chunk_id = c.id
            WHERE gw.depth < depth_limit AND ge.target_chunk_id IS NOT NULL
        )
        SELECT DISTINCT ON (gw.id, gw.depth) * FROM graph_walk gw
        ORDER BY gw.id, gw.depth, gw.depth ASC;
    ELSE
        RETURN QUERY
        WITH RECURSIVE graph_walk AS (
            SELECT 
                ge.id,
                ge.source_chunk_id,
                ge.target_chunk_id,
                ge.target_external_ref,
                ge.relation_type,
                ge.citation_text,
                1 AS depth,
                c.path::text AS target_path,
                c.verbatim_text AS target_text
            FROM graph_edges ge
            LEFT JOIN chunks c ON ge.source_chunk_id = c.id
            WHERE ge.target_chunk_id = source_id

            UNION ALL

            SELECT 
                ge.id,
                ge.source_chunk_id,
                ge.target_chunk_id,
                ge.target_external_ref,
                ge.relation_type,
                ge.citation_text,
                gw.depth + 1 AS depth,
                c.path::text AS target_path,
                c.verbatim_text AS target_text
            FROM graph_edges ge
            JOIN graph_walk gw ON ge.target_chunk_id = gw.source_chunk_id
            LEFT JOIN chunks c ON ge.source_chunk_id = c.id
            WHERE gw.depth < depth_limit
        )
        SELECT DISTINCT ON (gw.id, gw.depth) * FROM graph_walk gw
        ORDER BY gw.id, gw.depth, gw.depth ASC;
    END IF;
END;
$$ LANGUAGE plpgsql STABLE;
