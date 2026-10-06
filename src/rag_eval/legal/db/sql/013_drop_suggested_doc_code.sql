-- src/rag_eval/legal/db/sql/013_drop_suggested_doc_code.sql
-- Xóa bỏ cột rác suggested_doc_code khỏi bảng chunk_context_refs

ALTER TABLE chunk_context_refs DROP COLUMN IF EXISTS suggested_doc_code;
