-- ============================================================================
-- STORED PROCEDURES & IN-DATABASE REASONING FUNCTIONS
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. HYBRID LEGAL SEARCH WITH RECIPROCAL RANK FUSION (RRF) & PHRASE PROXIMITY
-- ----------------------------------------------------------------------------

-- 1.1. Explicit 384-Dimensional Overload (intfloat/multilingual-e5-small / 384-dim standard)
CREATE OR REPLACE FUNCTION hybrid_legal_search_384(
    query_text TEXT,
    query_vector VECTOR(384),
    target_actor actor_category DEFAULT NULL,
    target_vehicles TEXT[] DEFAULT NULL,
    match_limit INT DEFAULT 20,
    rrf_k INT DEFAULT 60,
    t_violation DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    chunk_id UUID,
    path TEXT,
    chunk_index VARCHAR,
    contextualized_text TEXT,
    min_fine_vnd BIGINT,
    max_fine_vnd BIGINT,
    rrf_score DOUBLE PRECISION,
    dense_rank BIGINT,
    sparse_rank BIGINT
) AS $$
DECLARE
    clean_query TEXT := regexp_replace(unaccent(query_text), '[/]', ' ', 'g');
    ts_phrase TSQUERY := phraseto_tsquery('vietnamese_legal', clean_query);
    ts_query TSQUERY := plainto_tsquery('vietnamese_legal', clean_query);
    words_arr TEXT[];
    or_query_str TEXT;
    ts_or_query TSQUERY;
    candidate_limit INT := GREATEST(match_limit * 6, 150);
BEGIN
    -- Build fallback OR query from keywords (skipping words of length < 2)
    words_arr := ARRAY(
        SELECT w FROM unnest(string_to_array(regexp_replace(trim(clean_query), '[^a-zA-Z0-9_\s]', ' ', 'g'), ' ')) AS w
        WHERE length(trim(w)) >= 2
    );
    IF cardinality(words_arr) > 0 THEN
        or_query_str := array_to_string(words_arr, ' | ');
        BEGIN
            ts_or_query := to_tsquery('vietnamese_legal', or_query_str);
        EXCEPTION WHEN OTHERS THEN
            ts_or_query := NULL;
        END IF;
    END IF;

    IF ts_query IS NULL OR ts_query::text = '' THEN
        ts_query := ts_or_query;
    END IF;

    RETURN QUERY
    WITH dense_search AS (
        SELECT 
            c.id,
            ROW_NUMBER() OVER (ORDER BY c.dense_embedding_384 <=> query_vector) AS rank_dense
        FROM legal_chunks c
        WHERE c.effective_date <= t_violation
          AND (c.expiration_date IS NULL OR c.expiration_date > t_violation)
          AND c.dense_embedding_384 IS NOT NULL
        ORDER BY (c.dense_embedding_384 <=> query_vector) ASC
        LIMIT candidate_limit
    ),
    sparse_search AS (
        SELECT 
            c.id,
            ROW_NUMBER() OVER (
                ORDER BY (
                    CASE 
                        WHEN ts_phrase IS NOT NULL AND c.tsv_vi @@ ts_phrase 
                        THEN 5.0 
                        ELSE 0.0 
                    END
                    + CASE 
                        WHEN ts_query IS NOT NULL AND c.tsv_vi @@ ts_query 
                        THEN 3.0 + COALESCE(ts_rank(c.tsv_vi, ts_query, 1), 0.0) * 3.0
                        ELSE 0.0 
                    END
                    + CASE 
                        WHEN ts_or_query IS NOT NULL AND c.tsv_vi @@ ts_or_query
                        THEN COALESCE(ts_rank(c.tsv_vi, ts_or_query, 1), 0.0) * 2.0
                        ELSE 0.0
                    END
                ) DESC
            ) AS rank_sparse
        FROM legal_chunks c
        WHERE c.effective_date <= t_violation
          AND (c.expiration_date IS NULL OR c.expiration_date > t_violation)
          AND (
              (ts_phrase IS NOT NULL AND c.tsv_vi @@ ts_phrase)
              OR (ts_query IS NOT NULL AND c.tsv_vi @@ ts_query)
              OR (ts_or_query IS NOT NULL AND c.tsv_vi @@ ts_or_query)
              OR (ts_query IS NULL AND ts_or_query IS NULL)
          )
        ORDER BY rank_sparse ASC
        LIMIT candidate_limit
    )
    SELECT 
        c.id AS chunk_id,
        c.path::text AS path,
        c.chunk_index,
        c.contextualized_text,
        c.min_fine_vnd,
        c.max_fine_vnd,
        (COALESCE(1.0 / (rrf_k + d.rank_dense), 0.0) + 
         COALESCE(1.0 / (rrf_k + s.rank_sparse), 0.0))::DOUBLE PRECISION AS rrf_score,
        COALESCE(d.rank_dense, 999)::BIGINT AS dense_rank,
        COALESCE(s.rank_sparse, 999)::BIGINT AS sparse_rank
    FROM dense_search d
    FULL OUTER JOIN sparse_search s ON d.id = s.id
    JOIN legal_chunks c ON c.id = COALESCE(d.id, s.id)
    ORDER BY rrf_score DESC
    LIMIT match_limit;
END;
$$ LANGUAGE plpgsql STABLE;

-- 1.2. Explicit 1536-Dimensional Overload (OpenAI / BGE-M3)
CREATE OR REPLACE FUNCTION hybrid_legal_search_1536(
    query_text TEXT,
    query_vector VECTOR(1536),
    target_actor actor_category DEFAULT NULL,
    target_vehicles TEXT[] DEFAULT NULL,
    match_limit INT DEFAULT 20,
    rrf_k INT DEFAULT 60,
    t_violation DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    chunk_id UUID,
    path TEXT,
    chunk_index VARCHAR,
    contextualized_text TEXT,
    min_fine_vnd BIGINT,
    max_fine_vnd BIGINT,
    rrf_score DOUBLE PRECISION,
    dense_rank BIGINT,
    sparse_rank BIGINT
) AS $$
DECLARE
    clean_query TEXT := regexp_replace(unaccent(query_text), '[/]', ' ', 'g');
    ts_phrase TSQUERY := phraseto_tsquery('vietnamese_legal', clean_query);
    ts_query TSQUERY := plainto_tsquery('vietnamese_legal', clean_query);
    words_arr TEXT[];
    or_query_str TEXT;
    ts_or_query TSQUERY;
    candidate_limit INT := GREATEST(match_limit * 6, 150);
BEGIN
    words_arr := ARRAY(
        SELECT w FROM unnest(string_to_array(regexp_replace(trim(clean_query), '[^a-zA-Z0-9_\s]', ' ', 'g'), ' ')) AS w
        WHERE length(trim(w)) >= 2
    );
    IF cardinality(words_arr) > 0 THEN
        or_query_str := array_to_string(words_arr, ' | ');
        BEGIN
            ts_or_query := to_tsquery('vietnamese_legal', or_query_str);
        EXCEPTION WHEN OTHERS THEN
            ts_or_query := NULL;
        END IF;
    END IF;

    IF ts_query IS NULL OR ts_query::text = '' THEN
        ts_query := ts_or_query;
    END IF;

    RETURN QUERY
    WITH dense_search AS (
        SELECT 
            c.id,
            ROW_NUMBER() OVER (ORDER BY c.dense_embedding_1536 <=> query_vector) AS rank_dense
        FROM legal_chunks c
        WHERE c.effective_date <= t_violation
          AND (c.expiration_date IS NULL OR c.expiration_date > t_violation)
          AND c.dense_embedding_1536 IS NOT NULL
        ORDER BY (c.dense_embedding_1536 <=> query_vector) ASC
        LIMIT candidate_limit
    ),
    sparse_search AS (
        SELECT 
            c.id,
            ROW_NUMBER() OVER (
                ORDER BY (
                    CASE 
                        WHEN ts_phrase IS NOT NULL AND c.tsv_vi @@ ts_phrase 
                        THEN 5.0 
                        ELSE 0.0 
                    END
                    + CASE 
                        WHEN ts_query IS NOT NULL AND c.tsv_vi @@ ts_query 
                        THEN 3.0 + COALESCE(ts_rank(c.tsv_vi, ts_query, 1), 0.0) * 3.0
                        ELSE 0.0 
                    END
                    + CASE 
                        WHEN ts_or_query IS NOT NULL AND c.tsv_vi @@ ts_or_query
                        THEN COALESCE(ts_rank(c.tsv_vi, ts_or_query, 1), 0.0) * 2.0
                        ELSE 0.0
                    END
                ) DESC
            ) AS rank_sparse
        FROM legal_chunks c
        WHERE c.effective_date <= t_violation
          AND (c.expiration_date IS NULL OR c.expiration_date > t_violation)
          AND (
              (ts_phrase IS NOT NULL AND c.tsv_vi @@ ts_phrase)
              OR (ts_query IS NOT NULL AND c.tsv_vi @@ ts_query)
              OR (ts_or_query IS NOT NULL AND c.tsv_vi @@ ts_or_query)
              OR (ts_query IS NULL AND ts_or_query IS NULL)
          )
        ORDER BY rank_sparse ASC
        LIMIT candidate_limit
    )
    SELECT 
        c.id AS chunk_id,
        c.path::text AS path,
        c.chunk_index,
        c.contextualized_text,
        c.min_fine_vnd,
        c.max_fine_vnd,
        (COALESCE(1.0 / (rrf_k + d.rank_dense), 0.0) + 
         COALESCE(1.0 / (rrf_k + s.rank_sparse), 0.0))::DOUBLE PRECISION AS rrf_score,
        COALESCE(d.rank_dense, 999)::BIGINT AS dense_rank,
        COALESCE(s.rank_sparse, 999)::BIGINT AS sparse_rank
    FROM dense_search d
    FULL OUTER JOIN sparse_search s ON d.id = s.id
    JOIN legal_chunks c ON c.id = COALESCE(d.id, s.id)
    ORDER BY rrf_score DESC
    LIMIT match_limit;
END;
$$ LANGUAGE plpgsql STABLE;

-- 1.3. Polymorphic Overloads for hybrid_legal_search
CREATE OR REPLACE FUNCTION hybrid_legal_search(
    query_text TEXT,
    query_vector VECTOR(384),
    target_actor actor_category DEFAULT NULL,
    target_vehicles TEXT[] DEFAULT NULL,
    match_limit INT DEFAULT 20,
    rrf_k INT DEFAULT 60,
    t_violation DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    chunk_id UUID,
    path TEXT,
    chunk_index VARCHAR,
    contextualized_text TEXT,
    min_fine_vnd BIGINT,
    max_fine_vnd BIGINT,
    rrf_score DOUBLE PRECISION,
    dense_rank BIGINT,
    sparse_rank BIGINT
) AS $$
BEGIN
    RETURN QUERY SELECT * FROM hybrid_legal_search_384(
        query_text, query_vector, target_actor, target_vehicles, match_limit, rrf_k, t_violation
    );
END;
$$ LANGUAGE plpgsql STABLE;

CREATE OR REPLACE FUNCTION hybrid_legal_search(
    query_text TEXT,
    query_vector VECTOR(1536),
    target_actor actor_category DEFAULT NULL,
    target_vehicles TEXT[] DEFAULT NULL,
    match_limit INT DEFAULT 20,
    rrf_k INT DEFAULT 60,
    t_violation DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    chunk_id UUID,
    path TEXT,
    chunk_index VARCHAR,
    contextualized_text TEXT,
    min_fine_vnd BIGINT,
    max_fine_vnd BIGINT,
    rrf_score DOUBLE PRECISION,
    dense_rank BIGINT,
    sparse_rank BIGINT
) AS $$
BEGIN
    RETURN QUERY SELECT * FROM hybrid_legal_search_1536(
        query_text, query_vector, target_actor, target_vehicles, match_limit, rrf_k, t_violation
    );
END;
$$ LANGUAGE plpgsql STABLE;

-- ----------------------------------------------------------------------------
-- 2. NORMATIVE TRIAD RECURSIVE CTE TRAVERSAL
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION traverse_normative_triad(
    anchor_sign_code VARCHAR(64),
    target_vehicles TEXT[] DEFAULT ARRAY['CAR_PASSENGER'],
    max_hops INT DEFAULT 4,
    t_violation DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    hop_depth INT,
    node_role legal_norm_role,
    document_code VARCHAR,
    chunk_path TEXT,
    chunk_heading VARCHAR,
    verbatim_text TEXT,
    min_fine BIGINT,
    max_fine BIGINT,
    traversal_path TEXT
) AS $$
BEGIN
    RETURN QUERY
    WITH RECURSIVE triad_graph AS (
        SELECT 
            c.id AS chunk_id,
            c.norm_role,
            d.doc_code AS document_code,
            c.path AS chunk_path,
            c.chunk_index AS chunk_heading,
            c.verbatim_text,
            c.min_fine_vnd AS min_fine,
            c.max_fine_vnd AS max_fine,
            1 AS hop_depth,
            ARRAY[c.id] AS visited_nodes,
            ('ANCHOR: [' || s.sign_code || '] ' || s.sign_name)::TEXT AS traversal_path
        FROM sign_catalog s
        JOIN legal_chunks c ON s.chunk_id = c.id
        JOIN legal_documents d ON c.document_id = d.id
        WHERE UPPER(s.sign_code) = UPPER(anchor_sign_code)
          AND c.effective_date <= t_violation
          AND (c.expiration_date IS NULL OR c.expiration_date > t_violation)
        
        UNION ALL
        
        SELECT 
            next_chunk.id AS chunk_id,
            next_chunk.norm_role,
            next_doc.doc_code AS document_code,
            next_chunk.path AS chunk_path,
            next_chunk.chunk_index AS chunk_heading,
            next_chunk.verbatim_text,
            next_chunk.min_fine_vnd AS min_fine,
            next_chunk.max_fine_vnd AS max_fine,
            tg.hop_depth + 1 AS hop_depth,
            tg.visited_nodes || next_chunk.id AS visited_nodes,
            (tg.traversal_path || ' -> [' || e.relation_type::text || '] -> ' || next_chunk.path::text)::TEXT AS traversal_path
        FROM triad_graph tg
        JOIN legal_graph_edges e ON (e.source_chunk_id = tg.chunk_id OR e.target_chunk_id = tg.chunk_id)
        JOIN legal_chunks next_chunk ON (
            CASE 
                WHEN e.source_chunk_id = tg.chunk_id THEN e.target_chunk_id 
                ELSE e.source_chunk_id 
            END = next_chunk.id
        )
        JOIN legal_documents next_doc ON next_chunk.document_id = next_doc.id
        WHERE tg.hop_depth < max_hops
          AND NOT (next_chunk.id = ANY(tg.visited_nodes))
          AND next_chunk.effective_date <= t_violation
          AND (next_chunk.expiration_date IS NULL OR next_chunk.expiration_date > t_violation)
          AND e.relation_type IN ('DEFINES_SANCTION_FOR', 'HAS_ADDITIONAL_SANCTION', 'REFERENCES_TECHNICAL_STANDARD', 'MODIFIES_AND_REPLACES', 'GUIDES', 'DEFINES_TERM')
    )
    SELECT 
        tg.hop_depth,
        tg.norm_role AS node_role,
        tg.document_code,
        tg.chunk_path::text,
        tg.chunk_heading,
        tg.verbatim_text,
        tg.min_fine,
        tg.max_fine,
        tg.traversal_path
    FROM triad_graph tg
    ORDER BY tg.hop_depth ASC, tg.min_fine DESC NULLS LAST;
END;
$$ LANGUAGE plpgsql STABLE;

-- ----------------------------------------------------------------------------
-- 3. SCOPE OVERRIDE & STATUTORY PRECEDENCE RESOLUTION
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION resolve_scope_overrides(
    target_path_param LTREE,
    active_actor actor_category DEFAULT 'DRIVER',
    is_emergency_vehicle BOOLEAN DEFAULT FALSE,
    t_violation DATE DEFAULT CURRENT_DATE
)
RETURNS TABLE (
    rule_type TEXT,
    override_priority INT,
    source_citation TEXT,
    exception_type VARCHAR,
    condition_expression TEXT,
    verbatim_text TEXT
) AS $$
BEGIN
    RETURN QUERY
    -- 1. Check direct exception clauses linked via EXEMPTS_CONDITION or OVERRIDES_PRIORITY edges
    SELECT 
        'EXCEPTION_CLAUSE' AS rule_type,
        exc_chunk.override_priority,
        exc_chunk.chunk_index::text AS source_citation,
        exc_chunk.exception_type,
        COALESCE(e.condition_expression, exc_chunk.lead_sentence, exc_chunk.verbatim_text) AS condition_expression,
        exc_chunk.verbatim_text
    FROM legal_chunks target_chunk
    JOIN legal_graph_edges e ON e.target_chunk_id = target_chunk.id
    JOIN legal_chunks exc_chunk ON e.source_chunk_id = exc_chunk.id
    WHERE target_chunk.path = target_path_param
      AND (exc_chunk.is_exception = TRUE OR e.relation_type IN ('EXEMPTS_CONDITION', 'OVERRIDES_PRIORITY'))
      AND exc_chunk.effective_date <= t_violation
      AND (exc_chunk.expiration_date IS NULL OR exc_chunk.expiration_date > t_violation)
      
    UNION ALL
    
    -- 2. Check statutory precedence rules (Emergency vehicle overrides / Special privileges) dynamically from legal_chunks
    SELECT 
        'STATUTORY_PRECEDENCE' AS rule_type,
        priv_chunk.override_priority,
        priv_chunk.chunk_index::text AS source_citation,
        priv_chunk.exception_type,
        COALESCE(priv_chunk.lead_sentence, priv_chunk.verbatim_text) AS condition_expression,
        priv_chunk.verbatim_text
    FROM legal_chunks priv_chunk
    WHERE is_emergency_vehicle = TRUE
      AND priv_chunk.exception_type = 'EMERGENCY_VEHICLE'
      AND priv_chunk.effective_date <= t_violation
      AND (priv_chunk.expiration_date IS NULL OR priv_chunk.expiration_date > t_violation)
      
    ORDER BY override_priority ASC;
END;
$$ LANGUAGE plpgsql STABLE;

-- ----------------------------------------------------------------------------
-- 4. RUNTIME KNOWLEDGE CACHE QUERY
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION query_runtime_knowledge_cache(
    input_query TEXT,
    input_vector VECTOR(384),
    similarity_threshold FLOAT DEFAULT 0.965
)
RETURNS TABLE (
    cache_id UUID,
    synthesized_answer TEXT,
    verified_citations JSONB,
    intent_classification JSONB,
    generated_plan JSONB,
    similarity_score FLOAT,
    is_exact_match BOOLEAN
) AS $$
DECLARE
    computed_hash VARCHAR(64);
    v_cache_id UUID;
    v_synthesized_answer TEXT;
    v_verified_citations JSONB;
    v_intent_classification JSONB;
    v_generated_plan JSONB;
    v_similarity_score FLOAT;
BEGIN
    computed_hash := encode(digest(trim(lower(input_query)), 'sha256'), 'hex');
    
    -- 1. Exact Hash Match (Latency < 0.5ms)
    SELECT 
        c.id, c.synthesized_answer, c.verified_citations, 
        c.intent_classification, c.generated_plan, 1.0::FLOAT
    INTO 
        v_cache_id, v_synthesized_answer, v_verified_citations, 
        v_intent_classification, v_generated_plan, v_similarity_score
    FROM runtime_knowledge_cache c
    WHERE c.query_hash = computed_hash
      AND c.validation_status = 'VERIFIED'
      AND c.expires_at > CURRENT_TIMESTAMP;
      
    IF FOUND THEN
        UPDATE runtime_knowledge_cache 
        SET hit_count = hit_count + 1, 
            last_accessed_at = CURRENT_TIMESTAMP 
        WHERE id = v_cache_id;
        
        cache_id := v_cache_id;
        synthesized_answer := v_synthesized_answer;
        verified_citations := v_verified_citations;
        intent_classification := v_intent_classification;
        generated_plan := v_generated_plan;
        similarity_score := v_similarity_score;
        is_exact_match := TRUE;
        RETURN NEXT;
        RETURN;
    END IF;

    -- 2. Semantic Embedding Similarity Match (Single-Pass HNSW)
    SELECT 
        c.id, c.synthesized_answer, c.verified_citations, 
        c.intent_classification, c.generated_plan, 
        (1.0 - (c.query_embedding_384 <=> input_vector))::FLOAT
    INTO 
        v_cache_id, v_synthesized_answer, v_verified_citations, 
        v_intent_classification, v_generated_plan, v_similarity_score
    FROM runtime_knowledge_cache c
    WHERE c.validation_status = 'VERIFIED'
      AND c.expires_at > CURRENT_TIMESTAMP
      AND c.query_embedding_384 IS NOT NULL
      AND (1.0 - (c.query_embedding_384 <=> input_vector)) >= similarity_threshold
    ORDER BY c.query_embedding_384 <=> input_vector ASC
    LIMIT 1;

    IF FOUND THEN
        UPDATE runtime_knowledge_cache 
        SET hit_count = hit_count + 1, 
            last_accessed_at = CURRENT_TIMESTAMP 
        WHERE id = v_cache_id;
        
        cache_id := v_cache_id;
        synthesized_answer := v_synthesized_answer;
        verified_citations := v_verified_citations;
        intent_classification := v_intent_classification;
        generated_plan := v_generated_plan;
        similarity_score := v_similarity_score;
        is_exact_match := FALSE;
        RETURN NEXT;
        RETURN;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- ----------------------------------------------------------------------------
-- 5. CACHE INVALIDATION TRIGGERS
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION invalidate_dependent_runtime_cache() 
RETURNS TRIGGER AS $$
DECLARE
    target_id UUID;
    target_path_str TEXT;
BEGIN
    IF TG_OP = 'DELETE' THEN
        target_id := OLD.id;
        target_path_str := OLD.path::text;
    ELSE
        target_id := NEW.id;
        target_path_str := NEW.path::text;
    END IF;

    UPDATE runtime_knowledge_cache
    SET validation_status = 'SUPERSEDED',
        verifier_feedback = 'Invalidated due to legislative amendment/deletion on chunk ' || COALESCE(target_path_str, target_id::text),
        expires_at = CURRENT_TIMESTAMP
    WHERE validation_status = 'VERIFIED'
      AND target_id = ANY(retrieved_chunk_ids);

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    ELSE
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_invalidate_cache_on_chunk_mutation ON legal_chunks;
CREATE TRIGGER trg_invalidate_cache_on_chunk_mutation
AFTER UPDATE OF verbatim_text, min_fine_vnd, max_fine_vnd, is_active OR DELETE ON legal_chunks
FOR EACH ROW EXECUTE FUNCTION invalidate_dependent_runtime_cache();

CREATE OR REPLACE FUNCTION invalidate_cache_on_edge_mutation() 
RETURNS TRIGGER AS $$
DECLARE
    affected_chunk_id UUID;
    rel_type TEXT;
BEGIN
    IF TG_OP = 'DELETE' THEN
        rel_type := OLD.relation_type::text;
        affected_chunk_id := OLD.target_chunk_id;
    ELSE
        rel_type := NEW.relation_type::text;
        affected_chunk_id := NEW.target_chunk_id;
    END IF;

    IF rel_type IN ('MODIFIES_AND_REPLACES', 'REPEALS') AND affected_chunk_id IS NOT NULL THEN
        UPDATE runtime_knowledge_cache
        SET validation_status = 'SUPERSEDED',
            verifier_feedback = 'Invalidated due to graph relationship change (amendment/repeal) on chunk ' || affected_chunk_id::text,
            expires_at = CURRENT_TIMESTAMP
        WHERE validation_status = 'VERIFIED'
          AND (affected_chunk_id = ANY(retrieved_chunk_ids) OR (TG_OP <> 'DELETE' AND NEW.id = ANY(traversed_edge_ids)));
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    ELSE
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_invalidate_cache_on_edge_mutation ON legal_graph_edges;
CREATE TRIGGER trg_invalidate_cache_on_edge_mutation
AFTER INSERT OR UPDATE OR DELETE ON legal_graph_edges
FOR EACH ROW 
EXECUTE FUNCTION invalidate_cache_on_edge_mutation();
