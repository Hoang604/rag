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

UPDATE chunks SET verbatim_text = verbatim_text
WHERE verbatim_text ~ '[[:alpha:]]{3}[[:digit:]]';
