-- Column-limited server reads for reviewed profile and runtime summaries.

BEGIN;

SET LOCAL search_path = agro, pg_catalog;

GRANT SELECT (id, allocation_id, title, status)
ON TABLE agro_work_items TO agro_vc_runtime;

GRANT SELECT (allocation_id, observed_at, received_at, actor_id, status, created_at)
ON TABLE agro_field_signals TO agro_vc_runtime;

COMMIT;
