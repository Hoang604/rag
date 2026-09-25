-- ============================================================================
-- Migration 023: Statutory Finalization State & Dangling Dependency Registry
-- ============================================================================

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'chunks' AND column_name = 'finalization_state'
    ) THEN
        ALTER TABLE chunks ADD COLUMN finalization_state VARCHAR(32) NOT NULL DEFAULT 'UNFINALIZED_OPEN_ENDED';
        ALTER TABLE chunks ADD CONSTRAINT chk_chunks_finalization_state CHECK (
            finalization_state IN (
                'FINALIZED_SELF_CONTAINED',
                'FINALIZED_FULLY_LINKED',
                'UNFINALIZED_PENDING_EXTERNAL',
                'UNFINALIZED_OPEN_ENDED'
            )
        );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_chunks_finalization_state ON chunks (finalization_state);

CREATE TABLE IF NOT EXISTS chunk_dangling_dependencies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id UUID NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    dependency_text TEXT NOT NULL,
    dependency_type VARCHAR(32) NOT NULL DEFAULT 'OPEN_ENDED',
    suggested_target_doc TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_dependency_type CHECK (
        dependency_type IN ('OPEN_ENDED', 'EXTERNAL_CITATION')
    )
);

CREATE INDEX IF NOT EXISTS idx_chunk_dangling_deps_chunk ON chunk_dangling_dependencies (chunk_id);
CREATE INDEX IF NOT EXISTS idx_chunk_dangling_deps_type ON chunk_dangling_dependencies (dependency_type);
