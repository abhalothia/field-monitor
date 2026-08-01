# FFL external-data roadmap

## Phase 1 — reference geography and first-party evidence

- Import a pinned, reviewed India Village Finder release for Andhra Pradesh,
  Telangana, Karnataka, Tamil Nadu, or Kerala.
- Retain LGD codes, parent hierarchy, PIN, native display name, its provenance,
  source URL, SHA-256, and GODL-India attribution. A PIN is an address hint,
  never a field coordinate; exact latitude/longitude remains an FFL
  field-observation/geometry record with its own accuracy and consent.
- Bind an FFL operating unit only after a manager selects the exact village.
- Retain soil-lab files as FFL evidence and publish reviewed measurements; lab
  evidence remains more authoritative than any public soil model.

## Phase 2 — official operational context

- Add only the IMD adapter after access review, fixed Hetzner egress/IP
  whitelisting, an official endpoint allow-list, and district mapping.
- Normalise warnings, nowcasts, forecasts, observations, and agromet bulletin
  references into a deduplicated source-run ledger.
- A source result may create a manager-visible watch. It does not complete work,
  publish agronomy, or make a farm decision.

## Phase 3 — reviewed contextual enrichment

- Keep AGMARKNET, Copernicus, Bhuvan, SoilGrids, and myScheme in the source
  catalog with their own owner, licence, coverage, freshness, and admission
  gate. They are disabled by default.
- Admit one provider at a time only after an adapter, source-specific tests,
  and a clear product use case exist. Public/model context never overwrites FFL
  primary evidence.

## Supabase boundary

- The geography extension depends on the canonical FFL `source_registry` and
  `source_runs` records created by `0001_ffl_private_schema.sql`; it does not
  create a second source ledger.
- FFL uses the private `ffl` schema and a separately reviewed least-privilege
  runtime role only.
- `ffl.ext_*` tables are revoked from `public`, `anon`, and `authenticated`;
  no FFL relation is added to another application's schema or table namespace.
- Apply `0001_ffl_private_schema.sql`, then `0100_ffl_external_data.sql`, with
  `FFL_DATABASE_URL` as a direct or session-pooler Postgres URL. Supabase
  publishable/secret API keys are not database migration credentials and never
  belong in a browser or Git.
