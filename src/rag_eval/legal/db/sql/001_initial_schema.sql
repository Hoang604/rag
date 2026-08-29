-- ============================================================================
-- 0. DATABASE EXTENSIONS & SYSTEM CONFIGURATION
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "vector";        -- pgvector v0.7.0+ (HNSW index support)
CREATE EXTENSION IF NOT EXISTS "ltree";         -- Hierarchical label tree support
CREATE EXTENSION IF NOT EXISTS "pg_trgm";       -- Trigram fuzzy matching for sign codes
CREATE EXTENSION IF NOT EXISTS "btree_gin";     -- Multi-column GIN indexing
CREATE EXTENSION IF NOT EXISTS "btree_gist";    -- Multi-column GIST indexing
CREATE EXTENSION IF NOT EXISTS "unaccent";      -- Vietnamese unaccented text normalization

-- ============================================================================
-- 1. ENUMERATED TYPES (DOMAIN TAXONOMY)
-- ============================================================================

DO $$ BEGIN
    CREATE TYPE legal_document_type AS ENUM (
        'LUAT',                 -- Law / Code passed by National Assembly (Quốc hội)
        'NGHI_DINH',            -- Decree issued by Government (Chính phủ)
        'THONG_TU',             -- Circular issued by Ministries (Bộ GTVT / Bộ Công an)
        'QUY_CHUAN_KY_THUAT',   -- National Technical Standard (QCVN 41:2019/BGTVT)
        'QUYET_DINH'            -- Decision issued by Prime Minister / Ministries
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE legal_document_status AS ENUM (
        'EFFECTIVE',            -- Đang có hiệu lực thi hành
        'PARTIALLY_EXPIRED',    -- Hết hiệu lực một phần (do văn bản khác sửa đổi)
        'EXPIRED',              -- Hết hiệu lực toàn bộ
        'NOT_YET_EFFECTIVE'     -- Đã ban hành nhưng chưa đến ngày có hiệu lực
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE legal_node_type AS ENUM (
        'DOCUMENT',             -- Cấp văn bản
        'PART',                 -- Phần
        'CHAPTER',              -- Chương
        'SECTION',              -- Mục
        'SUB_SECTION',          -- Tiểu mục
        'ARTICLE',              -- Điều
        'CLAUSE',               -- Khoản
        'POINT',                -- Điểm
        'APPENDIX',             -- Phụ lục
        'TABLE',                -- Bảng biểu
        'CLAUSE_PARAGRAPH'      -- Đoạn trong khoản (không đánh ký hiệu a, b, c)
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- 8 Canonical Jurisprudential Normative Roles matching schemas.py NormRole
DO $$ BEGIN
    CREATE TYPE legal_norm_role AS ENUM (
        'HYPOTHESIS_CONDITION',     -- Giả định (Chủ thể, điều kiện, hoàn cảnh áp dụng)
        'PRESCRIPTION_DUTY',        -- Quy định nghĩa vụ (Hành vi bắt buộc phải làm)
        'PRESCRIPTION_PROHIBITION', -- Quy định cấm đoán (Hành vi nghiêm cấm)
        'PRESCRIPTION_PERMISSION',  -- Quy định cho phép (Quyền hạn, miễn trừ)
        'SANCTION_PRINCIPAL',       -- Chế tài chính (Phạt tiền, phạt cảnh cáo)
        'SANCTION_SUPPLEMENTARY',   -- Chế tài bổ sung (Tước quyền sử dụng GPLX, tịch thu phương tiện)
        'SANCTION_POINT_DEDUCTION', -- Chế tài trừ điểm giấy phép lái xe (Nghị định 168/2024)
        'REMEDIAL_MEASURE'          -- Biện pháp khắc phục hậu quả (Buộc khôi phục tình trạng ban đầu)
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE actor_category AS ENUM (
        'DRIVER',               -- Người điều khiển phương tiện
        'PASSENGER',            -- Người ngồi trên phương tiện
        'PEDESTRIAN',           -- Người đi bộ
        'VEHICLE_OWNER',        -- Chủ phương tiện (cá nhân hoặc tổ chức)
        'TRANSPORT_BUSINESS',   -- Đơn vị kinh doanh vận tải / Hợp tác xã
        'ROAD_AUTHORITY',       -- Cơ quan quản lý đường bộ / Người điều khiển giao thông
        'OTHER'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE graph_relation_type AS ENUM (
        'DEFINES_SANCTION_FOR',         -- Nghị định chế tài hành vi quy định tại Luật
        'HAS_ADDITIONAL_SANCTION',       -- Liên kết chế tài bổ sung (Tước GPLX, tạm giữ xe, trừ điểm)
        'REFERENCES_TECHNICAL_STANDARD', -- Luật/Nghị định dẫn chiếu Quy chuẩn kỹ thuật QCVN (Biển báo, vạch kẻ)
        'MODIFIES_AND_REPLACES',         -- Sửa đổi, bổ sung hoặc thay thế điều khoản cũ
        'REPEALS',                       -- Bãi bỏ điều khoản cũ
        'OVERRIDES_PRIORITY',            -- Quan hệ ưu tiên/ghi đè hiệu lực (CSGT > Đèn > Biển > Vạch)
        'EXEMPTS_CONDITION',             -- Điều khoản ngoại lệ loại trừ trách nhiệm ("Trừ trường hợp...")
        'GUIDES',                        -- Hướng dẫn chi tiết thi hành
        'DEFINES_TERM'                   -- Định nghĩa thuật ngữ áp dụng cho quy định
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE sign_category_enum AS ENUM (
        'PROHIBITORY',          -- Biển báo cấm (Nhóm P)
        'WARNING',              -- Biển cảnh báo nguy hiểm (Nhóm W)
        'MANDATORY',            -- Biển hiệu lệnh (Nhóm R)
        'GUIDE',                -- Biển chỉ dẫn (Nhóm I)
        'AUXILIARY',            -- Biển phụ (Nhóm S)
        'ROAD_MARKING',         -- Vạch kẻ đường (Nhóm M)
        'TRAFFIC_LIGHT',        -- Đèn tín hiệu giao thông
        'POLICE_SIGNAL'         -- Hiệu lệnh của Cảnh sát giao thông / Người điều khiển
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

DO $$ BEGIN
    CREATE TYPE cache_validation_status AS ENUM (
        'CANDIDATE',            -- Mới sinh bởi agent, chưa qua kiểm chứng tự động
        'VERIFIED',             -- Đã kiểm chứng trích dẫn và logic thành công
        'REJECTED',             -- Bị từ chối do trích dẫn sai hoặc vi phạm logic pháp lý
        'SUPERSEDED'            -- Bị thay thế khi văn bản luật nền tảng thay đổi
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- ============================================================================
-- 2. TABLE DEFINITIONS
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 2.1. LEGAL DOCUMENTS
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS legal_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_code VARCHAR(128) NOT NULL UNIQUE,          -- e.g., "100/2019/ND-CP", "QCVN 41:2019/BGTVT"
    title TEXT NOT NULL,                            -- Tên đầy đủ của văn bản
    short_title VARCHAR(256),                       -- Tên viết tắt hiển thị (e.g., "Nghị định 100/2019")
    doc_type legal_document_type NOT NULL,
    issuing_authority VARCHAR(256) NOT NULL,        -- Cơ quan ban hành (e.g., "Chính phủ")
    signer VARCHAR(128),                            -- Người ký (e.g., "Nguyễn Xuân Phúc")
    promulgation_date DATE NOT NULL,                -- Ngày ban hành
    effective_date DATE NOT NULL,                   -- Ngày có hiệu lực
    expiration_date DATE,                           -- Ngày hết hiệu lực (NULL nếu còn hiệu lực vô thời hạn)
    status legal_document_status NOT NULL DEFAULT 'EFFECTIVE',
    gazette_date DATE,                              -- Ngày đăng công báo
    source_url TEXT,                                -- Đường dẫn văn bản gốc chính thức
    document_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_doc_dates CHECK (expiration_date IS NULL OR expiration_date >= effective_date)
);

-- ----------------------------------------------------------------------------
-- 2.2. LEGAL HIERARCHY NODES (Syntactic AST via ltree)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS legal_hierarchy_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES legal_documents(id) ON DELETE CASCADE,
    parent_id UUID REFERENCES legal_hierarchy_nodes(id) ON DELETE CASCADE,
    node_type legal_node_type NOT NULL,
    node_index VARCHAR(64) NOT NULL,                -- e.g., "Chương II", "Điều 5", "Khoản 1", "Điểm a"
    title VARCHAR(512),                             -- Tiêu đề của điều/khoản (nếu có)
    path LTREE NOT NULL,                            -- Dot-separated path: doc_nd100.c2.s1.a5.c1.p_a
    depth INT NOT NULL,                             -- Cấp bậc phân cấp (1 = Document, 6 = Point)
    display_order INT NOT NULL DEFAULT 0,           -- Thứ tự xuất hiện tự nhiên trong văn bản
    lead_sentence TEXT,                             -- Câu dẫn đầu của Khoản/Điều trực tiếp
    raw_text TEXT NOT NULL,                         -- Nguyên văn nội dung của nút
    full_path_title TEXT,                           -- Đường dẫn danh từ đầy đủ để tái tạo ngữ cảnh
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_hierarchy_path UNIQUE (path),
    CONSTRAINT chk_depth_positive CHECK (depth > 0)
);

-- ----------------------------------------------------------------------------
-- 2.3. LEGAL CHUNKS (Canonical Fully Qualified Chunks - CFQC)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS legal_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id UUID NOT NULL REFERENCES legal_hierarchy_nodes(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES legal_documents(id) ON DELETE CASCADE,
    chunk_type VARCHAR(64) NOT NULL DEFAULT 'LEGAL_RULE', -- 'LEGAL_RULE', 'TECHNICAL_STANDARD', 'DEFINITION'
    chunk_index VARCHAR(64) NOT NULL,               -- e.g., "Điều 5 Khoản 1 Điểm a"
    path LTREE NOT NULL,                            -- Inherited ltree path for direct filtering
    
    -- Content representations
    lead_sentence TEXT,                             -- Câu dẫn kế thừa bắt buộc (Context Preservation)
    verbatim_text TEXT NOT NULL,                    -- Văn bản gốc chính xác của điểm/khoản
    contextualized_text TEXT NOT NULL,              -- [Tên văn bản] > [Điều] > [Câu dẫn Khoản] > [Nội dung Điểm]
    
    -- Legal Norm Formal Classification
    norm_role legal_norm_role NOT NULL DEFAULT 'PRESCRIPTION_DUTY',
    primary_actor actor_category NOT NULL DEFAULT 'DRIVER',
    vehicle_types JSONB NOT NULL DEFAULT '[]'::jsonb, -- Array: ["CAR_PASSENGER", "CAR_TRUCK", "CAR_BUS", "CAR_TRACTOR", "MOTORCYCLE", "MOPED", "E_MOPED", "E_BICYCLE", "BICYCLE_PRIMITIVE", "SPECIALIZED_MACHINE", "PRIORITY_VEHICLE"]
    violation_categories JSONB NOT NULL DEFAULT '[]'::jsonb, -- Array: ["ALCOHOL_DRUGS", "SPEED_DISTANCE", "RED_LIGHT"]
    
    -- Financial & Administrative Sanctions Modeling
    min_fine_vnd BIGINT,                           -- Mức phạt tiền tối thiểu (VND)
    max_fine_vnd BIGINT,                           -- Mức phạt tiền tối đa (VND)
    additional_sanctions JSONB NOT NULL DEFAULT '{}'::jsonb,
    remedial_measures JSONB NOT NULL DEFAULT '[]'::jsonb, -- Array: ["Buộc khôi phục tình trạng ban đầu"]
    
    -- Scope Override, Precedence & Exceptions
    is_exception BOOLEAN NOT NULL DEFAULT FALSE,
    exception_type VARCHAR(64),                    -- 'EMERGENCY_VEHICLE', 'POLICE_COMMAND', 'AMBULANCE'
    exception_target_path LTREE,                   -- Đường dẫn đến quy tắc chung bị ghi đè
    override_priority INT NOT NULL DEFAULT 5,      -- 1=Police, 2=Light, 3=Sign, 4=Marking, 5=General Rule
    
    -- Multi-Modal Retrieval Fields (Dual Dimension Support)
    dense_embedding_384 VECTOR(384),               -- Dense embedding (384-dim standard BAAI/bge-small-en-v1.5)
    dense_embedding_1536 VECTOR(1536),             -- Dense embedding (1536-dim standard OpenAI/BGE-M3)
    dense_embedding VECTOR(1536),                  -- Backward-compatible alias
    sparse_embedding JSONB DEFAULT '{}'::jsonb,    -- BM25 / SPLADE token weights
    tsv_vi TSVECTOR,                               -- Vietnamese unaccented full-text search vector
    
    -- Temporal Boundaries
    effective_date DATE NOT NULL,
    expiration_date DATE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_chunk_path UNIQUE (path),
    CONSTRAINT chk_fine_boundaries CHECK (
        (min_fine_vnd IS NULL AND max_fine_vnd IS NULL) OR
        (min_fine_vnd IS NOT NULL AND max_fine_vnd IS NOT NULL AND min_fine_vnd <= max_fine_vnd)
    )
);

-- ----------------------------------------------------------------------------
-- 2.4. LEGAL GRAPH EDGES (Directed Relational Property Graph)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS legal_graph_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_chunk_id UUID NOT NULL REFERENCES legal_chunks(id) ON DELETE CASCADE,
    target_chunk_id UUID REFERENCES legal_chunks(id) ON DELETE SET NULL,
    source_node_id UUID NOT NULL REFERENCES legal_hierarchy_nodes(id) ON DELETE CASCADE,
    target_node_id UUID REFERENCES legal_hierarchy_nodes(id) ON DELETE SET NULL,
    
    source_path LTREE NOT NULL,
    target_path LTREE,                             -- Nullable if referencing an unresolved external document
    target_external_ref TEXT,                      -- e.g., "Khoản 2 Điều 12 Luật Giao thông đường bộ 2008"
    
    relation_type graph_relation_type NOT NULL,
    description TEXT,                              -- Giải thích chi tiết về mối quan hệ dẫn chiếu
    citation_text TEXT,                            -- Đoạn trích dẫn nguyên văn sinh ra mối quan hệ
    
    is_conditional BOOLEAN NOT NULL DEFAULT FALSE,
    condition_expression TEXT,                     -- e.g., "Khi điều khiển xe chở quá tải trọng từ 20% đến 50%"
    confidence_score NUMERIC(4, 3) NOT NULL DEFAULT 1.000, -- Điểm tin cậy trích xuất (0.000 - 1.000)
    
    valid_from DATE,
    valid_to DATE,
    
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Fixed: NULLS NOT DISTINCT ensures idempotency when target_chunk_id IS NULL
    CONSTRAINT uq_graph_edge UNIQUE NULLS NOT DISTINCT (source_chunk_id, target_chunk_id, relation_type),
    CONSTRAINT chk_confidence_range CHECK (confidence_score >= 0.000 AND confidence_score <= 1.000)
);

-- ----------------------------------------------------------------------------
-- 2.5. SIGN CATALOG (QCVN 41:2019/BGTVT Technical Specifications)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sign_catalog (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id UUID REFERENCES legal_chunks(id) ON DELETE SET NULL,
    node_id UUID REFERENCES legal_hierarchy_nodes(id) ON DELETE SET NULL,
    sign_code VARCHAR(64) NOT NULL UNIQUE,         -- e.g., "P.102", "W.207a", "R.301a", "M.1.1"
    sign_name TEXT NOT NULL,                       -- e.g., "Cấm đi ngược chiều", "Giao nhau với đường không ưu tiên"
    sign_category sign_category_enum NOT NULL,
    shape VARCHAR(64) NOT NULL,                    -- "TRÒN", "TAM_GIÁC_ĐỀU", "CHỮ_NHẬT", "HÌNH_THOI", "VẠCH_SƠN"
    primary_color VARCHAR(64) NOT NULL,            -- "ĐỎ_TRẮNG", "VÀNG_ĐEN", "XANH_TRẮNG"
    
    meaning TEXT NOT NULL,                         -- Ý nghĩa kỹ thuật và hiệu lực báo hiệu
    placement_rules TEXT,                          -- Quy chuẩn đặt biển, cự ly và vị trí hiệu lực
    penalty_references JSONB NOT NULL DEFAULT '[]'::jsonb, -- Danh sách paths đến các điều khoản xử phạt Nghị định
    dimensions_spec JSONB NOT NULL DEFAULT '{}'::jsonb,    -- Chi tiết kích thước (đường kính, viền đỏ, vạch trắng)
    image_url TEXT,                                -- Đường dẫn ảnh minh họa chuẩn
    
    -- Dual Dimension Vector Embeddings
    vector_embedding_384 VECTOR(384),              -- Dense embedding (384-dim standard)
    vector_embedding_1536 VECTOR(1536),            -- Dense embedding (1536-dim standard)
    vector_embedding VECTOR(1536),                 -- Backward-compatible alias
    tsv_sign TSVECTOR,                             -- Full-text search vector tiếng Việt
    
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- 2.6. RUNTIME KNOWLEDGE CACHE (Agent Dynamic Knowledge & Provenance)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS runtime_knowledge_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_hash VARCHAR(64) NOT NULL UNIQUE,        -- SHA-256 của normalized natural query
    natural_query TEXT NOT NULL,                   -- Câu hỏi tự nhiên nguyên bản của người dùng
    query_embedding_384 VECTOR(384),               -- 384-dim query embedding
    query_embedding_1536 VECTOR(1536),             -- 1536-dim query embedding
    query_embedding VECTOR(1536) NOT NULL,         -- Backward-compatible alias
    
    intent_classification JSONB NOT NULL,
    generated_plan JSONB NOT NULL,                 -- Kế hoạch suy luận đa bước (DAG of sub-goals)
    retrieved_chunk_ids UUID[] NOT NULL DEFAULT '{}', -- Danh sách các chunk đã dùng để tổng hợp
    traversed_edge_ids UUID[] NOT NULL DEFAULT '{}',  -- Danh sách các cạnh đồ thị đã duyệt qua
    
    synthesized_answer TEXT NOT NULL,              -- Câu trả lời pháp lý đã tổng hợp
    verified_citations JSONB NOT NULL,             -- Danh sách trích dẫn chuẩn pháp lý kèm bằng chứng
    
    validation_status cache_validation_status NOT NULL DEFAULT 'CANDIDATE',
    verifier_feedback TEXT,                        -- Nhận xét và bằng chứng kiểm định của Verifier Agent
    hit_count INT NOT NULL DEFAULT 1,
    ttl_seconds INT NOT NULL DEFAULT 2592000,       -- TTL mặc định 30 ngày (2592000s)
    expires_at TIMESTAMPTZ NOT NULL,
    last_accessed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ----------------------------------------------------------------------------
-- 2.7. QUERY EXECUTION LOGS (Audit Trails & Telemetry)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS query_execution_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL,
    query_text TEXT NOT NULL,
    query_embedding_384 VECTOR(384),
    query_embedding_1536 VECTOR(1536),
    query_embedding VECTOR(1536),
    execution_plan JSONB NOT NULL,
    tools_invoked JSONB NOT NULL,                  -- Danh sách các công cụ MCP đã gọi kèm tham số và thời gian
    steps_count INT NOT NULL DEFAULT 1,
    latency_ms NUMERIC(10, 2) NOT NULL,
    cache_hit BOOLEAN NOT NULL DEFAULT FALSE,
    retrieved_chunks JSONB NOT NULL DEFAULT '[]'::jsonb,
    final_status VARCHAR(32) NOT NULL DEFAULT 'SUCCESS', -- 'SUCCESS', 'FAILED', 'CIRCUIT_BROKEN'
    error_message TEXT,
    token_usage JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- 3. INDEX DEFINITIONS
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 3.1. HNSW VECTOR INDEXES (pgvector 0.7+)
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_legal_chunks_dense_embedding_384_hnsw 
ON legal_chunks 
USING hnsw (dense_embedding_384 vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_legal_chunks_dense_embedding_1536_hnsw 
ON legal_chunks 
USING hnsw (dense_embedding_1536 vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_legal_chunks_dense_embedding_hnsw 
ON legal_chunks 
USING hnsw (dense_embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_sign_catalog_embedding_384_hnsw 
ON sign_catalog 
USING hnsw (vector_embedding_384 vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_sign_catalog_embedding_1536_hnsw 
ON sign_catalog 
USING hnsw (vector_embedding_1536 vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_sign_catalog_embedding_hnsw 
ON sign_catalog 
USING hnsw (vector_embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_runtime_cache_query_embedding_384_hnsw 
ON runtime_knowledge_cache 
USING hnsw (query_embedding_384 vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_runtime_cache_query_embedding_1536_hnsw 
ON runtime_knowledge_cache 
USING hnsw (query_embedding_1536 vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_runtime_cache_query_embedding_hnsw 
ON runtime_knowledge_cache 
USING hnsw (query_embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- ----------------------------------------------------------------------------
-- 3.2. HIERARCHICAL LTREE INDEXES
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_legal_nodes_path_gist ON legal_hierarchy_nodes USING gist (path);
CREATE INDEX IF NOT EXISTS idx_legal_nodes_path_btree ON legal_hierarchy_nodes (path);

CREATE INDEX IF NOT EXISTS idx_legal_chunks_path_gist ON legal_chunks USING gist (path);
CREATE INDEX IF NOT EXISTS idx_legal_chunks_path_btree ON legal_chunks (path);

CREATE INDEX IF NOT EXISTS idx_legal_graph_edges_source_path_gist ON legal_graph_edges USING gist (source_path);
CREATE INDEX IF NOT EXISTS idx_legal_graph_edges_target_path_gist ON legal_graph_edges USING gist (target_path);

-- ----------------------------------------------------------------------------
-- 3.3. STRUCTURED JSONB GIN INDEXES (jsonb_path_ops)
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_legal_chunks_vehicle_types_gin 
ON legal_chunks 
USING gin (vehicle_types jsonb_path_ops);

CREATE INDEX IF NOT EXISTS idx_legal_chunks_violation_cats_gin 
ON legal_chunks 
USING gin (violation_categories jsonb_path_ops);

CREATE INDEX IF NOT EXISTS idx_legal_chunks_sanctions_gin 
ON legal_chunks 
USING gin (additional_sanctions jsonb_path_ops);

CREATE INDEX IF NOT EXISTS idx_legal_chunks_metadata_gin 
ON legal_chunks 
USING gin (metadata jsonb_path_ops);

-- GIN Array Indexes for Cache Invalidation Triggers (Prevents table scan)
CREATE INDEX IF NOT EXISTS idx_runtime_cache_chunk_ids_gin 
ON runtime_knowledge_cache USING gin (retrieved_chunk_ids);

CREATE INDEX IF NOT EXISTS idx_runtime_cache_edge_ids_gin 
ON runtime_knowledge_cache USING gin (traversed_edge_ids);

-- ----------------------------------------------------------------------------
-- 3.4. GRAPH EDGE TRAVERSAL & RELATION INDEXES
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_legal_graph_edges_source_chunk ON legal_graph_edges (source_chunk_id);
CREATE INDEX IF NOT EXISTS idx_legal_graph_edges_target_chunk ON legal_graph_edges (target_chunk_id);
CREATE INDEX IF NOT EXISTS idx_legal_graph_edges_relation ON legal_graph_edges (relation_type);

-- ----------------------------------------------------------------------------
-- 3.5. TRIGRAM & EXACT MATCH INDEXES (pg_trgm)
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_sign_catalog_code_trgm ON sign_catalog USING gin (sign_code gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_sign_catalog_name_trgm ON sign_catalog USING gin (sign_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_legal_nodes_index_trgm ON legal_hierarchy_nodes USING gin (node_index gin_trgm_ops);

-- ----------------------------------------------------------------------------
-- 3.6. RELATIONAL B-TREE INDEXES & CONSTRAINTS
-- ----------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_legal_nodes_doc_id ON legal_hierarchy_nodes (document_id);
CREATE INDEX IF NOT EXISTS idx_legal_nodes_parent_id ON legal_hierarchy_nodes (parent_id);
CREATE INDEX IF NOT EXISTS idx_legal_chunks_node_id ON legal_chunks (node_id);
CREATE INDEX IF NOT EXISTS idx_legal_chunks_doc_id ON legal_chunks (document_id);
CREATE INDEX IF NOT EXISTS idx_sign_catalog_chunk_id ON sign_catalog (chunk_id);
CREATE INDEX IF NOT EXISTS idx_sign_catalog_node_id ON sign_catalog (node_id);

CREATE INDEX IF NOT EXISTS idx_legal_chunks_fine_range 
ON legal_chunks (min_fine_vnd, max_fine_vnd) 
WHERE min_fine_vnd IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_legal_chunks_temporal_active 
ON legal_chunks (effective_date, expiration_date, is_active);

CREATE INDEX IF NOT EXISTS idx_runtime_cache_hash ON runtime_knowledge_cache (query_hash);
CREATE INDEX IF NOT EXISTS idx_runtime_cache_status_exp ON runtime_knowledge_cache (validation_status, expires_at);

-- ============================================================================
-- 4. VIETNAMESE FULL-TEXT SEARCH CONFIGURATION & TRIGGERS
-- ============================================================================

DO $$ BEGIN
    CREATE TEXT SEARCH CONFIGURATION vietnamese_legal (COPY = pg_catalog.simple);
    ALTER TEXT SEARCH CONFIGURATION vietnamese_legal
        ALTER MAPPING FOR word, asciiword, hword, asciihword
        WITH unaccent, simple;
EXCEPTION
    WHEN duplicate_object THEN null;
    WHEN others THEN null;
END $$;

CREATE OR REPLACE FUNCTION update_legal_chunks_tsv() 
RETURNS TRIGGER AS $$
BEGIN
    NEW.tsv_vi := 
        setweight(to_tsvector('vietnamese_legal', unaccent(COALESCE(NEW.chunk_index, ''))), 'A') ||
        setweight(to_tsvector('vietnamese_legal', unaccent(COALESCE(NEW.lead_sentence, ''))), 'B') ||
        setweight(to_tsvector('vietnamese_legal', unaccent(COALESCE(NEW.verbatim_text, ''))), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_legal_chunks_tsv_update ON legal_chunks;
CREATE TRIGGER trg_legal_chunks_tsv_update
BEFORE INSERT OR UPDATE OF chunk_index, lead_sentence, verbatim_text ON legal_chunks
FOR EACH ROW EXECUTE FUNCTION update_legal_chunks_tsv();

CREATE INDEX IF NOT EXISTS idx_legal_chunks_tsv_vi ON legal_chunks USING gin (tsv_vi);

CREATE OR REPLACE FUNCTION update_sign_catalog_tsv() 
RETURNS TRIGGER AS $$
BEGIN
    NEW.tsv_sign := 
        setweight(to_tsvector('vietnamese_legal', unaccent(COALESCE(NEW.sign_code, ''))), 'A') ||
        setweight(to_tsvector('vietnamese_legal', unaccent(COALESCE(NEW.sign_name, ''))), 'A') ||
        setweight(to_tsvector('vietnamese_legal', unaccent(COALESCE(NEW.meaning, ''))), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sign_catalog_tsv_update ON sign_catalog;
CREATE TRIGGER trg_sign_catalog_tsv_update
BEFORE INSERT OR UPDATE OF sign_code, sign_name, meaning ON sign_catalog
FOR EACH ROW EXECUTE FUNCTION update_sign_catalog_tsv();

CREATE INDEX IF NOT EXISTS idx_sign_catalog_tsv_vi ON sign_catalog USING gin (tsv_sign);
