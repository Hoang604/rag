-- src/rag_eval/legal/db/sql/008_relation_types_and_zero_defaults.sql

-- 1. Bảng danh mục quan hệ pháp lý chuẩn mực Việt Nam
CREATE TABLE IF NOT EXISTS relation_types (
    code VARCHAR(32) PRIMARY KEY,
    description TEXT NOT NULL,
    is_symmetric BOOLEAN NOT NULL
);

INSERT INTO relation_types (code, description, is_symmetric) VALUES
    ('MODIFIES_AND_REPLACES', 'Sửa đổi, bổ sung hoặc bãi bỏ quy phạm khác', FALSE),
    ('SANCTIONS', 'Xử phạt, chế tài hoặc áp dụng biện pháp khắc phục hậu quả', FALSE),
    ('OVERRIDES', 'Quy tắc ưu tiên áp dụng (Luật chuyên ngành áp đảo luật chung)', FALSE),
    ('EXEMPTS', 'Trường hợp ngoại lệ, miễn trừ trách nhiệm pháp lý', FALSE),
    ('GUIDES', 'Quy định chi tiết hoặc hướng dẫn thi hành điều khoản', FALSE),
    ('DEFINES_TERM', 'Giải thích từ ngữ, định nghĩa khái niệm pháp lý', FALSE),
    ('REFERENCES', 'Viện dẫn, tham chiếu kỹ thuật trung lập đến điều khoản khác', FALSE),
    ('CONFLICTS_WITH', 'Quy định mâu thuẫn hoặc xung đột hiệu lực', TRUE),
    ('SEE_ALSO', 'Liên kết tham khảo ngữ cảnh liên quan', TRUE)
ON CONFLICT (code) DO UPDATE SET
    description = EXCLUDED.description,
    is_symmetric = EXCLUDED.is_symmetric;

-- 2. Triệt tiêu toàn bộ DEFAULT trên bảng documents và chunks (Kể cả ID)
ALTER TABLE documents ALTER COLUMN id DROP DEFAULT;
ALTER TABLE documents ALTER COLUMN metadata DROP DEFAULT;
ALTER TABLE documents ALTER COLUMN created_at DROP DEFAULT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;
UPDATE documents SET updated_at = created_at WHERE updated_at IS NULL;
ALTER TABLE documents ALTER COLUMN updated_at SET NOT NULL;

ALTER TABLE chunks ALTER COLUMN id DROP DEFAULT;
ALTER TABLE chunks ALTER COLUMN metadata DROP DEFAULT;
ALTER TABLE chunks ALTER COLUMN start_line DROP DEFAULT;
ALTER TABLE chunks ALTER COLUMN end_line DROP DEFAULT;
ALTER TABLE chunks ALTER COLUMN finalization_state DROP DEFAULT;
ALTER TABLE chunks ALTER COLUMN created_at DROP DEFAULT;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;
UPDATE chunks SET updated_at = created_at WHERE updated_at IS NULL;
ALTER TABLE chunks ALTER COLUMN updated_at SET NOT NULL;

-- 3. Ràng buộc hình học và chỉ mục mới
ALTER TABLE chunks DROP CONSTRAINT IF EXISTS chk_chunks_line_spans;
ALTER TABLE chunks ADD CONSTRAINT chk_chunks_line_spans CHECK (end_line >= start_line AND start_line >= 1);
CREATE INDEX IF NOT EXISTS idx_documents_metadata ON documents USING gin (metadata jsonb_path_ops);

-- 4. Đồng bộ kiểu dữ liệu graph_edges.relation_type, chuẩn hóa target_chunk_id NOT NULL
ALTER TABLE graph_edges ALTER COLUMN id DROP DEFAULT;
ALTER TABLE graph_edges ALTER COLUMN metadata DROP DEFAULT;
ALTER TABLE graph_edges ALTER COLUMN created_at DROP DEFAULT;
ALTER TABLE graph_edges ALTER COLUMN relation_type TYPE VARCHAR(32);
ALTER TABLE graph_edges DROP CONSTRAINT IF EXISTS fk_graph_edges_relation;
ALTER TABLE graph_edges ADD CONSTRAINT fk_graph_edges_relation FOREIGN KEY (relation_type) REFERENCES relation_types(code);

-- Xóa các cạnh rác hoặc cạnh ngoài cũ trước khi đặt NOT NULL
DELETE FROM graph_edges WHERE target_chunk_id IS NULL;
ALTER TABLE graph_edges ALTER COLUMN target_chunk_id SET NOT NULL;
ALTER TABLE graph_edges DROP COLUMN IF EXISTS target_external_ref;

ALTER TABLE graph_edges DROP CONSTRAINT IF EXISTS chk_graph_edges_no_self_loop;
ALTER TABLE graph_edges ADD CONSTRAINT chk_graph_edges_no_self_loop CHECK (target_chunk_id != source_chunk_id);

ALTER TABLE graph_edges DROP CONSTRAINT IF EXISTS uq_graph_edges;
ALTER TABLE graph_edges ADD CONSTRAINT uq_graph_edges UNIQUE (source_chunk_id, target_chunk_id, relation_type);
