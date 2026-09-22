-- ----------------------------------------------------------------------------
-- MATCH THE OVERLAY BY WHAT A QUESTION SHARES, NOT BY WHETHER IT IS IDENTICAL
--
-- The first two versions keyed on an exact hash: first of every content word,
-- then of the four rarest. Both were tested against real paraphrases of one
-- question and both failed the same way.
--
--   "xe máy vượt đèn đỏ phạt bao nhiêu"
--   "vượt đèn đỏ với xe máy bị xử lý thế nào"
--
-- Same offence, same provision, different key -- because "xử lý" displaced
-- "phạt" among the rarest four. An overlay that only fires on a question asked
-- again in the same words fires almost never, and measuring it would have
-- produced an honest zero for a mechanism that was never given a chance.
--
-- So the stored key is the token set itself, and a search matches on overlap:
-- most of what the annotation was about must appear in the question. That is
-- the same containment test the leakage guard uses, for the same reason -- the
-- relationship being detected is "these are about the same thing", and exact
-- equality is the wrong tool for it in both directions.
-- ----------------------------------------------------------------------------

ALTER TABLE overlay_weights
    ADD COLUMN IF NOT EXISTS topic_tokens TEXT[] NOT NULL DEFAULT '{}';

CREATE INDEX IF NOT EXISTS idx_overlay_tokens
    ON overlay_weights USING GIN (topic_tokens);

-- Returns the boost a chunk earns for a question, or 0. Split out of
-- hybrid_search so the matching rule has one definition and can be tested on
-- its own.
CREATE OR REPLACE FUNCTION overlay_boost(
    target_chunk UUID,
    query_tokens TEXT[],
    active_version INT,
    min_containment DOUBLE PRECISION DEFAULT 0.6
) RETURNS DOUBLE PRECISION AS $$
    SELECT COALESCE(max(o.weight), 0.0)
    FROM overlay_weights o
    WHERE active_version IS NOT NULL
      AND o.build_version = active_version
      AND o.chunk_id = target_chunk
      AND o.topic_tokens && query_tokens
      AND cardinality(o.topic_tokens) > 0
      AND (
            SELECT count(*) FROM unnest(o.topic_tokens) t
            WHERE t = ANY(query_tokens)
          )::DOUBLE PRECISION / cardinality(o.topic_tokens) >= min_containment;
$$ LANGUAGE sql STABLE;
