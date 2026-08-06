# Farm and Farmer Profiles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Give AGRO CEO compact manager-only Farm and Farmer profile panels that distinguish reviewed operating truth from reported TrackWick context and historical purchase context.

**Architecture:** A new farm_profiles service is the sole owner of canonical farm/person profile DTOs. Its FastAPI router is manager-only and returns either a reviewed profile or an explicit reported source-context profile; it never returns contacts, raw provider facts, media URLs, or source coordinates. The Next command centre loads a profile only after a card is opened and renders it in place.

**Tech Stack:** Python 3/FastAPI, SQLite and private Supabase/Postgres repository contract, pytest + FastAPI TestClient, Next.js 16/React 19/TypeScript, pnpm.

## Global Constraints

- The browser never receives provider IDs, raw payloads/forms, contact values, source coordinates, remote media URLs, or credentials.
- A TrackWick-reported farm/farmer remains reported until named Farm Truth review. It cannot create canonical farm truth, a map marker, login, work completion, recommendation, or compliance claim.
- Procurement aggregates are village/variety/month history only; never attribute them to a person or farm.
- Fields = farms; Farmers = grower relationships. Field workers are deferred.
- Keep WhatsApp visibly muted as Coming soon; no send, receive, configuration, or launch control.
- No real provider call, external dependency, seed data, or public API route.
  A task may add only a reviewed, column-limited Postgres runtime-read grant
  when a production privilege audit proves an existing server query needs it.

---

## File Structure

| File | Responsibility |
|---|---|
| ffl/services/farm_profiles.py | Whitelisted reviewed and reported profile DTOs. |
| ffl/api/farm_profile_routes.py | Manager-only profile endpoints and 404 boundary. |
| ffl/app.py | New router registration. |
| tests/ffl/test_farm_profile_routes.py | Profile state, cardinality, redaction, and route tests. |
| apps/web/components/command-centre.tsx | Lazy profile loading and one in-place panel per page. |
| apps/web/app/globals.css | Compact panel and muted WhatsApp row. |

### Task 1: Safe farm/farmer profile DTOs

**Files:**
- Create: ffl/services/farm_profiles.py
- Create: tests/ffl/test_farm_profile_routes.py

**Interfaces:**
- Consumes: canonical operational_blocks, block_parcels, crop_allocations, work_items, field_signals, people, and person_operating_relationships; existing manager_board_for_source.
- Produces: farm_profile(conn, block_id: str) -> dict | None, farmer_profile(conn, person_id: str) -> dict | None, reported_farm_profile(conn, candidate_id: str) -> dict | None, and reported_farmer_profile(conn, party_id: str) -> dict | None.

- [ ] **Step 1: Write the failing profile service tests**

~~~python
def test_farm_profile_returns_reviewed_truth_and_not_source_context(ffl_db, users, crop_allocation):
    grower = repository.create_person(ffl_db, "Asha Grower", "grower")
    repository.create_person_operating_relationship(
        ffl_db, grower.id, "crop_allocation", crop_allocation.id, "grower",
        "2026-06-01", provenance="reviewed contract", reviewed_by_person_id=users["manager"].id,
    )

    profile = farm_profiles.farm_profile(ffl_db, crop_allocation.operational_block_id)

    assert profile["state"] == "reviewed"
    assert profile["kind"] == "farm"
    assert profile["current"] == {"crop_name": "Rice", "cultivar": "Pusa 1121"}
    assert profile["people"] == [{
        "id": grower.id, "name": "Asha Grower", "role": "grower", "starts_on": "2026-06-01",
    }]
    assert profile["location"] == {"state": "not_published"}
    assert "provenance" not in repr(profile)
    assert "source" not in repr(profile)


def test_reported_farmer_profile_is_safe_context_not_a_login(ffl_db, populated_trackwick_source):
    profile = farm_profiles.reported_farmer_profile(ffl_db, populated_trackwick_source["farmer_id"])

    assert profile["state"] == "reported"
    assert profile["kind"] == "farmer"
    assert profile["account"] == {"state": "not_created"}
    assert set(profile) == {"state", "kind", "id", "name", "reported", "account", "limitations"}
    serialized = repr(profile)
    assert "9999999999" not in serialized
    assert "latitude" not in serialized
    assert "remote_url" not in serialized
~~~

- [ ] **Step 2: Run the service tests to verify they fail**

Run: .venv/bin/pytest -q tests/ffl/test_farm_profile_routes.py -k 'farm_profile or reported_farmer_profile'

Expected: FAIL during collection because ffl.services.farm_profiles does not exist.

- [ ] **Step 3: Implement the minimum safe service**

~~~python
def farm_profile(conn, block_id: str) -> dict | None:
    block = conn.execute(
        "SELECT id, name, area_hectares FROM operational_blocks WHERE id = ?", (block_id,)
    ).fetchone()
    if block is None:
        return None
    allocations = _active_allocations(conn, block_id)
    return {
        "state": "reviewed", "kind": "farm", "id": block["id"], "name": block["name"],
        "current": _current_crop(allocations),
        "people": _reviewed_people_for_block(conn, block["id"], allocations),
        "work": _reviewed_work_for_allocations(conn, [row["id"] for row in allocations]),
        "location": _published_geometry_state(conn, block["id"]),
    }


def reported_farmer_profile(conn, party_id: str) -> dict | None:
    row = next((item for item in manager_board_for_source(conn)["farmers"] if item["id"] == party_id), None)
    if row is None:
        return None
    return {
        "state": "reported", "kind": "farmer", "id": row["id"], "name": row["name"],
        "reported": _reported_farmer_summary(row), "account": {"state": "not_created"},
        "limitations": ["Reported source context is not a reviewed Fortune relationship or sign-in."],
    }
~~~

Implement _reviewed_people_for_block over active relationships scoped to the
block, linked parcel, or active allocation. Whitelist only id, name, role, and
starts_on. Implement reported variants by filtering the existing safe board
and omitting its location member entirely.

- [ ] **Step 4: Run the service tests to verify they pass**

Run: .venv/bin/pytest -q tests/ffl/test_farm_profile_routes.py -k 'farm_profile or reported_farmer_profile'

Expected: PASS; serialization proves no contact, coordinate, provider value, raw source field, or login claim can escape.

- [ ] **Step 5: Commit the service slice**

~~~bash
git add ffl/services/farm_profiles.py tests/ffl/test_farm_profile_routes.py
git commit -m "feat: add safe farm and farmer profiles"
~~~

### Task 2: Manager-only profile API

**Files:**
- Create: ffl/api/farm_profile_routes.py
- Modify: ffl/app.py:14-31,438-458
- Modify: tests/ffl/test_farm_profile_routes.py

**Interfaces:**
- Consumes: Task 1 service and ffl.communications.auth.require_manager.
- Produces: GET /api/v1/farm-profiles/{block_id}, GET /api/v1/farmer-profiles/{person_id}, GET /api/v1/reported-farm-profiles/{candidate_id}, and GET /api/v1/reported-farmer-profiles/{party_id}.

- [ ] **Step 1: Write failing access and absence tests**

~~~python
def test_profile_routes_require_manager_and_distinguish_absence(tmp_path):
    app = create_app(str(tmp_path / "profiles.db"), manager_api_token="manager-secret")
    with TestClient(app) as client:
        manager = repository.create_person(app.state.conn, "Fortune COO", "operations_lead")
        app.state.manager_person_id = manager.id
        denied = client.get("/api/v1/farm-profiles/missing")
        absent = client.get(
            "/api/v1/farm-profiles/missing", headers={"X-FFL-Manager-Token": "manager-secret"}
        )

    assert denied.status_code == 403
    assert absent.status_code == 404
    assert absent.json() == {"detail": "farm profile not found"}
~~~

- [ ] **Step 2: Run route tests to verify they fail**

Run: .venv/bin/pytest -q tests/ffl/test_farm_profile_routes.py -k profile_routes

Expected: FAIL because the new router has not been registered.

- [ ] **Step 3: Implement guarded routes and register them**

~~~python
router = APIRouter(prefix="/api/v1")


@router.get("/farm-profiles/{block_id}")
def get_farm_profile(request: Request, block_id: str, _manager_id: str = Depends(require_manager)) -> dict:
    profile = farm_profiles.farm_profile(_connection(request), block_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="farm profile not found")
    return profile
~~~

Create the farmer and reported equivalents with exact singular 404 messages.
Use _connection(request) as existing routes do. Import and include
farm_profile_router in ffl/app.py beside other manager-only routers. Never
accept a caller-supplied manager identity.

- [ ] **Step 4: Run route tests to verify they pass**

Run: .venv/bin/pytest -q tests/ffl/test_farm_profile_routes.py -k profile_routes

Expected: PASS; unauthorized access is denied and no raw source data is present.

- [ ] **Step 5: Commit the API slice**

~~~bash
git add ffl/api/farm_profile_routes.py ffl/app.py tests/ffl/test_farm_profile_routes.py
git commit -m "feat: expose manager farm profiles"
~~~

### Task 3: Focused in-place profile panels and WhatsApp status

**Files:**
- Modify: apps/web/components/command-centre.tsx:80-540
- Modify: apps/web/app/globals.css:114-170
- Modify: tests/ffl/test_farm_profile_routes.py

**Interfaces:**
- Consumes: Task 2 GET routes and current Runtime / TrackwickBoard.
- Produces: lazy profile selection, ProfilePanel, and non-interactive disabled-connection row.

- [ ] **Step 1: Write the failing web-shell contract test**

~~~python
def test_command_centre_has_on_demand_profiles_and_muted_whatsapp_status():
    source = Path("apps/web/components/command-centre.tsx").read_text()

    assert 'readJson<FarmProfile>("/api/v1/farm-profiles/" + id)' in source
    assert 'readJson<FarmerProfile>("/api/v1/farmer-profiles/" + id)' in source
    assert "WhatsApp updates" in source
    assert "Coming soon" in source
    assert "disabled-connection" in source
~~~

The repository has no browser-test runner. This small rendering contract is
paired with the real TypeScript typecheck and production Next build.

- [ ] **Step 2: Run web-shell test to verify it fails**

Run: .venv/bin/pytest -q tests/ffl/test_farm_profile_routes.py -k command_centre

Expected: FAIL because no on-demand profile fetches or muted row exist.

- [ ] **Step 3: Implement one in-place panel**

~~~tsx
type FarmProfile = { state: "reviewed" | "reported"; kind: "farm"; id: string; name: string };
type FarmerProfile = { state: "reviewed" | "reported"; kind: "farmer"; id: string; name: string };

function ProfilePanel({ profile, close }: {
  profile: FarmProfile | FarmerProfile; close: () => void;
}) {
  return <aside className="profile-panel" aria-label={profile.name + " profile"}>
    <button className="quiet-button" onClick={close}>Back</button>
    <p className="eyebrow">{profile.state === "reviewed" ? "Reviewed record" : "Reported context"}</p>
    <h2>{profile.name}</h2>
  </aside>;
}
~~~

Keep selection state in CommandCentre; fetch only when a card opens; show
loading or error inside that page. Make Field/Farmer cards buttons with clear
profile-opening action. A reported panel's only primary action is Review in
Farm Truth; a reviewed farm links to its work. Do not show field workers on
the Farmers screen.

Add this non-clickable Settings row:

~~~tsx
<div className="disabled-connection" aria-disabled="true">
  <strong>WhatsApp updates <em>Coming soon</em></strong>
  <span>Named requests and reviewable evidence will arrive here after the separate launch gate. WhatsApp never decides or closes work.</span>
</div>
~~~

Style profile-panel as a compact in-flow reading path, and
disabled-connection at reduced contrast with no button/link styling. Maintain
the existing one-screen desktop surface and mobile single column.

- [ ] **Step 4: Run web verification to verify it passes**

Run: .venv/bin/pytest -q tests/ffl/test_farm_profile_routes.py -k command_centre && pnpm --dir apps/web typecheck && pnpm --dir apps/web build

Expected: test passes; TypeScript exits 0; production Next build completes.

- [ ] **Step 5: Commit the web slice**

~~~bash
git add apps/web/components/command-centre.tsx apps/web/app/globals.css tests/ffl/test_farm_profile_routes.py
git commit -m "feat: add farm and farmer profile panels"
~~~

### Task 4: Close final audit profile-content gaps

**Files:**
- Modify: ffl/services/farm_profiles.py
- Modify: apps/web/components/command-centre.tsx
- Modify: apps/web/app/globals.css
- Modify: tests/ffl/test_farm_profile_routes.py

**Interfaces:**
- Consumes: Task 1 safe profile service and Task 3 profile UI.
- Produces: complete, still-whitelisted reviewed/reported profile details. The
  farm DTO gains record metadata; the farmer DTO gains safe linked-farm
  context; neither response gains source identifiers, contacts, coordinates,
  raw evidence, or an account claim.

- [ ] **Step 1: Write focused failing content and boundary tests**

~~~python
def test_reviewed_farmer_profile_lists_linked_farm_crop_and_open_work(ffl_db, users, crop_allocation):
    grower = repository.create_person(ffl_db, "Asha Grower", "operations_lead")
    repository.create_person_operating_relationship(
        ffl_db, grower.id, "crop_allocation", crop_allocation.id, "grower",
        "2026-06-01", provenance="reviewed", reviewed_by_person_id=users["manager"].id,
    )

    profile = farm_profiles.farmer_profile(ffl_db, grower.id)

    assert profile["relationships"] == [{
        "scope_type": "crop_allocation", "scope_name": "North Block",
        "role": "grower", "starts_on": "2026-06-01",
    }]
    assert profile["farms"] == [{
        "id": crop_allocation.operational_block_id, "name": "North Block",
        "current": {"crop_name": "Rice", "cultivar": "Pusa 1121"}, "open_work_count": 0,
    }]


def test_command_centre_renders_profile_context_without_field_worker_surface():
    source = Path("apps/web/components/command-centre.tsx").read_text()

    assert "Latest activity" in source
    assert "Photo references" in source
    assert "Linked farms" in source
    assert "Field record" in source
    assert "item.field_worker_name" not in source
~~~

- [ ] **Step 2: Run focused tests to verify they fail**

Run: /Users/dakshbhatia/Documents/field-monitor/.venv/bin/pytest -q tests/ffl/test_farm_profile_routes.py -k 'linked_farm or profile_context'

Expected: FAIL because linked-farm DTO content and the displayed profile
context are not implemented yet.

- [ ] **Step 3: Add only safe, contextual DTO fields**

~~~python
def farmer_profile(conn, person_id: str) -> dict[str, Any] | None:
    # Keep all relationship history/contacts/provenance private.
    relationships = _reviewed_relationships_for_person(conn, person_id)
    return {
        "state": "reviewed", "kind": "farmer", "id": person["id"], "name": person["name"],
        "relationships": relationships,
        "farms": _linked_farms_for_reviewed_relationships(conn, person_id),
    }
~~~

Each relationship may contain only scope_type, scope_name, role, and
starts_on. Each linked farm may contain only block id/name, current
crop/cultivar, and open_work_count. For reviewed farm records, add
record.latest_observed_at from canonical non-draft field-signal metadata and
record.limitation as a fixed sentence; do not return signal payload/content.
Keep reported latest activity and photo reference values as counts/dates only.

- [ ] **Step 4: Render the missing profile modules without new surfaces**

Render reported latest activity and photo-reference totals inside the existing
profile facts. Render a reviewed farm **Field record** group with latest
observed time and fixed limitation. Render a reviewed farmer **Linked farms**
group with each farm's current crop and open-work count, then the existing
reviewed relationship role/date list using scope_name. Remove field-worker
name interpolation from SourceWorkRows; source tasks remain tasks, but field
workers get no product presentation until their dedicated slice.

- [ ] **Step 5: Run focused green tests and production checks**

Run: /Users/dakshbhatia/Documents/field-monitor/.venv/bin/pytest -q tests/ffl/test_farm_profile_routes.py && pnpm --dir apps/web typecheck && pnpm --dir apps/web build && git diff --check

Expected: all profile tests pass, TypeScript exits 0, Next production build
completes, and no whitespace issue remains.

- [ ] **Step 6: Commit the audit closure**

~~~bash
git add ffl/services/farm_profiles.py apps/web/components/command-centre.tsx apps/web/app/globals.css tests/ffl/test_farm_profile_routes.py docs/superpowers/plans/2026-08-06-farm-and-farmer-profiles.md
git commit -m "fix: complete farm and farmer profile context"
~~~

### Task 5: Repair the production runtime-read boundary

**Files:**
- Create: db/postgres/0017_agro_profile_runtime_read_grants.sql
- Modify: ffl/services/farm_profiles.py
- Modify: ffl/api/routes.py
- Modify: tests/ffl/test_vc_runtime_privileges.py
- Modify: tests/ffl/test_farm_profile_routes.py

**Interfaces:**
- Consumes: private agro schema and the existing agro_vc_runtime server role.
- Produces: an explicit, column-limited read grant for the safe work/field
  observation metadata the profile and runtime DTOs need. It does not grant
  raw signal values, evidence IDs, owners, contacts, source fields, writes,
  schema control, or Data API access.

- [ ] **Step 1: Write failing production-privilege and cross-dialect tests**

~~~python
def test_profile_runtime_grant_exposes_only_safe_summary_columns():
    sql = (ROOT / "db/postgres/0017_agro_profile_runtime_read_grants.sql").read_text()
    compact = " ".join(sql.split())

    assert "GRANT SELECT (id, allocation_id, title, status) ON TABLE agro_work_items" in compact
    assert "GRANT SELECT (allocation_id, observed_at, received_at, actor_id, status, created_at) ON TABLE agro_field_signals" in compact
    assert "values_json" not in sql
    assert "evidence_artifact_id" not in sql
    assert "GRANT ALL" not in sql


def test_farm_profile_latest_observation_compares_instants_not_sqlite_text_order(ffl_db, crop_allocation):
    # 09:30Z is later than 10:00+05:30 despite sorting before it as text.
    _record_signal(ffl_db, crop_allocation.id, observed_at="2026-08-01T10:00:00+05:30")
    _record_signal(ffl_db, crop_allocation.id, observed_at="2026-08-01T09:30:00+00:00")

    profile = farm_profiles.farm_profile(ffl_db, crop_allocation.operational_block_id)

    assert profile["record"]["latest_observed_at"] == "2026-08-01T09:30:00+00:00"
~~~

- [ ] **Step 2: Run the tests to verify they fail**

Run: /Users/dakshbhatia/Documents/field-monitor/.venv/bin/pytest -q tests/ffl/test_vc_runtime_privileges.py tests/ffl/test_farm_profile_routes.py -k 'profile_runtime_grant or latest_observation'

Expected: FAIL because migration 0017 does not exist and the SQLite query still
orders timestamp text lexically.

- [ ] **Step 3: Implement the least-privilege production path**

~~~sql
BEGIN;
SET LOCAL search_path = agro, pg_catalog;
GRANT SELECT (id, allocation_id, title, status)
ON TABLE agro_work_items TO agro_vc_runtime;
GRANT SELECT (allocation_id, observed_at, received_at, actor_id, status, created_at)
ON TABLE agro_field_signals TO agro_vc_runtime;
COMMIT;
~~~

Modify runtime work serialization to select only id, allocation_id, title and
status rather than SELECT star. In farm_profiles, select only safe timestamp
metadata and calculate the latest instant in Python with timezone-aware
datetime parsing; return the original accepted timestamp string. Use the same
open-work status set as portfolio/season logic. Never query signal values,
evidence, owner, template, or source columns.

- [ ] **Step 4: Run focused green tests and full targeted checks**

Run: /Users/dakshbhatia/Documents/field-monitor/.venv/bin/pytest -q tests/ffl/test_vc_runtime_privileges.py tests/ffl/test_farm_profile_routes.py tests/ffl/test_api.py && git diff --check

Expected: all tests pass and no whitespace error remains.

- [ ] **Step 5: Commit the runtime fix**

~~~bash
git add db/postgres/0017_agro_profile_runtime_read_grants.sql ffl/services/farm_profiles.py ffl/api/routes.py tests/ffl/test_vc_runtime_privileges.py tests/ffl/test_farm_profile_routes.py docs/superpowers/plans/2026-08-06-farm-and-farmer-profiles.md
git commit -m "fix: grant safe profile runtime reads"
~~~

### Task 6: Close the whole-branch safety and truth-boundary review

**Files:**
- Modify: ffl/services/trackwick_board.py
- Modify: ffl/api/trackwick_routes.py
- Modify: ffl/services/farm_profiles.py
- Modify: ffl/api/routes.py
- Modify: apps/web/components/command-centre.tsx
- Modify: tests/ffl/test_trackwick_board.py
- Modify: tests/ffl/test_farm_profile_routes.py
- Modify: tests/ffl/test_api.py

**Interfaces:**
- Produces a manager-authorised, command-centre-safe TrackWick DTO. It must
  contain only whitelisted reported labels, counts, and dates. Browser-facing
  responses must not contain a map, location/coordinates, field-worker
  material, provider tags/statuses/identifiers, raw registration/source-form
  values, media URLs, contacts, or a source payload.
- Runtime separately returns reviewed canonical operational blocks so a real
  farm remains discoverable without an active crop allocation.

- [x] **Step 1: Add failing regression tests for the browser boundary**

Add an authenticated command-centre board route test that serializes the
response and proves it omits `map`, `location`, `latitude`, `longitude`,
`crm_status`, `provider_tag`, `field_worker`, and raw registration variants.
Keep the exact whitelisted reported count/date semantics. Add a source-shell
test that proves the Next command centre reads this safe endpoint rather than
the private board route.

- [x] **Step 2: Create an explicit safe source projection**

Make a literal allowlist projection for the command-centre response (or safely
replace the existing browser route) with only source state, safe aggregate
counts, reported farms/farmers, and optionally redacted source inbox rows. Do
not calculate or carry a location/map/worker/provider value into that DTO.
The manager profile service may consume the safe projection for reported
profiles; remove unapproved `registration_status`, PB1, and 1718-area fields
from its reported-farm DTO. The web shell must only load the safe board after
manager access is known to be active.

- [x] **Step 3: Restore reviewed relationship and farm discovery truth**

Require active named-reviewer relationships everywhere a reviewed grower is
shown. A farmer profile is 404 unless an active reviewed `grower` relationship
exists. Farmer cards, relationships, and linked farms include only reviewed
grower relationships. Farm People includes only active reviewed `grower` or
`field_operator` relationships scoped directly to the block, a linked parcel,
an allocation, or the block's operating unit, with stable deduplication.
Runtime must filter relationships to reviewed entries and add a safe
`reviewed_farms` list from canonical blocks regardless of allocations; the
Field page uses it, adding current allocation context only when present.

- [x] **Step 4: Make work and expired access honest**

Return only open work (`planned`, `in_progress`, `blocked`, `submitted`,
`rejected`) in the reviewed farm profile, with a server-provided count; do not
let the UI reinterpret terminal statuses. On a profile 403, clear the stale
manager session, restore focus safely, and show a direct `/manager` re-auth
path instead of a generic read failure. Keep the farm work CTA truthful and
unscoped ("Open actions").

- [x] **Step 5: Verify the full closure**

Run:

~~~bash
.venv/bin/pytest -q tests/ffl
pnpm --dir apps/web typecheck
pnpm --dir apps/web build
git diff --check
~~~

Expected: all tests pass, the browser route is provably redacted, all reviewed
truth uses reviewed grower relationships, and the production web build exits
0.

- [ ] **Step 6: Commit the closure**

~~~bash
git add ffl/services/trackwick_board.py ffl/api/trackwick_routes.py ffl/services/farm_profiles.py ffl/api/routes.py apps/web/components/command-centre.tsx tests/ffl/test_trackwick_board.py tests/ffl/test_farm_profile_routes.py tests/ffl/test_api.py docs/superpowers/plans/2026-08-06-farm-and-farmer-profiles.md
git commit -m "fix: close farm profile safety boundaries"
~~~

### Task 7: Complete verification and deployment handoff

**Files:**
- Modify: docs/superpowers/plans/2026-08-06-farm-and-farmer-profiles.md (checkboxes only)

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: verified code ready for main-branch auto-deploy.

- [ ] **Step 1: Compare code to the approved design**

Verify these exact points against
docs/superpowers/specs/2026-08-06-farm-and-farmer-profiles-design.md:

~~~text
Reviewed/reported state separated
Farm/farmer many-to-many relationship preserved
Historical history not attributed
No source contact/coordinate/media data serialized
No field-worker product surface
WhatsApp Coming soon is visible and non-functional
~~~

- [ ] **Step 2: Run the complete FFL suite**

Run: .venv/bin/pytest -q tests/ffl

Expected: exit 0. Record the final pass count and any warnings.

- [ ] **Step 3: Run production web verification**

Run: pnpm --dir apps/web typecheck && pnpm --dir apps/web build

Expected: exit 0 for both TypeScript and production Next build.

- [ ] **Step 4: Inspect final diff for forbidden changes**

Run: git diff 7c06fd4..HEAD --check && git diff 7c06fd4..HEAD --stat && git status --short

Expected: no whitespace errors; no secret, .env, migration, generated build
output, or unrelated dirty file is staged.

- [ ] **Step 5: Commit plan tracking and push**

~~~bash
git add docs/superpowers/plans/2026-08-06-farm-and-farmer-profiles.md
git commit -m "docs: record farm profile delivery plan"
git push origin main
~~~

After configured GitHub/Vercel deployment completes, verify the latest web and
API deployments are READY and review their recent runtime-error feeds. Do not
make a TrackWick call or enable WhatsApp.
