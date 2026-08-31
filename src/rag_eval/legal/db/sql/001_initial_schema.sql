-- ============================================================================
-- 1. EXTENSIONS
-- ============================================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";        -- pgvector v0.7+
CREATE EXTENSION IF NOT EXISTS "ltree";         -- Hierarchical label tree
CREATE EXTENSION IF NOT EXISTS "pg_trgm";       -- Trigram regex & fuzzy search
CREATE EXTENSION IF NOT EXISTS "unaccent";      -- Vietnamese unaccented text normalization

-- ============================================================================
-- 2. TEXT SEARCH CONFIGURATION
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

-- ============================================================================
-- 3. TABLE 1: documents (Statutory Legal Documents)
-- ============================================================================
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_code VARCHAR(128) NOT NULL UNIQUE,          -- e.g., "100/2019/NĐ-CP", "QCVN 41:2019/BGTVT"
    title TEXT NOT NULL,                            -- Full official document title
    effective_date DATE NOT NULL,                   -- Enactment effective date
    expiration_date DATE,                           -- Expiration date (NULL if currently active indefinitely)
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,    -- Extended metadata (doc_type, issuing_authority, signer, url)
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_documents_dates CHECK (expiration_date IS NULL OR expiration_date >= effective_date)
);

CREATE INDEX IF NOT EXISTS idx_documents_code ON documents (doc_code);
CREATE INDEX IF NOT EXISTS idx_documents_dates ON documents (effective_date, expiration_date);

-- ============================================================================
-- 4. TABLE 2: chunks (Atomic Statutory Chunks with Context Preservation)
-- ============================================================================
CREATE TABLE IF NOT EXISTS chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    path LTREE NOT NULL UNIQUE,                     -- e.g., "doc_100_2019_nd_cp.a5.c3.p_a"
    verbatim_text TEXT NOT NULL,                    -- Raw verbatim statutory clause/point text
    contextualized_text TEXT NOT NULL,              -- Full CPHC synthesized context text
    embedding VECTOR(384),                          -- Normalized dense vector (HNSW indexed)
    tsv_content TSVECTOR,                           -- Full-text search vector (Trigger updated)
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,    -- Dynamic semantic payload (fines, vehicles, norm_roles, exceptions)
    effective_date DATE NOT NULL,                   -- Temporal boundary effective date
    expiration_date DATE,                           -- Temporal boundary expiration date
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_chunks_dates CHECK (expiration_date IS NULL OR expiration_date >= effective_date)
);

-- Optimized Multi-Modal Indexes
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_chunks_path_gist ON chunks USING gist (path);
CREATE INDEX IF NOT EXISTS idx_chunks_path_btree ON chunks (path);
CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON chunks USING gin (tsv_content);
CREATE INDEX IF NOT EXISTS idx_chunks_verbatim_trgm ON chunks USING gin (verbatim_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_chunks_context_trgm ON chunks USING gin (contextualized_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_chunks_metadata ON chunks USING gin (metadata jsonb_path_ops);
CREATE INDEX IF NOT EXISTS idx_chunks_temporal ON chunks (effective_date, expiration_date);

-- Trigger for Automated Vietnamese TSVector Synchronization
CREATE OR REPLACE FUNCTION update_chunks_tsv() 
RETURNS TRIGGER AS $$
BEGIN
    NEW.tsv_content := 
        setweight(to_tsvector('vietnamese_legal', regexp_replace(unaccent(COALESCE(NEW.contextualized_text, '')), '[/]', ' ', 'g')), 'A') ||
        setweight(to_tsvector('vietnamese_legal', regexp_replace(unaccent(COALESCE(NEW.verbatim_text, '')), '[/]', ' ', 'g')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_chunks_tsv_update ON chunks;
CREATE TRIGGER trg_chunks_tsv_update
BEFORE INSERT OR UPDATE OF contextualized_text, verbatim_text ON chunks
FOR EACH ROW EXECUTE FUNCTION update_chunks_tsv();

-- ============================================================================
-- 5. TABLE 3: graph_edges (Relational Knowledge Graph Edges)
-- ============================================================================
CREATE TABLE IF NOT EXISTS graph_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_chunk_id UUID NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    target_chunk_id UUID REFERENCES chunks(id) ON DELETE SET NULL, -- Nullable for external unresolved citations
    target_external_ref TEXT,                      -- Target citation string if target not yet ingested
    relation_type VARCHAR(64) NOT NULL,            -- "MODIFIES_AND_REPLACES", "REFERENCES", "SANCTIONS", "OVERRIDES", "EXEMPTS", "GUIDES", "DEFINES_TERM"
    citation_text TEXT,                            -- Verbatim statutory phrase declaring this relation
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,    -- Dynamic conditions, notes
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_graph_edges UNIQUE NULLS NOT DISTINCT (source_chunk_id, target_chunk_id, relation_type)
);

CREATE INDEX IF NOT EXISTS idx_graph_edges_source ON graph_edges (source_chunk_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_target ON graph_edges (target_chunk_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_relation ON graph_edges (relation_type);
