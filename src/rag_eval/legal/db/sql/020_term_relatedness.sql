-- Learned term relatedness, mined from the corpus rather than from users.
--
-- The plan gated this work on the overlay reaching PROMOTE, because the
-- intended signal was co-retrieval by real users. That gate is still shut and
-- measured shut: 40 annotations produced 28 topics against an 80-question set,
-- and only 8 words from 118 colloquial questions cleared a usable frequency
-- floor -- the top ones being interrogatives (`bao`, `thế`), not traffic terms.
--
-- So the signal here is a different one that does exist at scale: which words
-- occur together inside the same provision, over 7,093 provisions. That cannot
-- learn what users call things, and nothing in this table should be read as if
-- it could. What it can learn is which statutory words travel together, which
-- is enough to carry a query that lands on one of them toward the rest.
--
-- Kept in its own table rather than folded into `token_df` because the two
-- answer different questions and are rebuilt on different occasions: `token_df`
-- is one row per word, this is one row per ordered pair.

CREATE TABLE IF NOT EXISTS term_relatedness (
    term       TEXT             NOT NULL,
    related    TEXT             NOT NULL,
    score      DOUBLE PRECISION NOT NULL,
    -- How many provisions hold both. Kept so a reader can tell a pair supported
    -- by 400 provisions from one supported by the 8 that barely cleared the
    -- floor, which the score alone hides.
    pair_df    INTEGER          NOT NULL,
    PRIMARY KEY (term, related)
);

-- The only access pattern: given a query word, its strongest neighbours.
CREATE INDEX IF NOT EXISTS idx_term_relatedness_lookup
    ON term_relatedness (term, score DESC);
