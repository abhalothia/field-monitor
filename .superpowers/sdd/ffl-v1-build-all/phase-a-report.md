# FFL V1 Phase A report

## Delivered

- Added the V1 shared domain dataclasses in `ffl/domain/models.py`.
- Extended the idempotent SQLite schema in `ffl/persistence/schema.py` with all Phase A tables:
  `evidence_artifacts`, `field_signals`, `crop_stage_checkpoints`, `harvest_records`,
  `season_reviews`, `source_registry`, `source_runs`, `regional_signals`, `import_batches`,
  `import_rows`, `playbooks`, `trials`, `trial_allocations`, `trial_confounders`, and
  `trial_conclusions`.
- Added explicit-connection create/get/list repository helpers in
  `ffl/persistence/repository.py`. JSON columns are serialized on write and decoded in the
  dataclass mappers.
- Added focused in-memory coverage in `tests/ffl/test_v1_shared_repository.py` for schema and
  source registry idempotency, SHA-256 import/hash artifact linkage, append-only harvest
  corrections, and trial allocation/conclusion evidence/playbook linkage.

## Integrity contract

- UUID and UTC timestamps use the existing repository conventions.
- Sources retain only `credentials_reference`, never a credential-value field; their authority,
  owner, mapping/schema versions, coverage, freshness target, and run failure/retry metadata are
  represented explicitly.
- Imports require a lowercase SHA-256 digest and an artifact with the same digest; batch retries
  return the existing batch rather than duplicating it.
- Harvest corrections are new records with a required prior-record link, actor, and reason.
- Trial conclusions require evidence and can only promote a playbook when approved with an
  approval timestamp and playbook reference.

## Verification

- `python3 -m py_compile ffl/domain/models.py ffl/persistence/schema.py ffl/persistence/repository.py tests/ffl/test_v1_shared_repository.py` passed.
- An in-memory SQLite verification script passed after calling `create_schema` twice and covering
  source retry, import retry, harvest correction, and trial allocation/conclusion paths.
- `pytest -q tests/ffl/test_v1_shared_repository.py tests/ffl/test_repository.py` could not run:
  neither `pytest` nor the `pytest` Python module is installed in this workspace.

## Commit

`feat: add FFL V1 shared records`

## Deviations

None from Phase A scope. No API routes, UI changes, provider calls, archived modules, or Vercel
configuration were changed.
