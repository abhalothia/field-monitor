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
