# Fortune pilot launch checklist

## What is ready

- The internal farm operating kernel, evidence/import flows, manager and field
  surfaces, controlled learning records, and private `agro_*` Postgres adapter.
- A shared Fortune pilot gate: set `FFL_LAUNCH_PASSWORD` only in the private
  runtime. It issues a signed twelve-hour browser session and protects every
  FFL API and surface except health, static assets, login, and the separately
  authenticated LoopMessage webhook.

## Required before a real Fortune URL

1. Run the pilot web/API on Vercel HTTPS. Set `FFL_DATABASE_URL` to the
   reviewed Supabase **transaction-pooler** DSN for the least-privilege
   `agro_vc_runtime` role, plus `FFL_POSTGRES_SCHEMA=agro`,
   `FFL_LAUNCH_PASSWORD`, `FFL_LAUNCH_COOKIE_SECURE=true`, and
   `FFL_PUBLIC_ORIGIN=https://www.agroceo.co` in Vercel's encrypted Production
   environment. Do not put any of these in browser configuration or git.
2. Configure private durable evidence storage. `/tmp/ffl-evidence` is only a
   local/test fallback and is not a launch-grade evidence store.
3. Create the real Fortune operating unit, people, blocks, rights, current
   season, allocations, owners, and signal templates. Do not seed fictional
   pilot data into the live database.
4. Confirm backup/restore, server health alerts, and a named operating owner.
5. Give the shared pilot password only to the small Fortune team. Replace it
   when the pilot group changes; changing it invalidates existing sessions.

## Deliberately not a launch requirement

- IMD/Village Finder access, market/satellite context, and AI extraction.
- LoopMessage: it remains disabled until its separate sender, consent,
  WhatsApp sandbox-proof, worker, and privacy gates are completed.

## Next access-control milestone

Replace the shared pilot gate with named Fortune accounts and role-scoped
permissions before onboarding a wider field network. The shared password is a
small internal-launch control, not an audit identity.
