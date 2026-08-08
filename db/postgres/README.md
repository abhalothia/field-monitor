# FFL PostgreSQL bootstrap

`0001_agro_private_schema.sql` is the private relational contract for FFL's
Postgres adapter. It is intentionally **not** run by the API or worker.

Before applying it, confirm the exact project and use a reviewed migration role.
The migration creates the private `agro` schema; it must not be exposed through
Supabase's Data API. Create a dedicated, least-privilege server/worker role
afterward. Never put its connection string or a Supabase service-role key in
browser code, Vercel previews, fixtures, or git.

The server-side adapter maps the existing repository vocabulary to the
``agro_*`` relations and normalises placeholders, JSONB values, and primitive
rows. SQLite remains the disposable test/preview target. Configure
`FFL_DATABASE_URL` only in the private Hetzner runtime after the schema is
present; Vercel previews must not receive a production DSN. The application
never applies this migration itself.

`0007_agro_field_capture.sql` follows the TrackOlap source-record migration
(`0006`) and adds the private native field-capture pass/candidate ledger. It
does not enable a browser identity, upload endpoint, public Data API, or
provider integration by itself.

`0009_agro_trackwick_private_spatial_evidence.sql` adds the private typed
TrackWick CRM/evidence graph. It enables PostGIS in Supabase's `extensions`
schema and stores only source points—not farm polygons. Apply it with the
direct migration connection, never the Vercel transaction pooler. Its tables
remain outside Supabase's Data API and require an accountable Fortune manager
before the source refresh can run.

`0010_agro_named_access.sql` adds application owners/admins independently of
operational roles or Supabase user metadata. Pending memberships have no email
or Auth subject and cannot authenticate merely because their name is present.

`0011_agro_trackwick_media_origin_check.sql` repairs the original TrackWick
media-host constraint to accept the one explicitly approved S3 prefix. Apply
it after `0009`; it does not broaden the origin allow-list or copy any image.

`0021_agro_communications_control_plane.sql` adds the private, portal/person-
scoped communications profile, endpoint verification, operating-scope, and
append-only scoped-consent foundation. It does not enable WhatsApp traffic,
infer authority from a phone number, expose `agro` through the Data API, or
grant browser/runtime privileges. Apply it only after the customer portal and
person operating relationship migrations are present.

`0023_agro_operating_classification_spine.sql` adds the private, deterministic
place dictionary and task-type taxonomy used by the cached operating record.
It also extends the existing snapshot with place coverage, crop profile, and
latest activity type. It does not create or merge identities, infer a field
boundary, expose raw task labels, or make diagnostic claims. Apply it with the
direct migration connection, then run `scripts/backfill_operating_snapshots.py`
once; future source imports refresh the same facts atomically.

`0024_agro_place_operating_summaries.sql` adds a compact private rollup for
each reported place. It powers fast map and directory context with counts of
reported farms, connected farmers/workers, work, activity, and recorded
evidence. A task is counted only against places connected to its reported
farmer; the rollup never claims that a task happened inside a legal field
boundary. Apply it after `0023` and run the same snapshot backfill once.

`0025_agro_operating_vocabulary_registry.sql` adds a private, versioned
dictionary for the small vocabulary that repeats across source imports: task
labels, source-reported issues, and crop-product spellings. Imports discover
terms automatically without calling a model. After applying the migration with
the direct migration connection, run `scripts/enrich_operating_vocabulary.py`
to populate the dictionary. A deliberate `--apply` run can ask the configured
server-only Gemini Flash-Lite model for bounded spelling/casing/translation
suggestions. It uses `GEMINI_API_KEY` and remains optional. Those suggestions
remain `suggested` until reviewed and never change facts, boundaries, identities,
or browser-visible filters on their own.
