-- ----------------------------------------------------------------------------
-- SEPARATE FOOTNOTE MARKERS FROM THE WORDS THEY ARE STUCK TO, IN THE INDEX ONLY
--
-- The consolidated documents (văn bản hợp nhất) carry footnote reference
-- numbers as superscripts. Extraction flattens them into the text, so the
-- corpus holds "Bộ Xây dựng11", "đặc khu272", "để thi hành103" -- 114 chunks
-- across the three VBHN documents.
--
-- The retrieval cost is real and silent. The tokeniser sees "dựng11" as a
-- lexeme unrelated to "dựng", so a search for "Bộ Xây dựng" does not match the
-- clause that says exactly that. Nothing errors; the clause is simply absent
-- from the results.
--
-- Two decisions worth stating, because the obvious fix is worse than this one.
--
-- Only the index is changed, never `verbatim_text`. The marker is genuinely
-- in the official consolidated text, so showing it to a reader is faithful,
-- and rewriting citation text would break the grounding invariant that every
-- digit in a chunk exists in the source.
--
-- The digits are separated, not deleted. Deleting risks real loss: extraction
-- also drops spaces occasionally, so "Điều6" matches the same pattern, and
-- removing the 6 would erase an article number. Separating is safe in both
-- cases -- a footnote becomes "dựng 11", where the stray token is harmless,
-- and a lost space becomes "Điều 6", which is what it should have been.
--
-- Three letters are required before the digit so that licence classes (A1,
-- B2) and sign codes (P.118, M03b) are untouched. Verified against the corpus:
-- all 114 matches are footnote markers, none is content.
-- ----------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION unglue_footnote_markers(txt TEXT)
RETURNS TEXT AS $$
    SELECT regexp_replace(
        COALESCE(txt, ''), '([[:alpha:]]{3})([[:digit:]])', '\1 \2', 'g'
    );
$$ LANGUAGE sql IMMUTABLE;

CREATE OR REPLACE FUNCTION update_chunks_tsv()
RETURNS TRIGGER AS $$
BEGIN
    NEW.tsv_content :=
        setweight(
            to_tsvector(
                'vietnamese_legal',
                unglue_footnote_markers(COALESCE(NEW.contextualized_text, ''))
            ), 'A'
        ) ||
        setweight(
            to_tsvector(
                'vietnamese_legal',
                unglue_footnote_markers(COALESCE(NEW.verbatim_text, ''))
            ), 'B'
        );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Rebuild the index for rows already stored. The trigger fires on UPDATE of
-- these columns, so assigning them to themselves is enough.
UPDATE chunks SET verbatim_text = verbatim_text
WHERE verbatim_text ~ '[[:alpha:]]{3}[[:digit:]]';
