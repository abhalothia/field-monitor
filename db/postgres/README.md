# FFL PostgreSQL bootstrap

`0001_ffl_private_schema.sql` is the target relational contract for a future
FFL Postgres adapter. It is intentionally **not** run by the API or worker.

Before applying it, confirm the exact project and use a reviewed migration role.
The migration creates the private `ffl` schema; it must not be exposed through
Supabase's Data API. Create a dedicated, least-privilege server/worker role
afterward. Never put its connection string or a Supabase service-role key in
browser code, Vercel previews, fixtures, or git.

At present, the running FFL repository is SQLite-specific. Setting
`FFL_DATABASE_URL=postgresql://...` therefore fails closed with an actionable
error rather than falling back to SQLite. The follow-up adapter must translate
query placeholders, transaction/error semantics, JSONB values, timestamp/date
serialization, and the SQLite-only migrations before this bootstrap can become
the authoritative database.
