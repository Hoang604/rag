-- ============================================================================
-- Migration 024: Add raw_text to documents table for post-promotion hydration
-- ============================================================================

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'documents' AND column_name = 'raw_text'
    ) THEN
        ALTER TABLE documents ADD COLUMN raw_text TEXT;
    END IF;
END $$;
