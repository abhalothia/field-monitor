# Task 9 report: FFL Vercel preview adapter

## Delivered

- Added `api/index.py`, which exports the existing `ffl.app.app` ASGI instance
  without defining a second application, route set, or configuration.
- Added `vercel.json` for the `api/index.py` function, a 10-second preview
  duration, packaged `ffl/static/**` files, and a catch-all rewrite.
- Made the default SQLite path `/tmp/ffl.db` only when `VERCEL` is set and
  `FFL_DATABASE_PATH` is absent. An explicit `FFL_DATABASE_PATH` still wins.
- Documented that the Vercel database is disposable and must never contain real
  FFL data.

## Verification

```text
.venv/bin/pytest -q tests/ffl/test_vercel_preview.py
2 passed

.venv/bin/pytest -q tests/ffl
25 passed

git diff --check
passed with no output
```

## Commit

`feat: add FFL Vercel preview adapter`

## Assumptions and limits

- This adapter is preview-only; `/tmp/ffl.db` is ephemeral function storage and
  not an operating record.
- Deployment was intentionally not performed.
- No legacy `src/`, `db/`, `dashboard/`, or `config/` modules were changed.
