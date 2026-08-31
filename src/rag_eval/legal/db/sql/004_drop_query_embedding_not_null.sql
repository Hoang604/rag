-- ============================================================================
-- MIGRATION 004: DROP NOT NULL CONSTRAINT ON RUNTIME KNOWLEDGE CACHE EMBEDDING
-- ============================================================================
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'runtime_knowledge_cache' AND column_name = 'query_embedding'
    ) THEN
        ALTER TABLE runtime_knowledge_cache ALTER COLUMN query_embedding DROP NOT NULL;
    END IF;
END $$;
