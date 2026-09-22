-- ----------------------------------------------------------------------------
-- LEARNED OVERLAY: THE FIVE MECHANISMS, AND WHY EACH ONE IS LOAD-BEARING
--
-- The overlay lets what an agent found last time make the same provision
-- easier to find next time. That is ordinary relevance feedback, and on this
-- corpus it should work well: the query distribution repeats heavily -- "mức
-- phạt X" asked a hundred ways -- so a confirmed answer pays off often.
--
-- It is also the one feature here that can make the system permanently wrong.
-- A boosted chunk is easier to find, so it gets annotated again, so it is
-- boosted harder; a correct provision that was never surfaced stays invisible.
-- The version that matters for law is worse than a ranking bug: an agent
-- records "Điều 6 answers this", the article is later superseded, and the
-- system now amplifies a repealed answer -- and the longer it runs the more
-- entrenched that becomes.
--
-- Five mechanisms, none optional (§4.4 of the feasibility report):
--
--   1. Append-only, versioned. `annotations` is insert-only and every built
--      weight records the build that produced it, so an evaluation can be
--      replayed against the exact overlay state it ran on. Without this the
--      index changes underneath the measurement and no number reproduces.
--
--   2. Promotion gate. An annotation is a hypothesis, not a fact -- it is the
--      agent's belief that it looked in the right place. Nothing reaches
--      ranking until it is verified, by grep confirming the quoted text, by
--      independent sessions agreeing, or by a person.
--
--   3. Exploration. Applied at query time: a fraction of searches ignore the
--      overlay entirely, so provisions that were never surfaced still get
--      their chance to be. Without it the first answer found wins forever.
--
--   4. Decay. Weight falls off with age, so a year-old annotation cannot
--      outvote what the corpus says today.
--
--   5. Effectiveness invalidation. A weight pointing at a provision that has
--      expired is dropped, not decayed. This is the correctness mechanism:
--      the other four are about ranking quality, this one is about not citing
--      repealed law.
--
-- The weight is keyed by topic rather than applied to the chunk globally. The
-- claim being recorded is "this provision answers this kind of question", not
-- "this provision is generally good", and the second is both weaker and more
-- dangerous.
-- ----------------------------------------------------------------------------

-- Mechanism 2: a hypothesis carries its provenance and stays out of ranking
-- until something independent confirms it.
ALTER TABLE annotations
    ADD COLUMN IF NOT EXISTS verified BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS verified_by VARCHAR(32),
    ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ;

ALTER TABLE annotations
    DROP CONSTRAINT IF EXISTS chk_annotations_verified_by;
ALTER TABLE annotations
    ADD CONSTRAINT chk_annotations_verified_by
        CHECK (verified_by IS NULL OR verified_by IN ('grep', 'consensus', 'human'));

CREATE INDEX IF NOT EXISTS idx_annotations_verified
    ON annotations (verified) WHERE verified;

-- Mechanism 1: the built state, addressable by version.
CREATE TABLE IF NOT EXISTS overlay_weights (
    topic_fingerprint TEXT NOT NULL,
    chunk_id          UUID NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    -- A multiplier applied on top of the fused score. Bounded well below the
    -- facet bonuses: this is evidence about one past question, not about what
    -- the statute says, and it must never be able to override retrieval.
    weight            DOUBLE PRECISION NOT NULL,
    supporting        INTEGER NOT NULL,
    build_version     INTEGER NOT NULL,
    built_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (build_version, topic_fingerprint, chunk_id),
    CONSTRAINT chk_overlay_weight_bounds CHECK (weight > 0.0 AND weight <= 0.25),
    CONSTRAINT chk_overlay_supporting CHECK (supporting >= 1)
);

CREATE INDEX IF NOT EXISTS idx_overlay_lookup
    ON overlay_weights (build_version, topic_fingerprint);

-- Which build a search should consult. Empty means the overlay is off, which
-- is the state it ships in until an on/off experiment says otherwise.
CREATE TABLE IF NOT EXISTS overlay_active (
    id            BOOLEAN PRIMARY KEY DEFAULT TRUE,
    build_version INTEGER,
    activated_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    note          TEXT,

    CONSTRAINT chk_overlay_active_singleton CHECK (id)
);

INSERT INTO overlay_active (id, build_version, note)
VALUES (TRUE, NULL, 'Mặc định tắt: chờ thí nghiệm bật/tắt ở Sprint 3')
ON CONFLICT (id) DO NOTHING;
