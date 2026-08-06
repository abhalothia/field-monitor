# Farm Graph and Profile Kernel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Add a canonical Farm above Field and expose safe Farm, Field, Farmer, and Field Worker profiles.

**Architecture:** Farm is a new private canonical parent. Existing operational blocks remain Fields and retain parcels, crop allocations, work, and signals. Time-bounded Farm-to-Field membership and existing person relationships make cardinality explicit. Server-side read models compose reviewed truth and labelled TrackWick evidence; browser DTOs are strictly allowlisted.

**Tech Stack:** PostgreSQL/Supabase migrations, SQLite parity schema, Python/FastAPI, pytest, Next.js 16/React 19, TypeScript.

## Global Constraints

- Farm is canonical; Field is an operational block with reviewed parcels/geometry.
- One Field has one active Farm membership; membership history is retained.
- Farmers and Field Workers are people with many-to-many, time-bounded roles. Field Worker maps to field_operator.
- A crop belongs to a Field and Season through crop allocation, never directly to a person.
- TrackWick stays reported until an explicit reviewed link exists.
- Browser DTOs exclude contacts, provider identifiers, raw forms/payloads, coordinates, media URLs, and credentials.
- Disease/pest source data shows only kind, declared severity, and date; no raw source text or inferred diagnosis.
- Historical purchase cohorts are never attributed to a Farm/Farmer/Field without a future reviewed link.
- Directory limits: query <= 80 characters, 1 <= limit <= 100, ISO dates, maximum 366-day date window.

---

## File Structure

| File | Responsibility |
|---|---|
| db/postgres/0018_agro_farm_graph.sql | Farm graph migration, triggers, indexes, grants. |
| ffl/persistence/schema.py | SQLite parity schema/triggers. |
| ffl/persistence/repository.py | Farm graph records and helpers. |
| ffl/services/farm_profiles.py | Safe entity profiles and directories. |
| ffl/api/farm_profile_routes.py | Manager-only entity routes and bounds. |
| tests/ffl/test_farm_graph.py | Graph/cardinality lifecycle tests. |
| tests/ffl/test_farm_profile_routes.py | Profile, redaction, date, route tests. |
| apps/web/components/command-centre.tsx | Farm-first directory and profile panels. |
| apps/web/app/globals.css | Filter/profile responsive layout. |

### Task 1: Create the private Farm graph

**Files:**
- Create: db/postgres/0018_agro_farm_graph.sql
- Modify: ffl/persistence/schema.py
- Create: tests/ffl/test_farm_graph.py

**Interfaces:**
- Produces Farm and FarmField records, one active Farm membership per Field.
- Consumes operating_units and operational_blocks.

- [ ] **Step 1: Write failing cardinality tests**

~~~python
def test_farm_has_many_fields_but_field_has_one_active_farm(ffl_db, users, operating_unit):
    farm = repository.create_farm(ffl_db, operating_unit.id, "Fortune North", users.manager.id)
    field_one = repository.create_operational_block(ffl_db, operating_unit.id, "North 1", 1.5)
    field_two = repository.create_operational_block(ffl_db, operating_unit.id, "North 2", 1.2)

    repository.assign_field_to_farm(ffl_db, farm.id, field_one.id, "2026-08-06", users.manager.id)
    repository.assign_field_to_farm(ffl_db, farm.id, field_two.id, "2026-08-06", users.manager.id)

    assert [row.operational_block_id for row in repository.list_active_farm_fields(ffl_db, farm.id)] == [field_one.id, field_two.id]
    with pytest.raises(sqlite3.IntegrityError):
        repository.assign_field_to_farm(ffl_db, "other-farm", field_one.id, "2026-08-07", users.manager.id)
~~~

- [ ] **Step 2: Run the failing test**

Run: .venv/bin/pytest -q tests/ffl/test_farm_graph.py -k active_farm

Expected: FAIL because Farm graph relations and helpers do not exist.

- [ ] **Step 3: Add migration and SQLite parity**

~~~sql
CREATE TABLE IF NOT EXISTS agro_farms (
    id TEXT PRIMARY KEY,
    operating_unit_id TEXT NOT NULL REFERENCES agro_operating_units(id),
    name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'archived')),
    reviewed_by_person_id TEXT NOT NULL REFERENCES agro_people(id),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS agro_farm_fields (
    id TEXT PRIMARY KEY,
    farm_id TEXT NOT NULL REFERENCES agro_farms(id),
    operational_block_id TEXT NOT NULL REFERENCES agro_operational_blocks(id),
    starts_on DATE NOT NULL,
    ends_on DATE,
    status TEXT NOT NULL CHECK (status IN ('active', 'ended')),
    reviewed_by_person_id TEXT NOT NULL REFERENCES agro_people(id),
    created_at TIMESTAMPTZ NOT NULL,
    CHECK ((status = 'active' AND ends_on IS NULL) OR (status = 'ended' AND ends_on IS NOT NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS agro_idx_farm_fields_one_active_field
  ON agro_farm_fields (operational_block_id) WHERE status = 'active';
~~~

Add equivalent SQLite tables/indexes. Add PostgreSQL and SQLite triggers that reject a Farm-to-Field row when Farm and Field have different operating units. Revoke PUBLIC and grant runtime role SELECT and INSERT only.

- [ ] **Step 4: Run graph verification**

Run: .venv/bin/pytest -q tests/ffl/test_farm_graph.py

Expected: PASS; many fields per Farm, one active Farm per Field, ended membership reassigns, cross-unit association is rejected.

- [ ] **Step 5: Commit**

~~~bash
git add db/postgres/0018_agro_farm_graph.sql ffl/persistence/schema.py tests/ffl/test_farm_graph.py
git commit -m "feat: add canonical farm graph"
~~~

### Task 2: Add time-bounded Farm membership helpers

**Files:**
- Modify: ffl/persistence/repository.py
- Modify: tests/ffl/test_farm_graph.py

**Interfaces:**
- Produces Farm, FarmField, create_farm, assign_field_to_farm, end_farm_field_assignment, list_active_farm_fields, list_people_for_farm.
- Consumes Task 1 tables and existing reviewed person relationships.

- [ ] **Step 1: Write failing relationship test**

~~~python
def test_field_worker_and_farmer_can_each_span_many_fields(ffl_db, users, farm, fields, crop_allocation):
    worker = repository.create_person(ffl_db, "Nisha Field Worker", "field_operator")
    farmer = repository.create_person(ffl_db, "Ravi Farmer", "grower")

    repository.create_person_operating_relationship(
        ffl_db, worker.id, "operational_block", fields[0].id, "field_operator",
        "2026-08-06", reviewed_by_person_id=users.manager.id,
    )
    repository.create_person_operating_relationship(
        ffl_db, farmer.id, "crop_allocation", crop_allocation.id, "grower",
        "2026-08-06", reviewed_by_person_id=users.manager.id,
    )

    members = repository.list_people_for_farm(ffl_db, farm.id)
    assert {(item.name, item.role) for item in members} == {
        ("Nisha Field Worker", "field_operator"), ("Ravi Farmer", "grower"),
    }
~~~

- [ ] **Step 2: Run the failing test**

Run: .venv/bin/pytest -q tests/ffl/test_farm_graph.py -k span_many_fields

Expected: FAIL because list_people_for_farm does not exist.

- [ ] **Step 3: Implement reviewed-only helpers**

Implement list_people_for_farm by resolving active reviewed relationships scoped to active Farm Fields or their crop allocations. Deduplicate only by person_id and role, preserving a person with two roles. Never infer membership from TrackWick parties/tasks. End helper changes only an active FarmField row to ended with a supplied end date/reviewer.

- [ ] **Step 4: Run repository tests**

Run: .venv/bin/pytest -q tests/ffl/test_farm_graph.py

Expected: PASS; worker/farmer many-to-many roles, lifecycle, and review boundary hold.

- [ ] **Step 5: Commit**

~~~bash
git add ffl/persistence/repository.py tests/ffl/test_farm_graph.py
git commit -m "feat: connect people and fields to farms"
~~~

### Task 3: Add safe Farm, Field, Farmer, and Worker read models

**Files:**
- Modify: ffl/services/farm_profiles.py
- Modify: tests/ffl/test_farm_profile_routes.py

**Interfaces:**
- Produces farm_record(conn, farm_id, date_from=None, date_to=None), field_record(conn, block_id, ...), person_context(conn, person_id, kind, ...), and bounded list_entity_directory.
- Consumes Task 1/2 graph, canonical work/signals, and reviewed-linked TrackWick events.

- [ ] **Step 1: Write failing Farm Record tests**

~~~python
def test_farm_record_has_four_sections_and_labels_reported_events(ffl_db, farm):
    record = farm_profiles.farm_record(ffl_db, farm.id)

    assert set(record) == {"state", "kind", "id", "name", "now", "people", "updates", "context", "limitations"}
    assert record["kind"] == "farm"
    assert all(item["state"] in {"reviewed", "reported"} for item in record["updates"])
    assert "contact_value" not in repr(record)
    assert "provider_identifier" not in repr(record)
    assert "longitude" not in repr(record)

def test_field_worker_context_lists_safe_assignments(ffl_db, worker):
    profile = farm_profiles.person_context(ffl_db, worker.id, "field_worker")

    assert profile["kind"] == "field_worker"
    assert all(set(row) == {"farm_id", "farm_name", "field_id", "field_name", "role", "starts_on"} for row in profile["assignments"])
~~~

- [ ] **Step 2: Run the failing tests**

Run: .venv/bin/pytest -q tests/ffl/test_farm_profile_routes.py -k 'four_sections or worker_context'

Expected: FAIL because the Farm/Field/Worker record types do not exist.

- [ ] **Step 3: Implement bounded DTOs**

~~~python
def farm_record(conn, farm_id: str, date_from: str | None = None, date_to: str | None = None) -> dict | None:
    bounds = _record_date_bounds(date_from, date_to)
    farm = repository.get_farm(conn, farm_id)
    if farm is None:
        return None
    return {
        "state": "reviewed", "kind": "farm", "id": farm.id, "name": farm.name,
        "now": _farm_now(conn, farm.id),
        "people": _farm_people(conn, farm.id),
        "updates": _farm_updates(conn, farm.id, bounds),
        "context": {"state": "not_attributed", "message": "Historical purchase cohorts are not attributed to this farm."},
        "limitations": ["Reported source events remain reported until reviewed as Fortune truth."],
    }
~~~

Return at most 30 timestamp-parsed descending update items. Canonical signal/work items are reviewed. A TrackWick task/visit/finding appears only through a reviewed task-to-allocation link belonging to a Field in the Farm and is still reported. Disease/pest summary is fixed from finding_kind and declared_severity; do not return reported_value or source_field. Person context accepts only farmer or field_worker; field_worker maps to field_operator. Field record contains reviewed geometry state and crop-season allocations.

- [ ] **Step 4: Add date/filter bounds and run tests**

~~~python
@pytest.mark.parametrize("start,end", [
    ("2026-08-02", "2026-08-01"),
    ("not-a-date", "2026-08-01"),
    ("2025-01-01", "2026-08-02"),
])
def test_farm_record_rejects_invalid_date_window(ffl_db, start, end):
    with pytest.raises(ValueError):
        farm_profiles.farm_record(ffl_db, "missing", start, end)
~~~

Run: .venv/bin/pytest -q tests/ffl/test_farm_profile_routes.py -k 'record or context or profile'

Expected: PASS; redaction, date validation, parsed ordering, and source/canonical separation hold.

- [ ] **Step 5: Commit**

~~~bash
git add ffl/services/farm_profiles.py tests/ffl/test_farm_profile_routes.py
git commit -m "feat: add farm entity profile kernel"
~~~

### Task 4: Add manager-only entity routes

**Files:**
- Modify: ffl/api/farm_profile_routes.py
- Modify: tests/ffl/test_farm_profile_routes.py

**Interfaces:**
- Produces GET /api/v1/farms, GET /api/v1/farms/{farm_id}, GET /api/v1/fields/{block_id}, GET /api/v1/people/{kind}/{person_id}.
- Consumes Task 3 read models.

- [ ] **Step 1: Write failing route tests**

~~~python
def test_entity_routes_require_manager_and_validate_person_kind(tmp_path):
    app = create_app(str(tmp_path / "entities.db"), manager_api_token="manager-secret")
    with TestClient(app) as client:
        denied = client.get("/api/v1/farms")
        invalid = client.get("/api/v1/people/unknown/person-1", headers={"X-FFL-Manager-Token": "manager-secret"})

    assert denied.status_code == 403
    assert invalid.status_code == 422
~~~

- [ ] **Step 2: Run the failing test**

Run: .venv/bin/pytest -q tests/ffl/test_farm_profile_routes.py -k entity_routes

Expected: FAIL with missing routes.

- [ ] **Step 3: Implement strict routes**

~~~python
@router.get("/farms/{farm_id}")
def get_farm(request: Request, farm_id: str, date_from: str | None = None,
             date_to: str | None = None, _manager_id: str = Depends(require_manager)) -> dict:
    try:
        record = farm_profiles.farm_record(_connection(request), farm_id, date_from, date_to)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if record is None:
        raise HTTPException(status_code=404, detail="farm record not found")
    return record
~~~

Add Field and Person equivalents. Directory route validates type, query/crop length, limit, and date range before service invocation. Existing reported candidate endpoints remain separate and unchanged.

- [ ] **Step 4: Run API tests**

Run: .venv/bin/pytest -q tests/ffl/test_farm_profile_routes.py -k 'entity_routes or routes_require_manager'

Expected: PASS; authorization, 422 input bounds, 404 absence, and no source leakage.

- [ ] **Step 5: Commit**

~~~bash
git add ffl/api/farm_profile_routes.py tests/ffl/test_farm_profile_routes.py
git commit -m "feat: expose safe farm entity profiles"
~~~

### Task 5: Make the web shell Farm-first

**Files:**
- Modify: apps/web/components/command-centre.tsx
- Modify: apps/web/app/globals.css
- Modify: tests/ffl/test_farm_profile_routes.py

**Interfaces:**
- Consumes Task 4 routes.
- Produces Farm directory and Farm/Field/Person profile panels.

- [ ] **Step 1: Write the failing UI contract**

~~~python
def test_command_centre_uses_farm_first_entity_profiles():
    source = Path("apps/web/components/command-centre.tsx").read_text()

    assert 'readJson<FarmDirectory>("/api/v1/farms?" + params)' in source
    assert 'readJson<FarmRecord>("/api/v1/farms/" + id)' in source
    assert 'readJson<FieldRecord>("/api/v1/fields/" + id)' in source
    assert 'readJson<PersonContext>("/api/v1/people/" + kind + "/" + id)' in source
    for heading in ("Now", "People", "Updates", "Context"):
        assert f">{heading}<" in source
~~~

- [ ] **Step 2: Run the failing UI contract**

Run: .venv/bin/pytest -q tests/ffl/test_farm_profile_routes.py -k farm_first_entity_profiles

Expected: FAIL because Fields treats operational blocks as Farm identities.

- [ ] **Step 3: Implement one contextual profile shell**

Fields becomes the Farm directory with visible state/query/date filters backed by URLSearchParams. A Farm panel has exactly Now, People, Updates, Context. People links open Farmer or Field Worker context; Field chips open a Field profile; crop-season chips stay inside Field context. Disease is a dated reported update with declared severity, not a diagnosis. Keep WhatsApp as a muted, non-interactive Coming soon row. Preserve existing keyboard focus restoration and use one-column mobile layout.

- [ ] **Step 4: Run web verification**

Run: .venv/bin/pytest -q tests/ffl/test_farm_profile_routes.py -k 'farm_first_entity_profiles or command_centre' && cd apps/web && pnpm typecheck && pnpm build

Expected: PASS; UI contract, typecheck, and production build succeed.

- [ ] **Step 5: Commit**

~~~bash
git add apps/web/components/command-centre.tsx apps/web/app/globals.css tests/ffl/test_farm_profile_routes.py
git commit -m "feat: make command centre farm first"
~~~

### Task 6: Apply and verify the private production migration

**Files:**
- Apply: db/postgres/0018_agro_farm_graph.sql

**Interfaces:**
- Consumes Tasks 1-5.
- Produces private Farm graph in the confirmed Fortune database and a Ready production deployment.

- [ ] **Step 1: Verify target before migration**

Run:
~~~bash
set -a
. ./.env
set +a
/Users/dakshbhatia/.homebrew/opt/libpq/bin/psql "$FFL_POSTGRES_DIRECT_URL" -v ON_ERROR_STOP=1 -c "SELECT current_database(), current_user, to_regnamespace('agro') IS NOT NULL AS agro_private_schema;"
~~~

Expected: confirmed Fortune target and true private schema.

- [ ] **Step 2: Apply migration once**

Run:
~~~bash
/Users/dakshbhatia/.homebrew/opt/libpq/bin/psql "$FFL_POSTGRES_DIRECT_URL" -v ON_ERROR_STOP=1 -f db/postgres/0018_agro_farm_graph.sql
~~~

Expected: transaction commits with no browser/Data API grants.

- [ ] **Step 3: Verify least privilege and deploy**

Run:
~~~bash
.venv/bin/pytest -q
cd apps/web && pnpm typecheck && pnpm build
pnpx vercel@latest --prod --yes --scope dakshbhatia1s-projects
~~~

Expected: tests/build pass and the latest Production deployment is Ready.

## Plan Self-Review

- Spec coverage: Tasks 1-2 establish Farm/Field and many-to-many roles; Tasks 3-5 create safe profile pages; Task 6 migrates and deploys.
- Safety coverage: source/canonical separation, date/filter bounds, redaction, reviewed relationships, and no inferred disease/farm/geometry are tested.
- Scope control: crop season and disease remain contextual subrecords, and Farm is the only new primary destination.
