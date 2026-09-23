-- Migration 021: Add first-class statutory line span coordinates to chunks table
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS start_line INT NOT NULL DEFAULT 1;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS end_line INT NOT NULL DEFAULT 1;
CREATE INDEX IF NOT EXISTS idx_chunks_line_spans ON chunks (document_id, start_line, end_line);
