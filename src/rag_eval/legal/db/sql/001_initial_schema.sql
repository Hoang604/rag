CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";
CREATE EXTENSION IF NOT EXISTS "ltree";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "unaccent";

DO $$ BEGIN
    CREATE TEXT SEARCH CONFIGURATION vietnamese_legal (COPY = pg_catalog.simple);
    ALTER TEXT SEARCH CONFIGURATION vietnamese_legal
        ALTER MAPPING FOR word, asciiword, hword, asciihword
        WITH unaccent, simple;
EXCEPTION
    WHEN duplicate_object THEN null;
    WHEN others THEN null;
END $$;

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_code VARCHAR(128) NOT NULL UNIQUE,
    title TEXT NOT NULL,
    effective_date DATE NOT NULL,
    expiration_date DATE,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_documents_dates CHECK (expiration_date IS NULL OR expiration_date >= effective_date)
);

CREATE INDEX IF NOT EXISTS idx_documents_code ON documents (doc_code);
CREATE INDEX IF NOT EXISTS idx_documents_dates ON documents (effective_date, expiration_date);

CREATE TABLE IF NOT EXISTS chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    path LTREE NOT NULL UNIQUE,
    verbatim_text TEXT NOT NULL,
    contextualized_text TEXT NOT NULL,
    embedding VECTOR(384),
    tsv_content TSVECTOR,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    effective_date DATE NOT NULL,
    expiration_date DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_chunks_dates CHECK (expiration_date IS NULL OR expiration_date >= effective_date)
);

CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
CREATE INDEX IF NOT EXISTS idx_chunks_path_gist ON chunks USING gist (path);
CREATE INDEX IF NOT EXISTS idx_chunks_path_btree ON chunks (path);
CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON chunks USING gin (tsv_content);
CREATE INDEX IF NOT EXISTS idx_chunks_verbatim_trgm ON chunks USING gin (verbatim_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_chunks_context_trgm ON chunks USING gin (contextualized_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_chunks_metadata ON chunks USING gin (metadata jsonb_path_ops);
CREATE INDEX IF NOT EXISTS idx_chunks_temporal ON chunks (effective_date, expiration_date);

CREATE OR REPLACE FUNCTION update_chunks_tsv() 
RETURNS TRIGGER AS $$
BEGIN
    NEW.tsv_content := 
        setweight(to_tsvector('vietnamese_legal', COALESCE(NEW.contextualized_text, '')), 'A') ||
        setweight(to_tsvector('vietnamese_legal', COALESCE(NEW.verbatim_text, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_chunks_tsv_update ON chunks;
CREATE TRIGGER trg_chunks_tsv_update
BEFORE INSERT OR UPDATE OF contextualized_text, verbatim_text ON chunks
FOR EACH ROW EXECUTE FUNCTION update_chunks_tsv();

CREATE TABLE IF NOT EXISTS graph_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_chunk_id UUID NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    target_chunk_id UUID REFERENCES chunks(id) ON DELETE SET NULL,
    target_external_ref TEXT,
    relation_type VARCHAR(64) NOT NULL,
    citation_text TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_graph_edges UNIQUE NULLS NOT DISTINCT (source_chunk_id, target_chunk_id, relation_type)
);

CREATE INDEX IF NOT EXISTS idx_graph_edges_source ON graph_edges (source_chunk_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_target ON graph_edges (target_chunk_id);
CREATE INDEX IF NOT EXISTS idx_graph_edges_relation ON graph_edges (relation_type);
