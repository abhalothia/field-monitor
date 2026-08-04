-- Repair the least-privilege Vercel runtime role for the tables its existing
-- manager-only API already uses.  These privileges are server-side only: the
-- private ``agro`` schema remains outside Supabase's Data API and PUBLIC keeps
-- no access.  The role receives no DELETE, DDL, role-management, or schema
-- privileges.

BEGIN;

SET LOCAL search_path = agro, pg_catalog;

-- Portfolio/field capture read models and their append-only state changes.
GRANT SELECT, INSERT, UPDATE ON TABLE
    agro_field_capture_candidates,
    agro_field_capture_passes,
    agro_field_information_request_events,
    agro_field_information_requests
TO agro_vc_runtime;

-- The existing manager-only TrackWick refresh and operating board require the
-- typed source lane.  This does not grant a browser or the public Data API
-- access to contacts, exact locations, media URLs, or provider records.
GRANT SELECT, INSERT, UPDATE ON TABLE
    agro_trackolap_records,
    agro_trackwick_contact_points,
    agro_trackwick_crop_inputs,
    agro_trackwick_location_observations,
    agro_trackwick_media_references,
    agro_trackwick_parties,
    agro_trackwick_party_person_links,
    agro_trackwick_plot_operating_links,
    agro_trackwick_registration_plots,
    agro_trackwick_registrations,
    agro_trackwick_task_allocation_links,
    agro_trackwick_tasks,
    agro_trackwick_visit_findings,
    agro_trackwick_visits,
    agro_trackwick_worker_days
TO agro_vc_runtime;

COMMIT;
