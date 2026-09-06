-- ----------------------------------------------------------------------------
-- AGENT RELEVANCE FEEDBACK, KEPT OUT OF THE CORPUS
--
-- `add_metadata` records that a chunk answered a question the agent had to
-- hunt for. Sprint 3 evaluates an overlay built from this; the value of that
-- experiment depends entirely on the log having been running since Sprint 1,
-- because the data accumulates with use and cannot be reconstructed later.
--
-- It is a fourth table rather than a column on `chunks`, against the
-- three-table principle, for two reasons that outweigh it:
--
--   Reproducibility. Writing feedback into the corpus would make the index
--   change as it is measured -- run an evaluation twice and the second run
--   scores higher because the first one taught it. Held separately and read
--   only where asked for, retrieval stays a pure function of the corpus.
--
--   Withdrawability. If a split turns out contaminated, the annotations from
--   it must be deletable without touching statutory text.
--
-- Both fingerprints exist to keep evaluation honest. An agent that runs the
-- dev questions and records their answers has memorised the split, and no
-- checksum detects it: the sealed file is untouched, the index is what moved.
-- Consumers exclude by either fingerprint, so a padded or unaccented restating
-- of a held-out question cannot slip an annotation past the guard.
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS annotations (
    id                  UUID PRIMARY KEY,
    chunk_id            UUID NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    -- Kept in full so a contaminated split can be identified after the fact,
    -- not only blocked in advance.
    query_text          TEXT NOT NULL,
    -- Accents, case and punctuation folded away.
    query_fingerprint   TEXT NOT NULL,
    -- Content words only, sorted: survives filler and reordering.
    topic_fingerprint   TEXT NOT NULL,
    relation            VARCHAR(32) NOT NULL DEFAULT 'ANSWERS',
    note                TEXT,
    source              VARCHAR(32) NOT NULL DEFAULT 'agent',
    session_id          TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_annotations_relation
        CHECK (relation IN ('ANSWERS', 'RELEVANT', 'MISLEADING')),
    CONSTRAINT chk_annotations_query_text
        CHECK (length(trim(query_text)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_annotations_chunk ON annotations (chunk_id);
CREATE INDEX IF NOT EXISTS idx_annotations_query_fp ON annotations (query_fingerprint);
CREATE INDEX IF NOT EXISTS idx_annotations_topic_fp ON annotations (topic_fingerprint);
CREATE INDEX IF NOT EXISTS idx_annotations_created ON annotations (created_at);
