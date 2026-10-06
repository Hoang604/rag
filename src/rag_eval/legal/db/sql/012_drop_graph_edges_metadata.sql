-- src/rag_eval/legal/db/sql/012_drop_graph_edges_metadata.sql

ALTER TABLE graph_edges DROP COLUMN IF EXISTS metadata;
