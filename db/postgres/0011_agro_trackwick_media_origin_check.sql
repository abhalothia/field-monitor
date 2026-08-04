-- Repair the 0009 TrackWick media-origin check. PostgreSQL regular-expression
-- escaping made the original literal reject the exact approved S3 origin.
-- The normaliser canonicalises URLs to this prefix before they reach storage.

BEGIN;

SET LOCAL search_path = agro, pg_catalog;

ALTER TABLE agro_trackwick_media_references
    DROP CONSTRAINT IF EXISTS agro_trackwick_media_references_remote_url_check;

ALTER TABLE agro_trackwick_media_references
    ADD CONSTRAINT agro_trackwick_media_references_remote_url_check
    CHECK (remote_url LIKE 'https://trackolap-images-prod.s3.amazonaws.com/%');

COMMIT;
