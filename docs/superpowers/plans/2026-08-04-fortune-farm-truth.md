# Fortune Farm Truth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a Fortune manager turn a small, evidence-backed set of TrackWick farmer registrations and field visits into reviewed Farm Truth records: a real farm/field, grower relationship, crop allocation, right-to-operate basis, and durable source links.

**Architecture:** TrackWick remains read-only source evidence in private `agro` tables. A deterministic candidate service creates private, per-registration-plot review cases; a manager-only API presents safe summaries and atomically accepts a case into the canonical operating model. The existing Farms view opens one focused review sheet, and Inbox surfaces only cases needing evidence. Maps continue to render reviewed manifest geometry only.

**Tech Stack:** FastAPI, Pydantic, SQLite test mirror, private Supabase/Postgres `agro` schema, vanilla manager JavaScript/CSS, pytest.

## Global Constraints

- Keep the six top-level manager tabs exactly as they are: Home, Farms, Farmers, Field workers, Inbox, Settings. Farm Truth opens from Farms; it is not a new navigation system.
- Source data is read-only. Never write to TrackWick, call it from the browser, expose its credentials, or send source provider identifiers to a client.
- Only `require_manager(request)` authorizes these routes. The server derives the reviewer/owner identity; no client-provided reviewer identity is trusted.
- Never return or display raw phone numbers, Aadhaar/identity material, GPS coordinates, raw media URLs, unreviewed source-map points, or free-text source answers.
- A candidate is one TrackWick registration + one registration plot. Do not merge plots heuristically. A duplicate reviewed plot must not create a second canonical field.
- A candidate is eligible only when its registration is completed/valid, has a linked farmer and valid plot area, and has at least one completed Farmer Visit inside the selected current-season window. Prioritize open linked work, then visit recency, then registration recency; return readable reasons, never an opaque score.
- Acceptance is one database transaction. On any failure, canonical records, source links, review status, and audit event all roll back. Use a case claim transition (`open` to `accepting`) to make retries/concurrent clicks idempotent.
- Acceptance creates a land parcel, operational block, parcel-block link, dated right-to-operate, active crop allocation, grower relationship, reviewed TrackWick party/plot links, selected task/allocation links where relevant, and an audit event. Field-worker assignment is optional and only made when the source task supports it.
- `Needs evidence` and `Reject` create no canonical farm records. Needs-evidence cases become a manager-owned Inbox item using the review case itself; do not misuse field information requests before an allocation exists.
- New relations stay private: no `anon`/`authenticated` grants, PostgREST exposure, broad `ALL`, schema grants, or delete grants. Runtime gets only the minimum `SELECT, INSERT, UPDATE` privileges necessary.
- All added interface copy must exist in both `en` and `hi`, with short, natural Hindi—not a partly English page. No sample/setup/meta commentary in the manager flow.

---

## Data contract

### Private review-case table

Create `agro_farm_truth_review_cases` (and its SQLite mirror `farm_truth_review_cases`) with:

| Field | Purpose |
| --- | --- |
| `id` | stable private review-case identifier |
| `source_id`, `registration_id`, `plot_id` | exact TrackWick evidence unit |
| `candidate_fingerprint` | SHA-256 of registration/plot/source-task evidence; a changed source receipt creates a new reviewable case |
| `status` | `open`, `accepting`, `needs_evidence`, `accepted`, or `rejected` |
| `evidence_summary_json` | server-generated safe facts/reasons only—not raw source payload |
| `review_reason`, `missing_evidence_kind` | required decision context; missing kind is `plot_area`, `crop_season`, `right_to_operate`, `farmer_identity`, or `field_worker_assignment` |
| `owner_person_id`, `reviewed_by_person_id`, `reviewed_at` | manager accountability; needs-evidence owner defaults to the acting manager |
| accepted IDs | parcel, block, crop allocation, grower and optional field worker created by acceptance |
| timestamps | queue freshness and auditability |

Use `UNIQUE(plot_id, candidate_fingerprint)`. Add check constraints so terminal actions have a reviewer/time and accepted cases have all required canonical IDs. Add an update trigger/check so only `open → accepting|needs_evidence|rejected` and `accepting → accepted` are permitted; a failed transaction returns the claim to `open` automatically.

### API contract

- `POST /api/v1/farm-truth/refresh` — manager-only; computes eligible candidates from already-synced private TrackWick rows and upserts open review cases. It never calls TrackWick.
- `GET /api/v1/farm-truth/cases?status=open&limit=50` — manager-only; returns a bounded safe card summary and clear evidence reasons. No mutation.
- `GET /api/v1/farm-truth/cases/{case_id}` — manager-only; returns safe detail: place/area, registration date, crop/timing context, selected recent visit count, open work count, display names, and safe task labels.
- `POST /api/v1/farm-truth/cases/{case_id}/accept` — manager-only; strict body: existing operating unit/season, field name, managed area in hectares, crop/cultivar, grower effective date, right type/start/end, and optional supported field worker. Returns the accepted canonical IDs and stable case status.
- `POST /api/v1/farm-truth/cases/{case_id}/needs-evidence` — manager-only; strict allowed missing-evidence kind and concise reason. The current manager becomes the owner.
- `POST /api/v1/farm-truth/cases/{case_id}/reject` — manager-only; strict concise reason.

All responses use only safe names/labels and reviewed canonical IDs. `409` communicates a stale/claimed/already-resolved case, and a retry of an already accepted case returns its existing accepted result.

## Tasks

### Task 1: Add the private review-case schema and transactional repository seam

**Files:**
- Modify: `ffl/persistence/schema.py`
- Create: `db/postgres/0014_agro_farm_truth_review.sql`
- Modify: `ffl/persistence/repository.py`
- Create: `tests/ffl/test_farm_truth_repository.py`

- [ ] Write failing SQLite repository tests for: creation of an open case; enforced one-case-per-plot-fingerprint uniqueness; allowed lifecycle transitions; accepted case idempotency; and full rollback when a required canonical write fails.
- [ ] Run `./.venv/bin/pytest -q tests/ffl/test_farm_truth_repository.py` and confirm the tests fail because the relation/repository functions do not exist.
- [ ] Add the SQLite `farm_truth_review_cases` table after the TrackWick linkage tables. Mirror the Postgres constraints, foreign keys, lifecycle trigger, `UNIQUE(plot_id, candidate_fingerprint)`, reviewed/accepted checks, and indexes on `(status, updated_at)` and `(registration_id, plot_id)`.
- [ ] Add `0014_agro_farm_truth_review.sql` using only `agro_` table names. Create the private table, constraints, transition trigger, indexes, and minimal `agro_vc_runtime` `SELECT, INSERT, UPDATE` grants; explicitly retain revokes from `anon` and `authenticated` and add no schema/table-wide permissions.
- [ ] Add repository types and functions in `ffl/persistence/repository.py`: `FarmTruthReviewCase`, `create_or_refresh_farm_truth_case`, `list_farm_truth_cases`, `get_farm_truth_case`, `claim_farm_truth_case`, `mark_farm_truth_case_needs_evidence`, `mark_farm_truth_case_rejected`, and `accept_farm_truth_case`.
- [ ] Implement `accept_farm_truth_case` as a single `with conn:` transaction, directly inserting the required canonical rows and reviewed TrackWick link rows with `_new_identity()`. It must re-read/claim the case inside the transaction, return an existing accepted result on retry, reject a plot already carrying a reviewed plot-operating link, and emit an `agro_audit_events` record with case ID and source IDs as metadata.
- [ ] Run `./.venv/bin/pytest -q tests/ffl/test_farm_truth_repository.py` and confirm all new tests pass.
- [ ] Commit with `feat: add private farm truth review persistence`.

### Task 2: Build deterministic safe candidate discovery from TrackWick evidence

**Files:**
- Create: `ffl/services/farm_truth.py`
- Modify: `ffl/persistence/repository.py`
- Create: `tests/ffl/test_farm_truth_service.py`

- [ ] Write failing service tests that seed normalized TrackWick registrations, `Plot Details`, linked farmer parties, and Farmer Visit tasks. Cover eligibility, rejection of missing/zero plot area, current-season visit filtering, priority order, fingerprint stability/change, readable evidence reasons, and omission of contacts/GPS/media/raw form text from every returned summary.
- [ ] Run `./.venv/bin/pytest -q tests/ffl/test_farm_truth_service.py` and confirm failure because the service is absent.
- [ ] Implement `refresh_farm_truth_cases(conn, operating_unit_id, season_id, actor_id)` in `ffl/services/farm_truth.py`. Read only private typed TrackWick tables and reviewed source links. Resolve the selected season date window from `agro_seasons`; filter completed registrations and completed `Farmer Visit` tasks in that window; require positive `reported_area_bigha` or positive registration area.
- [ ] Model each candidate as `(registration_id, plot_id)`. Derive its SHA-256 fingerprint from registration/plot source fingerprints plus sorted eligible task IDs/fingerprints/statuses. Generate only safe evidence: village/block/district, Gata number, reported area, registration date, crop/timing facts already normalized, counts, display names, and short reason chips such as `Registration + 2 recent visits + open follow-up`.
- [ ] Use transparent sort keys: linked open work descending, latest completed visit descending, registration observation descending. Bound the returned queue to 50, but retain all cases in storage.
- [ ] Implement safe detail/list serializers and an owner Inbox serializer. They must never select or serialize `trackwick_contact_points`, `trackwick_locations`, `trackwick_media`, provider identifiers, or raw payload fields.
- [ ] Run `./.venv/bin/pytest -q tests/ffl/test_farm_truth_service.py` and confirm all tests pass.
- [ ] Commit with `feat: derive safe farm truth candidates from TrackWick`.

### Task 3: Expose the manager-only Farm Truth API

**Files:**
- Create: `ffl/api/farm_truth_routes.py`
- Modify: `ffl/app.py`
- Create: `tests/ffl/test_farm_truth_routes.py`

- [ ] Write failing route tests for every endpoint: unauthenticated requests are denied; manager identity comes from `require_manager`; refresh/list/detail return safe response shapes; accept requires strict valid inputs; needs-evidence/reject require nonempty bounded reasons; stale or terminal cases return `409`; and no request body can set `reviewed_by_person_id` or owner.
- [ ] Run `./.venv/bin/pytest -q tests/ffl/test_farm_truth_routes.py` and confirm failure because the router is not registered.
- [ ] Add a Pydantic route module under prefix `/api/v1/farm-truth`. Use `require_manager` in every handler and service/repository functions only—never browser-supplied identity or direct TrackWick calls.
- [ ] Define strict acceptance fields: `operating_unit_id`, `season_id`, `field_name` (1–160 chars), `managed_area_hectares` (>0), `crop_name`, optional `cultivar`, `grower_effective_on`, `right_type`, `right_starts_on`, optional `right_ends_on`, and optional `field_worker_party_id`. Validate all IDs exist, the season belongs to that operating unit, dates are coherent, and an optional worker is supported by the selected source evidence.
- [ ] Register the router in `ffl/app.py` alongside the existing manager-only TrackWick routes.
- [ ] Run `./.venv/bin/pytest -q tests/ffl/test_farm_truth_routes.py tests/ffl/test_trackwick_routes.py` and confirm all pass.
- [ ] Commit with `feat: add manager farm truth review API`.

### Task 4: Make Farms the single calm manager review surface and protect map truth

**Files:**
- Modify: `ffl/static/manager/index.html`
- Modify: `ffl/static/manager/app.js`
- Modify: `ffl/static/manager/styles.css`
- Modify: `tests/ffl/test_manager_assets.py`

- [ ] Write/update failing manager asset tests to assert exactly six tab buttons remain; Farms contains `farm-truth-open`; the review dialog and Farm Truth endpoints exist; English and Hindi copy contain all review actions/states; and the map rendering path does not merge `sourceBoardFeatureCollection()` or source GPS points into Home/Farms geometry.
- [ ] Run `./.venv/bin/pytest -q tests/ffl/test_manager_assets.py` and confirm the targeted assertions fail.
- [ ] Add one quiet `Review candidates` action to the existing Farms toolbar and a manager-session-gated `farm-truth-dialog`. The dialog shows one candidate at a time: identity-safe place/area/crop/visit/work facts, readable evidence chips, a concise acceptance form, and three actions: Accept, Needs evidence, Reject. Cards are clickable; there is no KPI wall, sample data, setup language, or extra navigation.
- [ ] Add local state and fetch functions for `refresh`, list, detail, accept, needs-evidence, and reject. Refresh only when the manager opens the review flow or explicitly refreshes it; ordinary `GET` rendering remains read-only. On a successful decision, move directly to the next case without reloading the page.
- [ ] Add a small Inbox merge that lists only `needs_evidence` Farm Truth cases as owned requests. Reuse the existing Inbox visual language rather than creating a second inbox.
- [ ] Remove raw-source feature collection from `renderBestMap`; render only published reviewed manifest geometry. Where no reviewed geometry exists, state that clearly without displaying source locations or counts as map pins.
- [ ] Add compact, responsive CSS for the single-card review sheet, evidence chips, and decision controls. Preserve keyboard dialog behavior, focus states, safe text escaping, and the existing narrow-screen layout.
- [ ] Run `./.venv/bin/pytest -q tests/ffl/test_manager_assets.py` and confirm all asset/privacy/navigation checks pass.
- [ ] Commit with `feat: add focused farm truth review to Farms`.

### Task 5: Prove the end-to-end contract, document rollout, and verify production-safe migrations

**Files:**
- Modify: `tests/ffl/test_farm_truth_service.py`
- Modify: `tests/ffl/test_farm_truth_routes.py`
- Modify: `docs/ffl/OPERATING-ARCHITECTURE.md`
- Modify: `docs/ffl/TRACKWICK-INTEGRATION.md`
- Create: `docs/ffl/FARM-TRUTH-REVIEW.md`

- [ ] Add an end-to-end test that seeds one farmer, registration, plot, eligible visit, and optional field worker; refreshes the case; accepts it; then asserts exactly one canonical parcel/block/allocation/grower relation/right/link set/audit event exists, the case is accepted, and a repeated accept returns the same IDs. Add companion needs-evidence and rejection tests proving zero canonical writes.
- [ ] Run `./.venv/bin/pytest -q tests/ffl/test_farm_truth_service.py tests/ffl/test_farm_truth_routes.py` and confirm the end-to-end tests fail before any missing edge implementation is completed.
- [ ] Complete only the minimal implementation required for the tests, including deterministic safe error responses and idempotent replay behavior.
- [ ] Document the boundary in `docs/ffl/OPERATING-ARCHITECTURE.md`: TrackWick evidence is private/read-only; reviewed Farm Truth is the canonical bridge; maps consume published reviewed geometry only.
- [ ] Update `docs/ffl/TRACKWICK-INTEGRATION.md` with the candidate evidence used, explicit fields intentionally excluded (phone, Aadhaar, raw GPS, media, raw form text), and source-link/audit behaviour.
- [ ] Add `docs/ffl/FARM-TRUTH-REVIEW.md`: choose operating unit/season; review one candidate; meaning of each decision; what `Needs evidence` does; why map publication remains a separate geometry-manifest review; and the first-session success criterion (25 accepted records, not a bulk import).
- [ ] Run `./.venv/bin/pytest -q tests/ffl`.
- [ ] Run `git diff --check` and inspect `git diff -- db/postgres/0014_agro_farm_truth_review.sql` to verify no public grants, no delete/broad grants, no credentials, and no raw contact/location/media serialization.
- [ ] Commit with `docs: define Farm Truth review rollout`.

## Verification checklist

- [ ] Fresh TrackWick evidence has not been copied or overwritten; Farm Truth refresh uses only already-ingested typed tables.
- [ ] A manager can finish one evidence-backed candidate in a few deliberate inputs and immediately proceed to the next one.
- [ ] A concurrent/double accept cannot create duplicate parcels, blocks, allocations, source links, or audit records.
- [ ] Needs-evidence and rejection remain accountable, visible in Inbox where appropriate, and make no canonical farm claims.
- [ ] Browser/static/API responses contain no TrackWick credentials, raw contact data, raw GPS, source media, provider identifiers, Aadhaar material, or free-text source payload.
- [ ] Home and Farms maps are backed only by reviewed published geometry.
- [ ] The complete FFL test suite passes before deploy; deployment comes after the 25-record manager review, not before it.
