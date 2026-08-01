# FFL Operating Kernel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a clean, offline-capable first vertical slice of the Fortune Farm Labs operating kernel for one managed farm, one season, and one field team.

**Architecture:** Create a new `ffl/` modular monolith beside the legacy prototype; it imports nothing from `src/`, `db/`, or `dashboard/`. A FastAPI backend owns SQLite persistence, state transitions, audit records, and idempotent field submissions. A dependency-free static PWA provides offline field capture, while a separate manager web surface consumes the same JSON API.

**Tech Stack:** Python 3.9, FastAPI, Uvicorn, SQLite, standard-library dataclasses, vanilla HTML/CSS/JavaScript, Service Worker, pytest.

## Global Constraints

- Do not modify or import from the legacy `src/`, `db/`, `dashboard/`, or `config/` product modules.
- Python source must remain compatible with Python 3.9; do not use `X | Y` union syntax or `match` statements.
- FFL V0 persists locally in SQLite but all repository calls accept an explicit `sqlite3.Connection` for deterministic tests.
- Every work, exception, decision, and evidence record uses an immutable UUID and records creation time in UTC ISO-8601 format.
- Work states are exactly `planned`, `in_progress`, `blocked`, `submitted`, `accepted`, `rejected`, and `cancelled`.
- Exception states are exactly `reported`, `triaged`, `owned`, `mitigated`, `monitoring`, `resolved`, `accepted_risk`, and `reopened`.
- A field submission includes a client-generated idempotency key. Replaying that key returns the original record and does not create a duplicate.
- Field PWA copy is English-first with a Hindi label dictionary; the selected language is stored in `localStorage`.
- Offline PWA submissions are queued in `localStorage`, visibly marked `Pending sync`, and retained after a failed HTTP response.
- No source adapter, document import, satellite feed, weather feed, or AI provider is implemented in this first vertical slice.

---

## Parallel delivery map

The first two tasks freeze the data and API contract; they are deliberately sequential. Once Task 2 is reviewed, the work can split without file overlap:

| Wave | Workstream | Tasks | Ownership boundary |
|---|---|---|---|
| 0 | Platform contract | 1, 2 | `ffl/domain/`, `ffl/persistence/` |
| 1 | Operating rules | 3 | `ffl/services/` and shared persistence extensions |
| 2 | Configured pilot | 4 | `ffl/seed.py`, template service, seed tests; requires Task 3's work-item contract |
| 3 | API | 5 | `ffl/api/`, `ffl/app.py`, API tests; requires Tasks 3 and 4 |
| 4A | Field PWA | 6 | `ffl/static/field/` only |
| 4B | Manager runtime | 7 | `ffl/static/manager/` only |
| 5 | Surface integration and full-path verification | 8 | `ffl/app.py`, `tests/ffl/test_e2e.py`, surface tests, runbook |

Tasks 1–5 are deliberately sequential: they extend the same persistence and API contracts. After Task 5 is committed and reviewed, Tasks 6 and 7 can run in separate worktrees in parallel because they own only separate static directories and their only shared dependency is the frozen JSON API. Task 8 alone adds the shared route wiring after both static surfaces are reviewed. Integrate each task only after its scoped review passes.

### Task 1: Bootstrap the Clean FFL Application

**Files:**
- Create: `ffl/__init__.py`
- Create: `ffl/app.py`
- Create: `ffl/config.py`
- Create: `tests/ffl/__init__.py`
- Create: `tests/ffl/test_app.py`
- Modify: `requirements.txt`

**Interfaces:**
- Produces `ffl.app.create_app(database_path: Optional[str] = None) -> FastAPI`.
- Produces `ffl.config.FFL_DATABASE_PATH`, defaulting to `<repo>/data/ffl.db` and overridable with `FFL_DATABASE_PATH`.

- [ ] **Step 1: Write the failing application test**

```python
from fastapi.testclient import TestClient

from ffl.app import create_app


def test_health_endpoint_reports_ffl_service():
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"service": "ffl-operating-kernel", "status": "ok"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python3 -m pytest tests/ffl/test_app.py::test_health_endpoint_reports_ffl_service -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'ffl'`.

- [ ] **Step 3: Add runtime dependencies and the minimal application factory**

Append these exact lines to `requirements.txt`:

```text
# FFL operating kernel
fastapi>=0.115.0,<1.0.0
uvicorn>=0.30.0,<1.0.0
httpx>=0.27.0,<1.0.0
```

Create `ffl/config.py`:

```python
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FFL_DATABASE_PATH = os.environ.get(
    "FFL_DATABASE_PATH", str(PROJECT_ROOT / "data" / "ffl.db")
)
```

Create `ffl/app.py`:

```python
from typing import Optional

from fastapi import FastAPI

from ffl.config import FFL_DATABASE_PATH


def create_app(database_path: Optional[str] = None) -> FastAPI:
    app = FastAPI(title="FFL Operating Kernel")
    app.state.database_path = database_path or FFL_DATABASE_PATH

    @app.get("/health")
    def health() -> dict:
        return {"service": "ffl-operating-kernel", "status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python3 -m pytest tests/ffl/test_app.py::test_health_endpoint_reports_ffl_service -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt ffl tests/ffl
git commit -m "feat: bootstrap FFL operating kernel"
```

### Task 2: Persist the Farm Topology and Operational State

**Files:**
- Create: `ffl/domain/__init__.py`
- Create: `ffl/domain/models.py`
- Create: `ffl/persistence/__init__.py`
- Create: `ffl/persistence/database.py`
- Create: `ffl/persistence/schema.py`
- Create: `ffl/persistence/repository.py`
- Create: `tests/ffl/conftest.py`
- Create: `tests/ffl/test_repository.py`

**Interfaces:**
- Produces `open_connection(path: str) -> sqlite3.Connection` and `create_schema(conn: sqlite3.Connection) -> None`.
- Produces `create_operating_unit`, `create_land_parcel`, `create_operational_block`, `create_right_to_operate`, `create_season`, and `create_crop_allocation`.
- Produces `create_person(conn, name: str, role: str) -> Person` and `link_block_parcel(conn, operational_block_id: str, land_parcel_id: str) -> None`.
- Produces `list_active_crop_allocations(conn, operating_unit_id: str) -> list[CropAllocation]`.
- `CropAllocation` has `id`, `operating_unit_id`, `operational_block_id`, `season_id`, `crop_name`, `cultivar`, `area_hectares`, `status`, `created_at`.

- [ ] **Step 1: Write failing topology tests**

```python
import pytest

from ffl.persistence.repository import (
    create_crop_allocation,
    create_land_parcel,
    create_operating_unit,
    create_operational_block,
    link_block_parcel,
    create_right_to_operate,
    create_season,
)


def test_partial_crop_allocation_preserves_block_history(ffl_db):
    unit = create_operating_unit(ffl_db, "Fortune Pilot")
    parcel = create_land_parcel(ffl_db, unit.id, "Parcel A", 10.0)
    block = create_operational_block(ffl_db, unit.id, "North Block", 10.0)
    link_block_parcel(ffl_db, block.id, parcel.id)
    create_right_to_operate(ffl_db, parcel.id, "leased", "2026-01-01", "2027-01-01")
    season = create_season(ffl_db, unit.id, "Kharif 2026", "2026-06-01", "2026-11-30")

    allocation = create_crop_allocation(
        ffl_db, unit.id, block.id, season.id, "Rice", "Pusa 1121", 4.0
    )

    assert allocation.area_hectares == 4.0
    assert allocation.operational_block_id == block.id


def test_overlapping_active_allocations_are_rejected(ffl_db):
    unit = create_operating_unit(ffl_db, "Fortune Pilot")
    block = create_operational_block(ffl_db, unit.id, "North Block", 5.0)
    season = create_season(ffl_db, unit.id, "Kharif 2026", "2026-06-01", "2026-11-30")
    create_crop_allocation(ffl_db, unit.id, block.id, season.id, "Rice", "Pusa 1121", 4.0)

    with pytest.raises(ValueError, match="exceeds available block area"):
        create_crop_allocation(ffl_db, unit.id, block.id, season.id, "Mint", None, 2.0)
```

- [ ] **Step 2: Run the topology tests to verify they fail**

Run: `python3 -m pytest tests/ffl/test_repository.py -v`

Expected: FAIL with `ModuleNotFoundError` for `ffl.persistence`.

- [ ] **Step 3: Implement the immutable identifiers, schema, and repository functions**

Use `uuid.uuid4()` and `datetime.now(timezone.utc).isoformat()` in one private helper. Create tables named `operating_units`, `land_parcels`, `operational_blocks`, `block_parcels`, `rights_to_operate`, `seasons`, `crop_allocations`, and `people` with text UUID primary keys and `created_at` text columns. `block_parcels` uses the composite primary key `(operational_block_id, land_parcel_id)`. Enable `PRAGMA foreign_keys = ON` in `open_connection`.

Implement the allocation guard exactly as:

```python
allocated = conn.execute(
    """SELECT COALESCE(SUM(area_hectares), 0) FROM crop_allocations
       WHERE operational_block_id = ? AND season_id = ? AND status = 'active'""",
    (operational_block_id, season_id),
).fetchone()[0]
if allocated + area_hectares > block.area_hectares:
    raise ValueError("crop allocation exceeds available block area")
```

Create `tests/ffl/conftest.py` with an in-memory connection, schema creation, `sqlite3.Row` rows, and cleanup:

```python
import pytest

from ffl.persistence.database import open_connection
from ffl.persistence.repository import (
    create_crop_allocation,
    create_operating_unit,
    create_operational_block,
    create_person,
    create_season,
)
from ffl.persistence.schema import create_schema


@pytest.fixture
def ffl_db():
    conn = open_connection(":memory:")
    create_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def users(ffl_db):
    return type("Users", (), {
        "manager": create_person(ffl_db, "Farm Manager", "farm_manager"),
        "operator": create_person(ffl_db, "Field Operator", "field_operator"),
        "lead": create_person(ffl_db, "Operations Lead", "operations_lead"),
    })()


@pytest.fixture
def crop_allocation(ffl_db):
    unit = create_operating_unit(ffl_db, "FFL Pilot Farm")
    block = create_operational_block(ffl_db, unit.id, "North Block", 5.0)
    season = create_season(ffl_db, unit.id, "Kharif 2026", "2026-06-01", "2026-11-30")
    return create_crop_allocation(ffl_db, unit.id, block.id, season.id, "Rice", "Pusa 1121", 5.0)


@pytest.fixture
def owner(ffl_db):
    return create_person(ffl_db, "Template Owner", "agronomist")
```

- [ ] **Step 4: Run the repository tests to verify they pass**

Run: `python3 -m pytest tests/ffl/test_repository.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ffl/domain ffl/persistence tests/ffl
git commit -m "feat: add FFL farm topology persistence"
```

### Task 3: Implement Work, Exceptions, Decisions, and Audit Transitions

**Files:**
- Create: `ffl/domain/transitions.py`
- Create: `ffl/services/__init__.py`
- Create: `ffl/services/operations.py`
- Modify: `ffl/domain/models.py`
- Modify: `ffl/persistence/schema.py`
- Modify: `ffl/persistence/repository.py`
- Create: `tests/ffl/test_operations.py`

**Interfaces:**
- Produces `create_work_item(conn, allocation_id, title, owner_id, due_at) -> WorkItem`.
- Produces `transition_work_item(conn, work_item_id, target_status, actor_id, reason) -> WorkItem`.
- Produces `report_exception(conn, allocation_id, title, severity, owner_id, fallback_owner_id, observed_at, idempotency_key) -> ExceptionRecord`.
- Produces `transition_exception(conn, exception_id, target_status, actor_id, reason) -> ExceptionRecord`.
- Produces `create_decision(conn, allocation_id, title, owner_id, review_due_at) -> Decision`.
- Produces `list_audit_events(conn, entity_type, entity_id) -> list[AuditEvent]`.

- [ ] **Step 1: Write failing state-machine tests**

```python
def test_work_requires_submission_before_acceptance(ffl_db, crop_allocation, users):
    work = create_work_item(ffl_db, crop_allocation.id, "Inspect irrigation", users.manager.id, "2026-07-10T09:00:00+00:00")

    with pytest.raises(ValueError, match="invalid work transition"):
        transition_work_item(ffl_db, work.id, "accepted", users.manager.id, "reviewed")

    submitted = transition_work_item(ffl_db, work.id, "submitted", users.operator.id, "photo attached")
    accepted = transition_work_item(ffl_db, submitted.id, "accepted", users.manager.id, "verified")

    assert accepted.status == "accepted"
    assert [event.to_status for event in list_audit_events(ffl_db, "work_item", work.id)] == ["submitted", "accepted"]


def test_replayed_exception_key_returns_same_exception(ffl_db, crop_allocation, users):
    first = report_exception(ffl_db, crop_allocation.id, "Leaf damage", "high", users.manager.id, users.lead.id, "2026-07-10T08:00:00+00:00", "device-7:42")
    replay = report_exception(ffl_db, crop_allocation.id, "Leaf damage", "high", users.manager.id, users.lead.id, "2026-07-10T08:00:00+00:00", "device-7:42")

    assert replay.id == first.id
```

- [ ] **Step 2: Run the operations tests to verify they fail**

Run: `python3 -m pytest tests/ffl/test_operations.py -v`

Expected: FAIL with `ImportError` for `ffl.services.operations`.

- [ ] **Step 3: Implement the state tables, transition guards, and audit events**

Create tables `work_items`, `exception_records`, `decisions`, and `audit_events`. Add a unique `idempotency_key` column to `exception_records`.

Define transition maps in `ffl/domain/transitions.py`:

```python
WORK_TRANSITIONS = {
    "planned": {"in_progress", "blocked", "cancelled"},
    "in_progress": {"blocked", "submitted", "cancelled"},
    "blocked": {"in_progress", "cancelled"},
    "submitted": {"accepted", "rejected"},
    "rejected": {"in_progress", "cancelled"},
    "accepted": set(),
    "cancelled": set(),
}
EXCEPTION_TRANSITIONS = {
    "reported": {"triaged"},
    "triaged": {"owned", "accepted_risk"},
    "owned": {"mitigated", "accepted_risk"},
    "mitigated": {"monitoring"},
    "monitoring": {"resolved", "reopened"},
    "resolved": {"reopened"},
    "accepted_risk": {"reopened"},
    "reopened": {"triaged"},
}
```

Reject target states not in the relevant map with `ValueError("invalid work transition")` or `ValueError("invalid exception transition")`. Insert one audit event for every successful transition with `entity_type`, `entity_id`, `from_status`, `to_status`, `actor_id`, `reason`, and `created_at`.

- [ ] **Step 4: Run the operations tests to verify they pass**

Run: `python3 -m pytest tests/ffl/test_operations.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ffl/domain ffl/services ffl/persistence tests/ffl/test_operations.py
git commit -m "feat: add FFL operational state machines"
```

### Task 4: Add Configurable Signal Templates and a Golden Pilot Seed

**Files:**
- Create: `ffl/services/templates.py`
- Create: `ffl/seed.py`
- Modify: `ffl/persistence/schema.py`
- Modify: `ffl/persistence/repository.py`
- Create: `tests/ffl/test_templates.py`
- Create: `tests/ffl/test_seed.py`

**Interfaces:**
- Produces `publish_signal_template(conn, name, version, fields, owner_id) -> SignalTemplate`.
- Produces `validate_signal_payload(template: SignalTemplate, payload: dict) -> dict`.
- Produces `seed_pilot(conn) -> dict` with keys `operating_unit_id`, `allocation_id`, `manager_id`, `operator_id`, and `lead_id`.

- [ ] **Step 1: Write failing template tests**

```python
import pytest

from ffl.persistence.repository import list_work_items
from ffl.services.templates import publish_signal_template, validate_signal_payload


def test_published_exception_template_rejects_missing_required_photo(ffl_db, owner):
    template = publish_signal_template(
        ffl_db,
        "crop_exception",
        1,
        [
            {"key": "severity", "type": "choice", "required": True, "options": ["low", "medium", "high", "critical"]},
            {"key": "photo_url", "type": "photo", "required": True},
        ],
        owner.id,
    )

    with pytest.raises(ValueError, match="photo_url is required"):
        validate_signal_payload(template, {"severity": "high"})


def test_seed_creates_active_work_for_the_pilot(ffl_db):
    seeded = seed_pilot(ffl_db)

    work = list_work_items(ffl_db, seeded["allocation_id"])

    assert len(work) == 1
    assert work[0].status == "planned"
```

- [ ] **Step 2: Run the template and seed tests to verify they fail**

Run: `python3 -m pytest tests/ffl/test_templates.py tests/ffl/test_seed.py -v`

Expected: FAIL with `ImportError` for `ffl.services.templates`.

- [ ] **Step 3: Implement template versioning and deterministic pilot data**

Create `signal_templates` with `name`, `version`, `status`, `fields_json`, `owner_id`, `published_at`, and unique `(name, version)`. `publish_signal_template` writes status `published` and serializes fields with `json.dumps`.

`validate_signal_payload` must reject missing required keys, reject choices not listed in `options`, and return only the declared keys. `seed_pilot` must create one operating unit named `FFL Pilot Farm`, one block named `North Block`, one active crop allocation for `Rice` / `Pusa 1121`, three users named `Farm Manager`, `Field Operator`, and `Operations Lead`, one `crop_exception` template, and one planned work item named `Inspect irrigation readiness`.

- [ ] **Step 4: Run the template and seed tests to verify they pass**

Run: `python3 -m pytest tests/ffl/test_templates.py tests/ffl/test_seed.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ffl/services/templates.py ffl/seed.py ffl/persistence tests/ffl
git commit -m "feat: add configurable pilot signal templates"
```

### Task 5: Expose the Kernel Through a Typed HTTP API

**Files:**
- Create: `ffl/api/__init__.py`
- Create: `ffl/api/routes.py`
- Modify: `ffl/app.py`
- Create: `tests/ffl/test_api.py`

**Interfaces:**
- `GET /api/v1/runtime` returns `operating_unit`, `allocations`, `work_items`, and `exceptions` for the seeded pilot.
- `POST /api/v1/work-items/{work_item_id}/transitions` accepts `status`, `actor_id`, and `reason`.
- `POST /api/v1/exceptions` accepts `allocation_id`, `title`, `severity`, `owner_id`, `fallback_owner_id`, `observed_at`, and `idempotency_key`.
- `GET /api/v1/exceptions/{exception_id}` returns the exception and its audit events.
- `POST /api/v1/exceptions/{exception_id}/transitions` accepts `status`, `actor_id`, and `reason`.

- [ ] **Step 1: Write failing HTTP tests**

```python
def test_exception_post_is_idempotent(seeded_client):
    payload = {
        "allocation_id": seeded_client.seed["allocation_id"],
        "title": "Water pooling in north edge",
        "severity": "high",
        "owner_id": seeded_client.seed["manager_id"],
        "fallback_owner_id": seeded_client.seed["lead_id"],
        "observed_at": "2026-07-10T08:00:00+00:00",
        "idempotency_key": "field-device-1:submission-2",
    }

    first = seeded_client.client.post("/api/v1/exceptions", json=payload)
    replay = seeded_client.client.post("/api/v1/exceptions", json=payload)

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]


def test_invalid_work_transition_returns_422(seeded_client):
    work_id = seeded_client.client.get("/api/v1/runtime").json()["work_items"][0]["id"]

    response = seeded_client.client.post(
        "/api/v1/work-items/{}/transitions".format(work_id),
        json={"status": "accepted", "actor_id": seeded_client.seed["manager_id"], "reason": "reviewed"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "invalid work transition"
```

- [ ] **Step 2: Run the API tests to verify they fail**

Run: `python3 -m pytest tests/ffl/test_api.py -v`

Expected: FAIL with `404` because `/api/v1/exceptions` is not registered.

- [ ] **Step 3: Implement routes with one database connection per app instance**

Create the connection in `create_app`, call `create_schema`, store it as `app.state.conn`, and register an `APIRouter(prefix="/api/v1")`. Convert `ValueError` from service calls into `HTTPException(status_code=422, detail=str(error))`. Return `201` only when an idempotency key creates a new exception; return `200` for a replay. Add this fixture to `tests/ffl/test_api.py` so every API test has a seeded, isolated application:

```python
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from ffl.app import create_app
from ffl.seed import seed_pilot


@pytest.fixture
def seeded_client(tmp_path: Path):
    app = create_app(str(tmp_path / "ffl.db"))
    seed = seed_pilot(app.state.conn)
    return SimpleNamespace(client=TestClient(app), seed=seed)
```

- [ ] **Step 4: Run the API tests to verify they pass**

Run: `python3 -m pytest tests/ffl/test_api.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ffl/api ffl/app.py tests/ffl/test_api.py
git commit -m "feat: expose FFL operating kernel API"
```

### Task 6: Build the Offline Field Capture PWA

**Files:**
- Create: `ffl/static/field/index.html`
- Create: `ffl/static/field/app.js`
- Create: `ffl/static/field/styles.css`
- Create: `ffl/static/field/sw.js`
- Create: `tests/ffl/test_field_assets.py`

**Interfaces:**
- `app.js` persists pending exceptions in `localStorage` key `ffl.pendingExceptions`.
- Every queued submission stores `idempotency_key`, payload, and `queued_at`.

- [ ] **Step 1: Write failing static asset tests**

```python
from pathlib import Path


def test_field_assets_define_offline_exception_capture():
    root = Path(__file__).resolve().parents[2] / "ffl" / "static" / "field"

    assert "Report exception" in (root / "index.html").read_text()
    assert "ffl.pendingExceptions" in (root / "app.js").read_text()
    assert "ffl-field-v1" in (root / "sw.js").read_text()
```

- [ ] **Step 2: Run the static asset test to verify it fails**

Run: `python3 -m pytest tests/ffl/test_field_assets.py -v`

Expected: FAIL because the field assets do not yet exist.

- [ ] **Step 3: Implement the small offline-first field experience**

The page must include English/Hindi labels for `Today’s work`, `Report exception`, `Severity`, `Photo`, `Location`, `Pending sync`, and `Sync now`. Route wiring is intentionally deferred to Task 8 so this static-only task can run in parallel with Task 7.

`app.js` must:

```javascript
const PENDING_KEY = "ffl.pendingExceptions";

function queueSubmission(payload) {
  const pending = JSON.parse(localStorage.getItem(PENDING_KEY) || "[]");
  pending.push({ payload, queued_at: new Date().toISOString() });
  localStorage.setItem(PENDING_KEY, JSON.stringify(pending));
}
```

Generate `idempotency_key` with `crypto.randomUUID()` before queueing. Submit online to `/api/v1/exceptions`; on network error or non-2xx response, retain the queue entry and display `Pending sync`. On successful replay, remove only that queue entry. Register `sw.js`, cache the field shell under cache name `ffl-field-v1`, and use a network-first strategy for `/api/` requests.

- [ ] **Step 4: Run the static asset test to verify it passes**

Run: `python3 -m pytest tests/ffl/test_field_assets.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ffl/static/field tests/ffl/test_field_assets.py
git commit -m "feat: add offline FFL field capture PWA"
```

### Task 7: Build the Manager Action Centre

**Files:**
- Create: `ffl/static/manager/index.html`
- Create: `ffl/static/manager/app.js`
- Create: `ffl/static/manager/styles.css`
- Create: `tests/ffl/test_manager_assets.py`

**Interfaces:**
- The manager shell requests `GET /api/v1/runtime` and renders open work and exceptions.
- Selecting an exception requests `GET /api/v1/exceptions/{id}` and renders audit history.

- [ ] **Step 1: Write failing manager surface tests**

```python
from pathlib import Path


def test_manager_assets_define_action_centre():
    root = Path(__file__).resolve().parents[2] / "ffl" / "static" / "manager"

    assert "FFL Action Centre" in (root / "index.html").read_text()
    assert "/api/v1/runtime" in (root / "app.js").read_text()
    assert "/api/v1/exceptions/" in (root / "app.js").read_text()
```

- [ ] **Step 2: Run the manager test to verify it fails**

Run: `python3 -m pytest tests/ffl/test_manager_assets.py -v`

Expected: FAIL because the manager assets do not yet exist.

- [ ] **Step 3: Implement the manager action centre**

The manager shell must render four cards from `/api/v1/runtime`: active allocation, planned/in-progress work, submitted work awaiting review, and open exceptions. The exception list shows severity, title, owner, fallback owner, observed time, current state, and next action. The work list shows title, owner, due time, current state, and whether it is overdue. Do not render satellite indexes, PDF exports, generic metrics, or unsupported AI advice. Route wiring is intentionally deferred to Task 8 so this static-only task can run in parallel with Task 6.

- [ ] **Step 4: Run the manager test to verify it passes**

Run: `python3 -m pytest tests/ffl/test_manager_assets.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ffl/static/manager tests/ffl/test_manager_assets.py
git commit -m "feat: add FFL manager action centre"
```

### Task 8: Verify the Golden Operating Loop and Document Local Run

**Files:**
- Create: `tests/ffl/test_e2e.py`
- Create: `tests/ffl/test_surfaces.py`
- Create: `docs/ffl/LOCAL-RUN.md`
- Modify: `README.md`
- Modify: `ffl/app.py`

**Interfaces:**
- The golden path creates the seeded pilot, reports one idempotent exception, transitions it through `triaged`, `owned`, `mitigated`, `monitoring`, and `resolved`, and confirms an auditable history.

- [ ] **Step 1: Write the end-to-end and surface-integration tests**

```python
def test_golden_exception_resolution_loop(seeded_client):
    payload = {
        "allocation_id": seeded_client.seed["allocation_id"],
        "title": "Irrigation drainage issue",
        "severity": "high",
        "owner_id": seeded_client.seed["manager_id"],
        "fallback_owner_id": seeded_client.seed["lead_id"],
        "observed_at": "2026-07-10T08:00:00+00:00",
        "idempotency_key": "E-001",
    }
    reported = seeded_client.client.post("/api/v1/exceptions", json=payload).json()

    for status, actor, reason in [
        ("triaged", seeded_client.seed["manager_id"], "priority confirmed"),
        ("owned", seeded_client.seed["manager_id"], "manager assigned"),
        ("mitigated", seeded_client.seed["operator_id"], "drainage cleared"),
        ("monitoring", seeded_client.seed["manager_id"], "follow-up scheduled"),
        ("resolved", seeded_client.seed["manager_id"], "follow-up passed"),
    ]:
        response = seeded_client.client.post(
            "/api/v1/exceptions/{}/transitions".format(reported["id"]),
            json={"status": status, "actor_id": actor, "reason": reason},
        )
        assert response.status_code == 200

    detail = seeded_client.client.get("/api/v1/exceptions/{}".format(reported["id"])).json()

    assert detail["status"] == "resolved"
    assert [event["to_status"] for event in detail["audit_events"]] == [
        "triaged", "owned", "mitigated", "monitoring", "resolved"
    ]


def test_field_and_manager_surfaces_are_served(client):
    assert client.get("/field").status_code == 200
    assert "Report exception" in client.get("/field").text
    assert client.get("/manager").status_code == 200
    assert "FFL Action Centre" in client.get("/manager").text
```

- [ ] **Step 2: Run the tests to verify the surface-integration test fails**

Run: `python3 -m pytest tests/ffl/test_e2e.py -v`

Expected: the existing API golden loop passes; the new surface test fails with `404` until the static routes are wired.

- [ ] **Step 3: Wire the reviewed static surfaces, complete any missing API payload, and write the local run guide**

Mount `ffl/static` at `/static` using `StaticFiles`; add `GET /field` and `GET /manager` routes that return their respective `index.html` files using `FileResponse`. Do not duplicate static content in Python.

`docs/ffl/LOCAL-RUN.md` must contain these exact commands:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn ffl.app:app --reload
```

It must link to `http://127.0.0.1:8000/field`, `http://127.0.0.1:8000/manager`, and `http://127.0.0.1:8000/docs`, and state that the default runtime writes SQLite data to `data/ffl.db`, which `FFL_DATABASE_PATH` can override.

- [ ] **Step 4: Run the focused and full suites**

Run: `python3 -m pytest tests/ffl -v`

Expected: PASS.

The legacy suite is known to fail collection under the mandated Python 3.9 runtime because the archived experiment uses Python 3.10 union syntax. Do not modify it for FFL V0; record that known non-FFL limitation in the final verification report instead.

- [ ] **Step 5: Commit**

```bash
git add ffl/app.py tests/ffl docs/ffl/LOCAL-RUN.md README.md
git commit -m "test: verify FFL golden operating loop"
```
