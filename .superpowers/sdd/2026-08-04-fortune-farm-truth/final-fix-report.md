# Fortune Farm Truth final-fix report

## Outcome

The final review wave is complete. All twelve review findings are addressed in
the application, private persistence layer, production migration, manager UI,
Next.js cutover, and executable regressions. Farm Truth remains a
manager-authorized bridge from private TrackWick evidence to reviewed canonical
records; it does not infer farms from farmer-wide task history, coverage data,
sample data, or source map points.

## Findings closed

| Area | Final correction | Regression evidence |
| --- | --- | --- |
| PostgreSQL values | Recursively normalize finite `Decimal` values before JSON serialization and browser-safe summaries. | `test_database_targets.py`, `test_farm_truth_service.py` |
| Runtime authority | Migration `0015` grants the runtime only the exact source reads, derived association writes, canonical inserts, and review-case columns it needs; reviewed links remain append-only and guarded against update/delete. | `test_vc_runtime_privileges.py`, `test_farm_truth_repository.py` |
| Plot provenance | A visit or open task supports a plot only through a valid explicit task/registration/plot association. Farmer-wide task reuse and spatial guessing are removed. | `test_farm_truth_service.py`, `test_farm_truth_repository.py` |
| Live association path | A configured TrackWick form key persists one bounded plot reference and reconciles it to the same farmer's completed registration only when one normalized Gata match exists. Delta refreshes can resolve older registrations; ambiguous matches fail closed. | `test_trackwick_integration.py` |
| Acceptance freshness | Acceptance locks and recomputes the registration, plot, association, task, and visit receipt inside the transaction. Source mutation after a UI refresh returns a conflict. | `test_farm_truth_repository.py`, `test_farm_truth_routes.py` |
| Concurrent acceptance | Request-body replay validation lives in the repository; unique reviewed-plot races become deterministic `409` responses without duplicate canonical writes. | `test_farm_truth_routes.py`, `test_farm_truth_repository.py` |
| Accepted replay | The normalized acceptance contract is persisted with the accepted case. An identical retry returns the established IDs even after the season expires or its dates change; a different body conflicts. | `test_farm_truth_repository.py`, `test_farm_truth_routes.py` |
| Current context | Refresh, list, detail, and new acceptance require a current season. A dedicated context endpoint lists real operating-unit/current-season pairs even before the first allocation exists. | `test_farm_truth_service.py`, `test_farm_truth_routes.py` |
| Owner Inbox | A dedicated authenticated Inbox endpoint returns only the acting manager's `needs_evidence` cases and stable reason codes. Late responses cannot restore data after lock/context invalidation. | `test_farm_truth_routes.py`, `manager_app_behavior_test.js` |
| Stable localization | API evidence, task, status, title, and reason values are stable codes. The manager maps them to complete English/Hindi copy, including Farm Truth accessible names. | `test_farm_truth_service.py`, `test_manager_assets.py`, `manager_app_behavior_test.js` |
| Honest manager state | Synthetic farms, people, weather, maps, and fallback names were removed. Canonical directories render honest empty states; aggregate source activity remains separate from reviewed farm/person claims. | `test_manager_assets.py`, `manager_app_behavior_test.js` |
| Web cutover | `/manager` and its assets now rewrite to the full FastAPI manager surface instead of redirecting to an incomplete Next view. Authenticated Next users receive a bilingual Farm Truth entry point. | `test_next_farm_truth_entry.py`, Next typecheck/build |

## Integrity properties

- The candidate unit is exactly one completed registration plus one valid plot.
- Supporting tasks must have a valid `source_explicit` association to that exact
  registration and plot and must belong to the same source farmer.
- `trackwick_task_plot_links` permits one current plot per task. Reconciliation
  quarantines a previously managed link before resolving the current reference.
- The candidate fingerprint includes registration, plot, task, visit, and
  association fingerprints. Acceptance locks every PostgreSQL row whose value
  contributes to that receipt.
- New decisions require a current season. Accepted retries compare the immutable
  stored contract and do not depend on later season eligibility.
- Reviewed TrackWick identity, plot, and allocation links cannot be updated or
  deleted in SQLite or PostgreSQL.
- Browser responses remain allowlisted and omit raw contacts, Aadhaar material,
  provider identifiers, raw GPS, media URLs, and free-text provider payloads.

## Verification

All commands ran from repository HEAD plus this final-fix wave on 2026-08-05.

```text
./.venv/bin/pytest -q tests/ffl
413 passed, 1 pre-existing Starlette/httpx deprecation warning

node --check ffl/static/manager/app.js
passed

node tests/ffl/manager_app_behavior_test.js
manager Farm Truth behavior harness passed

pnpm typecheck  (apps/web)
passed

pnpm build  (apps/web)
Next.js optimized production build passed; 9/9 static pages generated

./.venv/bin/python -m compileall -q ffl tests/ffl
passed

git diff --check
passed
```

No `FFL_TEST_POSTGRES_DSN` was available, so a live PostgreSQL smoke test was
not run. PostgreSQL SQL translation, relation discovery, Decimal conversion,
migration privilege parsing, and the SQLite behavioral mirror are covered by
the green automated suite; the receipt lock clause was also inspected directly.

## Deployment requirements

1. Apply `db/postgres/0015_agro_farm_truth_hardening.sql` before deploying the
   application code. It adds the provider plot-reference column, explicit
   association table, immutable reviewed-link guards, and runtime privileges.
2. Configure `FFL_TRACKWICK_TASK_PLOT_REFERENCE_FORM_KEY` with the reviewed
   TrackWick Farmer Visit form field that carries the registration plot's Gata
   reference. Without this setting, refresh deliberately creates no derived
   task-to-plot associations and therefore no guessed Farm Truth candidates.
3. Run a live PostgreSQL migration/smoke check in the deployment environment,
   then perform the planned manager review of 25 records before broader rollout.
