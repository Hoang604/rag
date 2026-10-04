-- src/rag_eval/legal/db/sql/009_chunk_context_refs_and_span_grounding.sql

-- 1. Bảng lưu trữ chi tiết tham chiếu ngữ cảnh có tọa độ ký tự chính xác (Zero Defaults)
CREATE TABLE IF NOT EXISTS chunk_context_refs (
    id UUID PRIMARY KEY,
    chunk_id UUID NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    char_start INT,
    char_end INT,
    citation_phrase TEXT,
    target_chunk_id UUID REFERENCES chunks(id) ON DELETE SET NULL,
    edge_id UUID REFERENCES graph_edges(id) ON DELETE SET NULL,
    target_path VARCHAR(500),
    suggested_doc_code VARCHAR(128),
    dependency_type VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT chk_ref_span_geometry CHECK (
        (char_start IS NULL AND char_end IS NULL) OR
        (char_start IS NOT NULL AND char_end IS NOT NULL AND char_end > char_start AND char_start >= 0)
    ),
    CONSTRAINT chk_ref_no_self_loop CHECK (target_chunk_id IS NULL OR target_chunk_id != chunk_id),
    CONSTRAINT chk_ref_dependency_type CHECK (dependency_type IN ('OPEN_ENDED', 'EXTERNAL_CITATION', 'INTERNAL_REFERENCE'))
);

CREATE INDEX IF NOT EXISTS idx_chunk_refs_chunk_id ON chunk_context_refs (chunk_id);
CREATE INDEX IF NOT EXISTS idx_chunk_refs_target_id ON chunk_context_refs (target_chunk_id);
CREATE INDEX IF NOT EXISTS idx_chunk_refs_edge_id ON chunk_context_refs (edge_id);

-- 2. Sao chép dữ liệu từ chunk_dangling_dependencies sang chunk_context_refs
INSERT INTO chunk_context_refs (
    id, chunk_id, char_start, char_end, citation_phrase, target_chunk_id, edge_id,
    target_path, suggested_doc_code, dependency_type, created_at
)
SELECT 
    id, chunk_id, NULL, NULL, dependency_text, NULL, NULL,
    NULL, suggested_target_doc, dependency_type, created_at
FROM chunk_dangling_dependencies
ON CONFLICT (id) DO NOTHING;
