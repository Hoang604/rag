-- src/rag_eval/legal/db/sql/011_contract_and_cleanup.sql

-- 1. Xóa bỏ bảng cũ sau khi toàn bộ code đã chuyển sang chunk_context_refs
DROP TABLE IF EXISTS chunk_dangling_dependencies CASCADE;

-- 2. Xóa bỏ các stored procedure overload cũ (bản 3-param và 6-param)
DROP FUNCTION IF EXISTS traverse_knowledge_graph(UUID, TEXT, INT);
DROP FUNCTION IF EXISTS hybrid_search(TEXT, VECTOR, DATE, INT, INT, TEXT[]);
DROP FUNCTION IF EXISTS verbatim_grep(TEXT, TEXT[], BOOLEAN, BOOLEAN, DATE, INT);
DROP FUNCTION IF EXISTS verbatim_grep_count(TEXT, TEXT[], BOOLEAN, BOOLEAN, DATE);
