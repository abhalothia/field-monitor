-- Private, reviewed TrackWick CRM basics.  No public-schema grant is made.
-- The application stores a minimal allow-list only: names, opaque source IDs,
-- ownership, coarse location, reported acreage, crop timing, and work state.
-- Aadhaar, mobile, signature, photo, comment, and exact GPS never enter this table.

BEGIN;
SET LOCAL search_path = agro, pg_catalog;

ALTER TABLE agro_trackolap_records
    DROP CONSTRAINT IF EXISTS agro_trackolap_records_feed_check;

ALTER TABLE agro_trackolap_records
    ADD CONSTRAINT agro_trackolap_records_feed_check CHECK (feed IN (
        'officers', 'attendance', 'farmer_tasks', 'visits',
        'issue_observations', 'pesticide_events',
        'farmer_profiles', 'farm_candidates', 'field_workers',
        'crop_context', 'soil_context', 'follow_ups'
    ));

COMMIT;
