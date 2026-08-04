# TrackWick Private Spatial Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist TrackWick's approved private CRM, task, plot, location, and media-reference data in typed PostgreSQL tables without changing canonical farm truth.

**Architecture:** Add one private, idempotent Postgres migration and a focused TrackWick normaliser/persistence lane beside the existing aggregate metrics feed. Source identity and provenance stay typed; exact points and remote media URLs are accessible only to authenticated server routes in later work.

**Tech Stack:** PostgreSQL/Supabase private `agro` schema, PostGIS geography, FastAPI, Python, HTTPX, pytest.

## Global Constraints

- Do not expose `agro` through Supabase Data API or grant `PUBLIC`, `anon`, or browser roles access.
- Never import Aadhaar, signatures, comments, unknown media fields, or raw provider JSON.
- Crop and plot media remain remote references; no object-storage write or AI call is added.
- A TrackWick location is source evidence only and must never create canonical farm/field geometry.
- Use `TIMESTAMPTZ`, typed columns for map/filter fields, explicit checks, foreign-key indexes, GiST for point search, and atomic UPSERTs.

---

### Task 1: Add the private typed schema

**Files:**
- Create: `db/postgres/0009_agro_trackwick_private_spatial_evidence.sql`
- Test: `tests/ffl/test_trackwick_private_schema.py`

**Interfaces:**
- Consumes: `agro_source_registry`, `agro_source_runs`, canonical `agro_*` tables.
- Produces: typed `agro_trackwick_*` source/evidence tables and review-link tables.

- [ ] **Step 1: Write the failing schema-contract test**

```python
def test_private_spatial_migration_declares_typed_source_tables():
    sql = migration_text("0009_agro_trackwick_private_spatial_evidence.sql")
    assert "CREATE TABLE IF NOT EXISTS agro_trackwick_location_observations" in sql
    assert "geography(Point, 4326)" in sql
    assert "Aadhar" not in sql
```

- [ ] **Step 2: Run it and verify failure**

Run: `pytest -q tests/ffl/test_trackwick_private_schema.py`

- [ ] **Step 3: Add the migration**

Create typed party, contact, task, visit, finding, crop-input, registration,
plot, location, media, worker-day, and review-link tables. Add source identity
uniqueness, source-row provenance, location bounds checks, GiST/foreign-key
indexes, and no-public-access revocations.

- [ ] **Step 4: Run schema-contract tests**

Run: `pytest -q tests/ffl/test_trackwick_private_schema.py`

### Task 2: Normalise the private TrackWick allow-list

**Files:**
- Modify: `ffl/integrations/trackolap/trackwick.py`
- Create: `tests/ffl/test_trackwick_private_evidence.py`

**Interfaces:**
- Consumes: `TrackwickFetchResult` provider objects.
- Produces: `TrackwickPrivateEvidenceResult` with typed valid rows and quarantined count.

- [ ] **Step 1: Write a failing normalisation test**

```python
def test_private_normaliser_keeps_crop_media_and_photo_geo_but_drops_aadhaar(sample_fetch):
    result = normalise_trackwick_private_evidence(sample_fetch, config)
    assert result.media[0].media_kind == "crop_photo"
    assert result.locations[0].location_kind == "media_capture"
    assert "Aadhar No" not in repr(result)
```

- [ ] **Step 2: Run it and verify failure**

Run: `pytest -q tests/ffl/test_trackwick_private_evidence.py`

- [ ] **Step 3: Implement allow-listed mapping**

Map only documented CRM, task, visit, registration, plot, location, and
crop/plot-media fields. Validate fixed-host HTTPS image URLs, coordinates, and
provider timestamps. Produce no raw form payload.

- [ ] **Step 4: Run normalisation tests**

Run: `pytest -q tests/ffl/test_trackwick_private_evidence.py`

### Task 3: Persist the typed source graph atomically

**Files:**
- Modify: `ffl/services/trackwick_ingest.py`
- Modify: `ffl/persistence/repository.py`
- Test: `tests/ffl/test_trackwick_ingest.py`

**Interfaces:**
- Consumes: `TrackwickPrivateEvidenceResult`, current `SourceRun`.
- Produces: idempotent private typed row upserts tied to the source run.

- [ ] **Step 1: Write a failing persistence test**

```python
def test_refresh_upserts_private_media_location_and_task_once(seeded_connection, adapter):
    result = refresh_live_trackwick(seeded_connection, manager_id, adapter=adapter)
    assert count_rows(seeded_connection, "trackwick_media_references") == 1
    assert count_rows(seeded_connection, "trackwick_location_observations") >= 1
```

- [ ] **Step 2: Run it and verify failure**

Run: `pytest -q tests/ffl/test_trackwick_ingest.py -k private`

- [ ] **Step 3: Add batched UPSERT persistence**

Use source/provider identity and `ON CONFLICT` to retain first/last-seen
times. Insert parents before children. Keep existing safe metric records
unchanged. Roll back the source transaction if any private persistence fails.

- [ ] **Step 4: Run persistence tests**

Run: `pytest -q tests/ffl/test_trackwick_ingest.py -k private`

### Task 4: Verify the complete private lane

**Files:**
- Modify: `docs/ffl/TRACKWICK-INTEGRATION.md`
- Test: `tests/ffl/test_trackwick_private_evidence.py`

**Interfaces:**
- Consumes: schema, normaliser, and persistence lane.
- Produces: a documented private-data boundary and a verified test suite.

- [ ] **Step 1: Add replay/exclusion coverage**

```python
def test_replay_does_not_duplicate_private_source_rows(seeded_connection, manager_id, adapter):
    refresh_live_trackwick(seeded_connection, manager_id, adapter=adapter)
    refresh_live_trackwick(seeded_connection, manager_id, adapter=adapter)
    assert count_rows(seeded_connection, "trackwick_tasks") == 1
```

- [ ] **Step 2: Document the exact boundary**

Document the private allow-list, remote-only media rule, source location
confidence labels, no-AI boundary, and manager-only serving requirement.

- [ ] **Step 3: Run focused and full test suites**

Run: `pytest -q tests/ffl/test_trackwick_private_evidence.py tests/ffl/test_trackwick_ingest.py && pytest -q tests/ffl`

- [ ] **Step 4: Verify migration and diff hygiene**

Run: `git diff --check && git status --short`
