-- Every embedding ever computed, keyed by model, dimension and the exact text embedded,
-- so re-ingest and model comparisons reuse vectors instead of recomputing them.
CREATE TABLE embedding_cache (
    model TEXT NOT NULL,
    dim INT NOT NULL CHECK (dim > 0),
    text_sha256 TEXT NOT NULL,
    embedding VECTOR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (model, dim, text_sha256),
    CHECK (vector_dims(embedding) = dim)
);

INSERT INTO embedding_cache (model, dim, text_sha256, embedding, created_at)
SELECT 'Qwen/Qwen3-Embedding-0.6B', 512, encode(sha256(convert_to(contextualized_text, 'UTF8')), 'hex'), embedding, now()
FROM chunks
WHERE embedding IS NOT NULL
ON CONFLICT DO NOTHING;
