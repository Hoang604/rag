-- metadata was written as a JSON string through a jsonb codec that encodes again, so every row held a
-- jsonb string scalar ('"{\"amends\": ...}"') and `metadata->>'amends'` returned NULL. Store the object itself.
UPDATE documents SET metadata = (metadata #>> '{}')::jsonb WHERE jsonb_typeof(metadata) = 'string';
UPDATE chunks SET metadata = (metadata #>> '{}')::jsonb WHERE jsonb_typeof(metadata) = 'string';

ALTER TABLE documents ADD CONSTRAINT documents_metadata_is_object CHECK (jsonb_typeof(metadata) = 'object');
ALTER TABLE chunks ADD CONSTRAINT chunks_metadata_is_object CHECK (jsonb_typeof(metadata) = 'object');
