-- ----------------------------------------------------------------------------
-- HOW COMMON EACH WORD IS IN THIS CORPUS
--
-- The overlay keys on what a question is about, and the first version keyed on
-- the exact set of its content words. That only ever matches a question asked
-- again in the same words, which is not what repeat traffic looks like: people
-- ask about running a red light in a dozen phrasings, and every one of them
-- produced a different key. The feature would have fired almost never and the
-- experiment measuring it would have shown nothing, correctly.
--
-- A stable key needs the distinctive words and not the ubiquitous ones. "Xe"
-- and "phạt" appear in most questions in this domain and carry no topic;
-- "đèn", "cồn", "vỉa hè" do. Which is which is a property of this corpus, not
-- something to assert by hand, so it is counted.
-- ----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS token_df (
    token TEXT PRIMARY KEY,
    df    INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_token_df_df ON token_df (df);
