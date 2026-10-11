-- src/rag_eval/legal/db/sql/015_drop_edge_origin.sql
-- Một loại cạnh duy nhất: ai tạo hay gỡ cạnh chỉ là lịch sử, ghi ở graph_edge_log.actor.

ALTER TABLE graph_edges DROP COLUMN origin;
