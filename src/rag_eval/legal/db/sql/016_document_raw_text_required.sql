-- src/rag_eval/legal/db/sql/016_document_raw_text_required.sql
-- Mọi văn bản đều được nạp kèm nguyên văn: câu chữ của chunk là lát cắt dòng của raw_text.

ALTER TABLE documents ALTER COLUMN raw_text SET NOT NULL;
