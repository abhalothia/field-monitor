# TrackOlap Dual Ingest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one private, read-only TrackOlap source lane that reaches dashboard-metric parity from both historical CSV bundles and a reviewed live API configuration.

**Architecture:** Both inputs pass through one strict mapping layer and persist source-backed normalized records. A manager-only metric service derives coverage, visits, issue counts, and confidence warnings from those records. The live adapter is configuration-bound and GET-only, so it cannot guess TrackOlap endpoints or make a request without a reviewed token/configuration pair.

**Tech Stack:** Python 3.12, FastAPI, SQLite/Postgres repository boundary, `httpx`, standard-library `csv`/`zipfile`, pytest.

## Global Constraints

- Source key is `trackolap-fortune-paddy`; it is a partner, read-only source.
- Retain a CSV bundle as private evidence; normalize API payloads in memory and never retain a raw API payload.
- Admit only six approved feeds and their mapping-manifest fields.
- No browser credential, TrackOlap write request, GPS history, contact/payment identity data, parcel geometry, automatic agronomic recommendation, or task completion.
- A missing API config or token must yield `unavailable` with zero HTTP requests.
- `filing_officer_id` and `territory_owner_id` remain distinct in all records and metrics.

---

### Task 1: Shared contracts, mapping manifest, and CSV bundle parser

**Files:**
- Create: `ffl/integrations/__init__.py`
- Create: `ffl/integrations/trackolap/__init__.py`
- Create: `ffl/integrations/trackolap/contracts.py`
- Create: `ffl/integrations/trackolap/mapping.py`
- Create: `ffl/integrations/trackolap/csv_ingest.py`
- Test: `tests/ffl/test_trackolap_mapping.py`

**Interfaces:**
- Produces `TrackolapRecord(feed, source_id, source_updated_at, tenant_id, values)` and `MappingResult(record, errors)`.
- Produces `MappingManifest.from_dict(value)` and `parse_csv_bundle(content, manifest)`.
- Consumes only raw row dictionaries and the reviewed field mapping; it does not access a database or network.

- [ ] **Step 1: Write failing mapping and CSV tests**

```python
def test_mapping_keeps_filing_officer_separate_from_territory_owner():
    result = normalise_row("visits", {
        "visit_key": "visit-1", "task_key": "task-1", "filed_by": "officer-1",
        "performed": "2026-08-03T09:00:00+05:30", "submitted": "2026-08-03T09:05:00+05:30",
        "status": "complete", "updated": "2026-08-03T09:05:00+05:30",
    }, VISIT_MANIFEST)
    assert result.record.values["filing_officer_id"] == "officer-1"
    assert "territory_owner_id" not in result.record.values

def test_csv_bundle_reports_unknown_header_and_never_guesses_mapping():
    bundle = zip_bytes({"visits.csv": "visit_key,wrong\nv-1,value\n"})
    parsed = parse_csv_bundle(bundle, VISIT_MANIFEST)
    assert parsed.rows[0].errors[0]["code"] == "missing_mapped_column"
```

- [ ] **Step 2: Run the failing tests**

Run: `pytest tests/ffl/test_trackolap_mapping.py -v`

Expected: FAIL because the TrackOlap integration modules do not exist.

- [ ] **Step 3: Implement immutable feed contracts and validation**

```python
FEEDS = frozenset({"officers", "attendance", "farmer_tasks", "visits", "issue_observations", "pesticide_events"})

@dataclass(frozen=True)
class TrackolapRecord:
    feed: str
    source_id: str
    source_updated_at: str
    tenant_id: str
    values: dict[str, str]

def normalise_row(feed: str, raw: Mapping[str, str], manifest: MappingManifest) -> MappingResult:
    required = REQUIRED_FIELDS[feed]
    values, errors = manifest.map_fields(feed, raw, required)
    return MappingResult(_record(feed, values, errors), tuple(errors))
```

Validate every required stable ID and timezone-aware timestamp, reject a field outside the feed contract, require all six manifest feed definitions, and limit ZIP entry count, uncompressed bytes, row count, and filename traversal.

- [ ] **Step 4: Run the mapping tests**

Run: `pytest tests/ffl/test_trackolap_mapping.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the standalone mapping boundary**

```bash
git add ffl/integrations tests/ffl/test_trackolap_mapping.py
git commit -m "feat: add TrackOlap mapping boundary"
```

### Task 2: Persist normalized source records and CSV evidence imports

**Files:**
- Modify: `ffl/persistence/schema.py`
- Modify: `ffl/domain/models.py`
- Modify: `ffl/persistence/repository.py`
- Create: `ffl/services/trackolap_ingest.py`
- Test: `tests/ffl/test_trackolap_ingest.py`

**Interfaces:**
- Consumes `TrackolapRecord`, `MappingResult`, an approved manager/owner, and source evidence bytes.
- Produces `TrackolapIngestResult(source, batch, source_run, valid_count, quarantined_count, idempotent)`.
- Persists `trackolap_records` with `(source_id, feed, source_identifier, source_updated_at)` uniqueness and an immutable normalized JSON payload.

- [ ] **Step 1: Write failing source-import lifecycle tests**

```python
def test_csv_bundle_retains_one_evidence_artifact_and_quarantines_bad_rows(ffl_db, owner, tmp_path):
    result = ingest_csv_bundle(ffl_db, BUNDLE_WITH_ONE_BAD_VISIT, MANIFEST, owner.id, evidence_directory=str(tmp_path))
    assert result.valid_count == 6
    assert result.quarantined_count == 1
    assert repository.list_trackolap_records(ffl_db, result.source.id)[0].feed == "officers"

def test_replaying_identical_bundle_is_idempotent(ffl_db, owner, tmp_path):
    first = ingest_csv_bundle(ffl_db, VALID_BUNDLE, MANIFEST, owner.id, evidence_directory=str(tmp_path))
    replay = ingest_csv_bundle(ffl_db, VALID_BUNDLE, MANIFEST, owner.id, evidence_directory=str(tmp_path))
    assert replay.idempotent is True
    assert replay.batch.id == first.batch.id
```

- [ ] **Step 2: Run the failing source-import tests**

Run: `pytest tests/ffl/test_trackolap_ingest.py -v`

Expected: FAIL because persistence and the service do not exist.

- [ ] **Step 3: Add schema, models, repository functions, and service transaction**

```sql
CREATE TABLE IF NOT EXISTS trackolap_records (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES source_registry(id),
    source_run_id TEXT REFERENCES source_runs(id),
    import_batch_id TEXT REFERENCES import_batches(id),
    feed TEXT NOT NULL,
    source_identifier TEXT NOT NULL,
    source_updated_at TEXT NOT NULL,
    values_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('valid', 'quarantined', 'published')),
    created_at TEXT NOT NULL,
    UNIQUE (source_id, feed, source_identifier, source_updated_at)
);
```

`ingest_csv_bundle` registers `trackolap-fortune-paddy` as a disabled-by-default `partner` source, retains the bundle with `application/zip`, creates the import batch and source run in one transaction, writes valid rows and quarantine rows separately, and only marks source records published after the existing import review/publish lifecycle succeeds.

- [ ] **Step 4: Run lifecycle and regression tests**

Run: `pytest tests/ffl/test_trackolap_ingest.py tests/ffl/test_evidence_imports.py tests/ffl/test_sources.py -v`

Expected: PASS.

- [ ] **Step 5: Commit source-backed CSV ingest**

```bash
git add ffl/persistence/schema.py ffl/domain/models.py ffl/persistence/repository.py ffl/services/trackolap_ingest.py tests/ffl/test_trackolap_ingest.py
git commit -m "feat: import TrackOlap CSV bundles privately"
```

### Task 3: Derive dashboard-parity metrics and expose manager-safe routes

**Files:**
- Create: `ffl/services/trackolap_metrics.py`
- Create: `ffl/api/trackolap_routes.py`
- Modify: `ffl/app.py`
- Test: `tests/ffl/test_trackolap_metrics.py`
- Test: `tests/ffl/test_trackolap_routes.py`

**Interfaces:**
- Consumes published `TrackolapRecord` rows, `as_of`, reporting timezone, and a 14-day recent window.
- Produces `parity_snapshot` with `coverage`, `visits`, `issues`, `pesticides`, `freshness`, and `warnings` only.
- Routes are `POST /api/v1/trackolap/imports/csv`, `GET /api/v1/trackolap/metrics`, and `GET /api/v1/trackolap/health`.

- [ ] **Step 1: Write failing metric and route tests**

```python
def test_coverage_marks_never_visited_and_stale_visits_overdue():
    snapshot = dashboard_metrics(RECORDS, as_of="2026-08-03T18:00:00+05:30")
    assert snapshot["coverage"] == {"taken_kit": 3, "visited": 2, "recent": 1, "overdue": 2, "never_visited": 1}
    assert snapshot["warnings"] == ["low_observation_confidence"]

def test_metrics_route_does_not_expose_task_urls_or_credentials(trackolap_client):
    response = trackolap_client.get("/api/v1/trackolap/metrics")
    assert response.status_code == 200
    assert "https://" not in repr(response.json())
    assert "token" not in repr(response.json()).lower()
```

- [ ] **Step 2: Run the failing metric and route tests**

Run: `pytest tests/ffl/test_trackolap_metrics.py tests/ffl/test_trackolap_routes.py -v`

Expected: FAIL because the metric service and router do not exist.

- [ ] **Step 3: Implement calculations and safe presentation**

```python
def dashboard_metrics(records: Sequence[TrackolapRecord], as_of: datetime, recent_days: int = 14) -> dict:
    population = _active_tasks(records)
    visits = _valid_visits(records)
    coverage = _coverage(population, visits, as_of, recent_days)
    return {"coverage": coverage, "visits": _visit_summary(visits, as_of), "issues": _issue_summary(records, as_of), "pesticides": _pesticide_summary(records), "warnings": _warnings(coverage, visits), "freshness": _freshness(records, as_of)}
```

The route validates base64 bundle content and a reviewed mapping manifest, maps service exceptions to 422/404/503 responses, serializes only aggregate metric values, and is added to `create_app` behind the existing launch gate.

- [ ] **Step 4: Run metric, route, and app regressions**

Run: `pytest tests/ffl/test_trackolap_metrics.py tests/ffl/test_trackolap_routes.py tests/ffl/test_app.py -v`

Expected: PASS.

- [ ] **Step 5: Commit parity metrics and routes**

```bash
git add ffl/services/trackolap_metrics.py ffl/api/trackolap_routes.py ffl/app.py tests/ffl/test_trackolap_metrics.py tests/ffl/test_trackolap_routes.py
git commit -m "feat: expose TrackOlap parity metrics"
```

### Task 4: Add the config-bound, GET-only live API adapter

**Files:**
- Create: `ffl/integrations/trackolap/api.py`
- Modify: `ffl/config.py`
- Modify: `ffl/services/trackolap_ingest.py`
- Modify: `ffl/api/trackolap_routes.py`
- Test: `tests/ffl/test_trackolap_api.py`
- Test: `tests/ffl/test_trackolap_routes.py`
- Modify: `docs/ffl/TRACKOLAP-TRACKWICK-INTEGRATION.md`

**Interfaces:**
- Consumes `TrackolapApiConfig`, a runtime token resolver, and injected `httpx` transport.
- Produces `ApiFetchResult(rows, cursor, rows_received)` or `SourceUnavailable(code)` / `SourceFailure(code)`.
- Adds `POST /api/v1/trackolap/refresh`, which records safe source health and never returns provider content.

- [ ] **Step 1: Write failing API safety and pagination tests**

```python
def test_missing_token_is_unavailable_without_any_http_call():
    transport = RecordingTransport()
    result = refresh_trackolap(SOURCE, CONFIG, credential_resolver=lambda _: None, transport=transport)
    assert result.status == "unavailable"
    assert result.reason_code == "credentials_unavailable"
    assert transport.requests == []

def test_api_adapter_uses_only_get_and_advances_configured_cursor():
    result = adapter.fetch(config=CONFIG, token="runtime-token", cursor="cursor-1", transport=two_page_transport())
    assert result.cursor == "cursor-3"
    assert [request.method for request in result.requests] == ["GET", "GET"]
```

- [ ] **Step 2: Run the failing API tests**

Run: `pytest tests/ffl/test_trackolap_api.py -v`

Expected: FAIL because the live adapter does not exist.

- [ ] **Step 3: Implement strict configuration and live refresh**

```python
@dataclass(frozen=True)
class TrackolapApiConfig:
    tenant_id: str
    base_url: str
    allowed_hosts: tuple[str, ...]
    reporting_timezone: str
    endpoints: Mapping[str, FeedEndpoint]
    read_only: bool

def fetch(self, config: TrackolapApiConfig, token: str, cursor: str | None) -> ApiFetchResult:
    if not config.read_only:
        raise SourceUnavailable("read_only_required")
    response = self._client.get(url, headers=headers, params=params)
    response.raise_for_status()
```

`TrackolapApiConfig.from_environment` rejects malformed JSON, missing six-feed contracts, non-HTTPS base URLs, host mismatch, empty project scope, write methods, and unrecognized cursor/envelope paths. The service records unavailable/failed/quarantined/succeeded runs through the existing source registry and sends fetched rows to the shared mapper from Task 1.

- [ ] **Step 4: Run complete TrackOlap and full FFL tests**

Run: `pytest tests/ffl/test_trackolap_mapping.py tests/ffl/test_trackolap_ingest.py tests/ffl/test_trackolap_metrics.py tests/ffl/test_trackolap_routes.py tests/ffl/test_trackolap_api.py -v && pytest tests/ffl -q`

Expected: PASS.

- [ ] **Step 5: Update operator guidance and commit the live boundary**

Add the exact environment keys, mapping-manifest shape, no-write guarantee, and a sample redacted configuration to `docs/ffl/TRACKOLAP-TRACKWICK-INTEGRATION.md`.

```bash
git add ffl/integrations/trackolap/api.py ffl/config.py ffl/services/trackolap_ingest.py ffl/api/trackolap_routes.py tests/ffl/test_trackolap_api.py tests/ffl/test_trackolap_routes.py docs/ffl/TRACKOLAP-TRACKWICK-INTEGRATION.md
git commit -m "feat: add safe TrackOlap API refresh"
```

## Plan self-review

- **Spec coverage:** Tasks 1–2 implement identical CSV/API normalization and source provenance; Task 3 implements parity and confidence; Task 4 implements the disabled-by-default GET-only live path and documentation.
- **Placeholder scan:** No incomplete work items, generic testing instructions, or unnamed interfaces remain.
- **Type consistency:** `TrackolapRecord`, `MappingManifest`, `TrackolapApiConfig`, `dashboard_metrics`, and `TrackolapIngestResult` are defined before any consuming task.
