ALTER TABLE graph_edge_log ADD CONSTRAINT chk_graph_edge_log_actor CHECK (actor IN ('INGEST', 'AGENT'));
