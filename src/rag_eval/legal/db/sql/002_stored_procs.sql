-- ============================================================================
-- STORED PROCEDURES & IN-DATABASE REASONING FUNCTIONS (REMEDIATED)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. VEHICLE TAXONOMY HIERARCHICAL EXPANSION (SCALAR & ARRAY)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION expand_vehicle_category(category TEXT)
RETURNS TEXT[] AS $$
DECLARE
    norm_cat TEXT;
BEGIN
    IF category IS NULL OR TRIM(category) = '' THEN
        RETURN ARRAY[]::TEXT[];
    END IF;

    -- Normalize Vietnamese diacritics, convert whitespace and hyphens to underscores, uppercase
    norm_cat := UPPER(REPLACE(REPLACE(TRIM(unaccent(category)), '-', '_'), ' ', '_'));

    RETURN CASE norm_cat
        -- Group Aliases
        WHEN 'CAR' THEN ARRAY['CAR_PASSENGER', 'CAR_TRUCK', 'CAR_BUS', 'CAR_TRACTOR']
        WHEN 'AUTO' THEN ARRAY['CAR_PASSENGER', 'CAR_TRUCK', 'CAR_BUS', 'CAR_TRACTOR']
        WHEN 'AUTOMOBILE' THEN ARRAY['CAR_PASSENGER', 'CAR_TRUCK', 'CAR_BUS', 'CAR_TRACTOR']
        WHEN 'XE_O_TO' THEN ARRAY['CAR_PASSENGER', 'CAR_TRUCK', 'CAR_BUS', 'CAR_TRACTOR']
        WHEN 'O_TO' THEN ARRAY['CAR_PASSENGER', 'CAR_TRUCK', 'CAR_BUS', 'CAR_TRACTOR']
        WHEN 'OTO' THEN ARRAY['CAR_PASSENGER', 'CAR_TRUCK', 'CAR_BUS', 'CAR_TRACTOR']
        WHEN 'MOTOR_VEHICLE' THEN ARRAY['CAR_PASSENGER', 'CAR_TRUCK', 'CAR_BUS', 'CAR_TRACTOR', 'MOTORCYCLE', 'MOPED', 'E_MOPED']
        WHEN 'XE_CO_GIOI' THEN ARRAY['CAR_PASSENGER', 'CAR_TRUCK', 'CAR_BUS', 'CAR_TRACTOR', 'MOTORCYCLE', 'MOPED', 'E_MOPED']
        WHEN 'CO_GIOI' THEN ARRAY['CAR_PASSENGER', 'CAR_TRUCK', 'CAR_BUS', 'CAR_TRACTOR', 'MOTORCYCLE', 'MOPED', 'E_MOPED']
        WHEN 'ALL_MOTOR' THEN ARRAY['CAR_PASSENGER', 'CAR_TRUCK', 'CAR_BUS', 'CAR_TRACTOR', 'MOTORCYCLE', 'MOPED', 'E_MOPED']
        WHEN 'TWO_WHEELER' THEN ARRAY['MOTORCYCLE', 'MOPED', 'E_MOPED', 'E_BICYCLE', 'BICYCLE_PRIMITIVE']
        WHEN 'XE_HAI_BANH' THEN ARRAY['MOTORCYCLE', 'MOPED', 'E_MOPED', 'E_BICYCLE', 'BICYCLE_PRIMITIVE']
        WHEN 'HAI_BANH' THEN ARRAY['MOTORCYCLE', 'MOPED', 'E_MOPED', 'E_BICYCLE', 'BICYCLE_PRIMITIVE']
        WHEN 'MOPED_ALL' THEN ARRAY['MOPED', 'E_MOPED']
        WHEN 'XE_GAN_MAY_ALL' THEN ARRAY['MOPED', 'E_MOPED']
        WHEN 'PRIMITIVE' THEN ARRAY['E_BICYCLE', 'BICYCLE_PRIMITIVE']
        WHEN 'XE_THO_SO' THEN ARRAY['E_BICYCLE', 'BICYCLE_PRIMITIVE']

        -- Exact Member Aliases (35+ aliases from schemas.py)
        WHEN 'CAR_PASSENGER' THEN ARRAY['CAR_PASSENGER']
        WHEN 'XE_CON' THEN ARRAY['CAR_PASSENGER']
        WHEN 'XE_O_TO_CON' THEN ARRAY['CAR_PASSENGER']
        WHEN 'O_TO_CON' THEN ARRAY['CAR_PASSENGER']
        WHEN 'PASSENGER_CAR' THEN ARRAY['CAR_PASSENGER']
        WHEN 'CAR_TRUCK' THEN ARRAY['CAR_TRUCK']
        WHEN 'XE_TAI' THEN ARRAY['CAR_TRUCK']
        WHEN 'XE_O_TO_TAI' THEN ARRAY['CAR_TRUCK']
        WHEN 'O_TO_TAI' THEN ARRAY['CAR_TRUCK']
        WHEN 'TRUCK' THEN ARRAY['CAR_TRUCK']
        WHEN 'CAR_BUS' THEN ARRAY['CAR_BUS']
        WHEN 'XE_KHACH' THEN ARRAY['CAR_BUS']
        WHEN 'XE_O_TO_KHACH' THEN ARRAY['CAR_BUS']
        WHEN 'O_TO_KHACH' THEN ARRAY['CAR_BUS']
        WHEN 'XE_BUYT' THEN ARRAY['CAR_BUS']
        WHEN 'O_TO_BUYT' THEN ARRAY['CAR_BUS']
        WHEN 'BUS' THEN ARRAY['CAR_BUS']
        WHEN 'CAR_TRACTOR' THEN ARRAY['CAR_TRACTOR']
        WHEN 'XE_DAU_KEO' THEN ARRAY['CAR_TRACTOR']
        WHEN 'XE_O_TO_DAU_KEO' THEN ARRAY['CAR_TRACTOR']
        WHEN 'DAU_KEO' THEN ARRAY['CAR_TRACTOR']
        WHEN 'TRACTOR' THEN ARRAY['CAR_TRACTOR']
        WHEN 'MOTORCYCLE' THEN ARRAY['MOTORCYCLE']
        WHEN 'XE_MO_TO' THEN ARRAY['MOTORCYCLE']
        WHEN 'MO_TO' THEN ARRAY['MOTORCYCLE']
        WHEN 'XE_MAY' THEN ARRAY['MOTORCYCLE']
        WHEN 'MOTO' THEN ARRAY['MOTORCYCLE']
        WHEN 'MOPED' THEN ARRAY['MOPED']
        WHEN 'XE_GAN_MAY' THEN ARRAY['MOPED']
        WHEN 'GAN_MAY' THEN ARRAY['MOPED']
        WHEN 'E_MOPED' THEN ARRAY['E_MOPED']
        WHEN 'XE_MAY_DIEN' THEN ARRAY['E_MOPED']
        WHEN 'ELECTRIC_MOPED' THEN ARRAY['E_MOPED']
        WHEN 'E_BICYCLE' THEN ARRAY['E_BICYCLE']
        WHEN 'XE_DAP_DIEN' THEN ARRAY['E_BICYCLE']
        WHEN 'ELECTRIC_BICYCLE' THEN ARRAY['E_BICYCLE']
        WHEN 'BICYCLE_PRIMITIVE' THEN ARRAY['BICYCLE_PRIMITIVE']
        WHEN 'XE_DAP' THEN ARRAY['BICYCLE_PRIMITIVE']
        WHEN 'XE_THO_SO_PRIMITIVE' THEN ARRAY['BICYCLE_PRIMITIVE']
        WHEN 'SPECIALIZED_MACHINE' THEN ARRAY['SPECIALIZED_MACHINE']
        WHEN 'XE_MAY_CHUYEN_DUNG' THEN ARRAY['SPECIALIZED_MACHINE']
        WHEN 'XE_CHUYEN_DUNG' THEN ARRAY['SPECIALIZED_MACHINE']
        WHEN 'PRIORITY_VEHICLE' THEN ARRAY['PRIORITY_VEHICLE']
        WHEN 'XE_UU_TIEN' THEN ARRAY['PRIORITY_VEHICLE']

        ELSE ARRAY[norm_cat]
    END;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION expand_vehicle_categories(categories TEXT[])
RETURNS TEXT[] AS $$
DECLARE
    cat TEXT;
    result TEXT[] := ARRAY[]::TEXT[];
BEGIN
    IF categories IS NULL OR cardinality(categories) = 0 THEN
        RETURN ARRAY[]::TEXT[];
    END IF;
    FOREACH cat IN ARRAY categories LOOP
        IF cat IS NOT NULL AND trim(cat) <> '' THEN
            result := array_cat(result, expand_vehicle_category(cat));
        END IF;
    END LOOP;
    IF cardinality(result) = 0 THEN
        RETURN ARRAY[]::TEXT[];
    END IF;
    RETURN ARRAY(SELECT DISTINCT unnest(result));
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- ----------------------------------------------------------------------------
-- 2. HYBRID LEGAL SEARCH WITH RECIPROCAL RANK FUSION (RRF) - DUAL DIMENSIONS
-- ----------------------------------------------------------------------------

-- 2.1. Explicit 384-Dimensional Overload (BAAI/bge-small-en-v1.5)
CREATE OR REPLACE FUNCTION hybrid_legal_search_384(
    query_text TEXT,
    query_vector VECTOR(384),
    target_actor actor_category DEFAULT NULL,
    target_vehicles TEXT[] DEFAULT NULL,
    match_limit INT DEFAULT 20,
    rrf_k INT DEFAULT 60
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
    expanded_vehicles TEXT[] := expand_vehicle_categories(target_vehicles);
    ts_query TSQUERY := websearch_to_tsquery('vietnamese_legal', query_text);
    candidate_limit INT := GREATEST(match_limit * 4, 100);
BEGIN
    RETURN QUERY
    WITH dense_search AS (
        SELECT 
            c.id,
            ROW_NUMBER() OVER (ORDER BY c.dense_embedding_384 <=> query_vector) AS rank_dense
        FROM legal_chunks c
        WHERE c.is_active = TRUE
          AND c.dense_embedding_384 IS NOT NULL
          AND (target_actor IS NULL OR c.primary_actor = target_actor)
          AND (
              target_vehicles IS NULL 
              OR cardinality(target_vehicles) = 0
              OR c.vehicle_types = '[]'::jsonb
              OR c.vehicle_types ?| expanded_vehicles
              OR c.vehicle_types ?| target_vehicles
          )
        ORDER BY c.dense_embedding_384 <=> query_vector
        LIMIT candidate_limit
    ),
    sparse_search AS (
        SELECT 
            c.id,
            ROW_NUMBER() OVER (
                ORDER BY ts_rank_cd(c.tsv_vi, ts_query) DESC
            ) AS rank_sparse
        FROM legal_chunks c
        WHERE c.is_active = TRUE
          AND (ts_query IS NULL OR c.tsv_vi @@ ts_query)
          AND (target_actor IS NULL OR c.primary_actor = target_actor)
          AND (
              target_vehicles IS NULL 
              OR cardinality(target_vehicles) = 0
              OR c.vehicle_types = '[]'::jsonb
              OR c.vehicle_types ?| expanded_vehicles
              OR c.vehicle_types ?| target_vehicles
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

-- 2.2. Explicit 1536-Dimensional Overload (OpenAI / BGE-M3)
CREATE OR REPLACE FUNCTION hybrid_legal_search_1536(
    query_text TEXT,
    query_vector VECTOR(1536),
    target_actor actor_category DEFAULT NULL,
    target_vehicles TEXT[] DEFAULT NULL,
    match_limit INT DEFAULT 20,
    rrf_k INT DEFAULT 60
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
    expanded_vehicles TEXT[] := expand_vehicle_categories(target_vehicles);
    ts_query TSQUERY := websearch_to_tsquery('vietnamese_legal', query_text);
    candidate_limit INT := GREATEST(match_limit * 4, 100);
BEGIN
    RETURN QUERY
    WITH dense_search AS (
        SELECT 
            c.id,
            ROW_NUMBER() OVER (ORDER BY c.dense_embedding_1536 <=> query_vector) AS rank_dense
        FROM legal_chunks c
        WHERE c.is_active = TRUE
          AND c.dense_embedding_1536 IS NOT NULL
          AND (target_actor IS NULL OR c.primary_actor = target_actor)
          AND (
              target_vehicles IS NULL 
              OR cardinality(target_vehicles) = 0
              OR c.vehicle_types = '[]'::jsonb
              OR c.vehicle_types ?| expanded_vehicles
              OR c.vehicle_types ?| target_vehicles
          )
        ORDER BY c.dense_embedding_1536 <=> query_vector
        LIMIT candidate_limit
    ),
    sparse_search AS (
        SELECT 
            c.id,
            ROW_NUMBER() OVER (
                ORDER BY ts_rank_cd(c.tsv_vi, ts_query) DESC
            ) AS rank_sparse
        FROM legal_chunks c
        WHERE c.is_active = TRUE
          AND (ts_query IS NULL OR c.tsv_vi @@ ts_query)
          AND (target_actor IS NULL OR c.primary_actor = target_actor)
          AND (
              target_vehicles IS NULL 
              OR cardinality(target_vehicles) = 0
              OR c.vehicle_types = '[]'::jsonb
              OR c.vehicle_types ?| expanded_vehicles
              OR c.vehicle_types ?| target_vehicles
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

-- 2.3. Polymorphic Overloads for hybrid_legal_search
CREATE OR REPLACE FUNCTION hybrid_legal_search(
    query_text TEXT,
    query_vector VECTOR(384),
    target_actor actor_category DEFAULT NULL,
    target_vehicles TEXT[] DEFAULT NULL,
    match_limit INT DEFAULT 20,
    rrf_k INT DEFAULT 60
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
        query_text, query_vector, target_actor, target_vehicles, match_limit, rrf_k
    );
END;
$$ LANGUAGE plpgsql STABLE;

CREATE OR REPLACE FUNCTION hybrid_legal_search(
    query_text TEXT,
    query_vector VECTOR(1536),
    target_actor actor_category DEFAULT NULL,
    target_vehicles TEXT[] DEFAULT NULL,
    match_limit INT DEFAULT 20,
    rrf_k INT DEFAULT 60
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
        query_text, query_vector, target_actor, target_vehicles, match_limit, rrf_k
    );
END;
$$ LANGUAGE plpgsql STABLE;

-- ----------------------------------------------------------------------------
-- 3. NORMATIVE TRIAD RECURSIVE CTE TRAVERSAL
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION traverse_normative_triad(
    anchor_sign_code VARCHAR(64),
    target_vehicles TEXT[] DEFAULT ARRAY['CAR_PASSENGER']
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
DECLARE
    expanded_vehicles TEXT[] := expand_vehicle_categories(target_vehicles);
BEGIN
    RETURN QUERY
    WITH RECURSIVE triad_graph AS (
        -- Anchor Member: Resolve the Technical Standard Sign from sign_catalog
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
        
        UNION ALL
        
        -- Recursive Member: Traverse Graph Edges
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
        WHERE tg.hop_depth < 3
          AND NOT (next_chunk.id = ANY(tg.visited_nodes))
          AND next_chunk.is_active = TRUE
          AND (
              target_vehicles IS NULL 
              OR cardinality(target_vehicles) = 0
              OR next_chunk.vehicle_types = '[]'::jsonb 
              OR next_chunk.vehicle_types ?| expanded_vehicles
              OR next_chunk.vehicle_types ?| target_vehicles
          )
          AND e.relation_type IN ('DEFINES_SANCTION_FOR', 'HAS_ADDITIONAL_SANCTION', 'REFERENCES_TECHNICAL_STANDARD', 'MODIFIES_AND_REPLACES', 'GUIDES', 'DEFINES_TERM')
    )
    SELECT 
        tg.hop_depth,
        tg.node_role,
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
-- 4. SCOPE OVERRIDE & STATUTORY PRECEDENCE RESOLUTION
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION resolve_scope_overrides(
    target_path_param LTREE,
    active_actor actor_category DEFAULT 'DRIVER',
    is_emergency_vehicle BOOLEAN DEFAULT FALSE
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
        e.condition_expression,
        exc_chunk.verbatim_text
    FROM legal_chunks target_chunk
    JOIN legal_graph_edges e ON e.target_chunk_id = target_chunk.id
    JOIN legal_chunks exc_chunk ON e.source_chunk_id = exc_chunk.id
    WHERE target_chunk.path = target_path_param
      AND (exc_chunk.is_exception = TRUE OR e.relation_type IN ('EXEMPTS_CONDITION', 'OVERRIDES_PRIORITY'))
      AND exc_chunk.is_active = TRUE
      
    UNION ALL
    
    -- 2. Check statutory precedence rules (Emergency vehicle overrides)
    SELECT 
        'STATUTORY_PRECEDENCE' AS rule_type,
        priv_chunk.override_priority,
        priv_chunk.chunk_index::text AS source_citation,
        priv_chunk.exception_type,
        'Xe ưu tiên đang thực hiện nhiệm vụ khẩn cấp theo Điều 22 Luật GTĐB' AS condition_expression,
        priv_chunk.verbatim_text
    FROM legal_chunks priv_chunk
    WHERE is_emergency_vehicle = TRUE
      AND priv_chunk.exception_type = 'EMERGENCY_VEHICLE'
      AND priv_chunk.is_active = TRUE
      
    ORDER BY override_priority ASC;
END;
$$ LANGUAGE plpgsql STABLE;

-- ----------------------------------------------------------------------------
-- 5. RUNTIME KNOWLEDGE CACHE QUERY (SINGLE-PASS HNSW & DIRECT PK UPDATE)
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
-- 6. CACHE INVALIDATION TRIGGERS
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

    -- Only invalidate if relation type is an amendment or repeal
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

