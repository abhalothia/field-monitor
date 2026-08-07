# WhatsApp Communications Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a role-, consent-, and operating-scope-aware WhatsApp control plane that lets verified owners/admins command AGRO CEO while giving farmers and field workers safe, contextual workflows.

**Architecture:** Preserve the existing sealed-receipt/provider-worker foundation, but add a communications profile and policy layer before it may resolve a message. Versioned workflows create recipient/allocation-specific interaction runs; a dispatcher sends approved LoopMessage WhatsApp templates; inbound messages correlate to exactly one run. Owner/admin commands produce typed proposals and execute only through allow-listed canonical services after a short-lived WhatsApp confirmation.

**Tech Stack:** Python 3, FastAPI, SQLite test runtime, private PostgreSQL/Supabase schema, Pydantic, pytest, LoopMessage provider port, Next.js/React manager UI, Hetzner systemd worker.

## Global Constraints

- Keep `agro` and communications data private; do not add it to Supabase Data API or browser access.
- Never infer a person, role, farm, or allocation from phone number, display name, language, prior chat, or a source CRM record.
- Resolve every field-facing message through endpoint verification, active portal membership, active purpose/scope consent, and effective operating scope.
- Existing provider delivery/read status must never close work, approve evidence, establish consent, or publish agronomic advice.
- Use an immutable interaction/campaign/template/policy snapshot for every outbound send and an immutable event/candidate/evidence link for every inbound item.
- Keep raw provider payloads, phone values, remote media URLs, credentials, and arbitrary conversation content out of routine APIs and logs.
- Production worker and receipt handling remain private Hetzner responsibilities; Vercel/browser code must not receive provider secrets or receipt keys.
- Use real LoopMessage WhatsApp templates/parameters only after the documented sandbox contract is proven. Do not enable live traffic by a configuration flag alone.
- Implement new behavior test-first and commit each independently testable task with only the files named in that task.

---

## File structure and release boundaries

The PRD spans four independently releasable subsystems. Implement in this order
because each layer is a safety dependency of the next.

| Release | New units | Existing units changed | Outcome |
|---|---|---|---|
| A. Context foundation | `ffl/communications/identity.py`, `policy.py`, `interactions.py` | persistence, private Postgres/SQLite schemas, tests | A number can be classified safely by portal role, consent, and allocation scope. |
| B. Field workflows | `workflows.py`, `outbox.py`, `scheduler.py` | LoopMessage port, worker, field-information request adapter, routes | One worker/farmer interaction can be sent and correlated without the one-open-prompt heuristic. |
| C. Command and campaigns | `commands.py`, `campaigns.py`, `audience.py` | policy, outbox, routes, worker | Owner/admin commands and governed bulk sends execute through typed proposals and snapshots. |
| D. Manager surface and controlled rollout | communications API router and React components | app routing, command centre, deployment docs | Managers can configure/operate the system without a chat archive or raw-source leak. |

Use these shared value shapes from Task 2 onward:

```python
@dataclass(frozen=True)
class CommunicationResolution:
    state: Literal[
        "unknown", "known_unverified", "known_ineligible", "ambiguous_scope",
        "eligible_owner", "eligible_admin", "eligible_farmer", "eligible_field_worker",
    ]
    person_id: str | None
    portal_id: str | None
    endpoint_id: str | None
    allocation_ids: tuple[str, ...]
    locale: str | None

@dataclass(frozen=True)
class InteractionRun:
    id: str
    profile_id: str
    endpoint_id: str
    allocation_id: str | None
    workflow_version_id: str | None
    campaign_snapshot_id: str | None
    context_token: str
    expected_intents: tuple[str, ...]
    status: Literal["ready", "dispatching", "dispatched", "responded", "expired", "cancelled"]

@dataclass(frozen=True)
class CommandProposal:
    id: str
    portal_id: str
    actor_person_id: str
    operation: str
    arguments: dict[str, object]
    risk_class: Literal["routine", "material", "high"]
    confirmation_token: str
    expires_at: str
    status: Literal["awaiting_confirmation", "approved", "executed", "expired", "rejected"]
```

### Task 1: Prove and freeze the LoopMessage WhatsApp contract

**Files:**

- Create: `docs/ffl/LOOPMESSAGE-WHATSAPP-CONTRACT.md`
- Modify: `ffl/communications/ports.py`
- Modify: `ffl/communications/loopmessage.py`
- Modify: `ffl/communications/fake.py`
- Test: `tests/ffl/test_loopmessage_whatsapp_contract.py`

**Interfaces:**

- Consumes: current `LoopMessageProvider`, existing readiness gates, a named non-production LoopMessage sandbox account.
- Produces: `TemplateSend`, `NormalizedInboundEvent`, and documented `LoopMessageProvider.send_template()` behavior used by Tasks 6 and 7.

- [ ] **Step 1: Write the failing contract tests**

```python
def test_template_send_preserves_provider_template_and_parameters():
    provider = FakeLoopMessageProvider()
    result = provider.send_template(
        contact="+15550000001", sender="fake-whatsapp-sender",
        template_id="weekly-checkin-hi-v1", locale="hi-IN",
        parameters={"farm": "North Block"}, passthrough="run-1",
    )
    assert result.provider_message_id == "fake-message-1"
    assert provider.sent[0]["template_id"] == "weekly-checkin-hi-v1"
    assert provider.sent[0]["parameters"] == {"farm": "North Block"}

def test_normalized_reply_exposes_reply_to_and_opt_out_without_raw_address():
    event = FakeLoopMessageProvider().normalize_webhook({
        "event": "message_inbound", "webhook_id": "evt-1", "message_id": "msg-2",
        "contact": "+15550000001", "sender": "fake-whatsapp-sender",
        "text": "STOP", "reply_to_message_id": "outbound-1",
    })
    assert event["reply_to_message_id"] == "outbound-1"
    assert event["intent"] == "opt_out"
```

- [ ] **Step 2: Run the contract tests and verify they fail**

Run: `pytest tests/ffl/test_loopmessage_whatsapp_contract.py -v`

Expected: FAIL because `send_template` and normalized reply correlation do not exist.

- [ ] **Step 3: Record the sandbox proof and implement the narrow port**

Add immutable, non-secret evidence to `LOOPMESSAGE-WHATSAPP-CONTRACT.md`:

```markdown
| Capability | Sandbox result | Required adapter field |
|---|---|---|
| Template send | observed provider message ID | template ID, locale, parameter map, passthrough |
| Inbound reply | observed parent message/correlation field | reply_to_message_id |
| Delivery callback | observed status and sender field | provider message ID, status, sender |
| Media | observed media reference retrieval flow | opaque attachment reference |
| Opt-out | observed event/text behavior | opt_out intent |
```

Add the following protocol method and data shape without guessing undocumented
JSON keys; `LoopMessageProvider` maps them only after the sandbox response is
captured:

```python
class CommunicationsProvider(Protocol):
    def send_template(
        self, contact: str, sender: str, template_id: str, locale: str,
        parameters: dict[str, str], passthrough: str,
    ) -> SendResult: ...
```

Normalize `reply_to_message_id`, constrained `intent`, and protected attachment
references while retaining the complete raw payload only in the sealed receipt.

- [ ] **Step 4: Run focused provider and legacy communications tests**

Run: `pytest tests/ffl/test_loopmessage_whatsapp_contract.py tests/ffl/test_communications.py -v`

Expected: PASS. Existing `build_send_payload` tests remain valid until Task 6
switches the dispatcher to templates.

- [ ] **Step 5: Commit the contract boundary**

```bash
git add docs/ffl/LOOPMESSAGE-WHATSAPP-CONTRACT.md ffl/communications/ports.py \
  ffl/communications/loopmessage.py ffl/communications/fake.py \
  tests/ffl/test_loopmessage_whatsapp_contract.py
git commit -m "feat: prove LoopMessage WhatsApp contract"
```

### Task 2: Add private communications profile, endpoint verification, and scoped consent records

**Files:**

- Create: `db/postgres/0021_agro_communications_control_plane.sql`
- Modify: `ffl/communications/persistence.py`
- Modify: `ffl/persistence/schema.py`
- Test: `tests/ffl/test_communications_profiles.py`
- Modify: `db/postgres/README.md`

**Interfaces:**

- Consumes: canonical `people`, `customer_portals`, `portal_memberships`, and `person_operating_relationships` records.
- Produces: `create_communication_profile`, `verify_endpoint`, `set_scoped_consent`, and `profile_for_endpoint`; used by Tasks 3–10.

- [ ] **Step 1: Write failing private-schema and SQLite parity tests**

```python
def test_verified_endpoint_is_tenant_scoped_and_consent_is_scope_specific(ffl_db, seeded_portal):
    profile = create_communication_profile(ffl_db, seeded_portal.id, "farmer-1", "hi-IN", "Asia/Kolkata")
    endpoint = verify_endpoint(
        ffl_db, profile["id"], "loopmessage", "+919876543210", "portal_invitation", "admin-1",
    )
    set_scoped_consent(
        ffl_db, profile["id"], endpoint["id"], "weekly_farmer_checkin",
        "crop_allocation", "allocation-1", True, "signed consent", "admin-1",
    )
    assert profile_for_endpoint(ffl_db, "loopmessage", "+919876543210", seeded_portal.id)["id"] == profile["id"]
    assert has_scoped_consent(
        ffl_db, endpoint["id"], "weekly_farmer_checkin", "crop_allocation", "allocation-1"
    )
    assert not has_scoped_consent(
        ffl_db, endpoint["id"], "weekly_farmer_checkin", "crop_allocation", "allocation-2"
    )
```

- [ ] **Step 2: Run profile tests and verify they fail**

Run: `pytest tests/ffl/test_communications_profiles.py -v`

Expected: FAIL with missing profile and scoped-consent functions/tables.

- [ ] **Step 3: Add the production migration and SQLite equivalent**

Create private tables with foreign keys and indexes for:

```sql
agro_communication_profiles (
  id, portal_id, person_id, status, locale, time_zone, created_at,
  UNIQUE (portal_id, person_id)
)
agro_communication_endpoint_verifications (
  id, profile_id, endpoint_id, verification_method, verified_by_person_id,
  verified_at, status, revoked_at
)
agro_communication_endpoint_scopes (
  id, profile_id, relationship_id, scope_type, scope_id, starts_on, ends_on, status
)
agro_communication_scoped_consents (
  id, profile_id, endpoint_id, purpose, scope_type, scope_id, channel,
  status, evidence, granted_at, revoked_at
)
```

Use checks for `active|revoked|disabled` statuses, one active endpoint
verification per endpoint/profile, and `UNIQUE(endpoint_id, purpose, scope_type,
scope_id, channel)`. Add the same private tables/indexes to
`create_communications_schema`; no browser grants.

- [ ] **Step 4: Implement validation and append-only consent events**

`verify_endpoint` must require an existing profile and matching endpoint person.
`set_scoped_consent` must reject unknown purpose/scope values, append an event,
and preserve original capture evidence. A revoked consent is represented by a
new event/state transition, never removal. Keep old endpoint-level consent
functions intact for existing work prompts until Task 6 migrates them.

- [ ] **Step 5: Run schema/profile regression tests**

Run: `pytest tests/ffl/test_communications_profiles.py tests/ffl/test_communications.py -v`

Expected: PASS. Existing communication endpoint redaction tests remain green.

- [ ] **Step 6: Commit the profile foundation**

```bash
git add db/postgres/0021_agro_communications_control_plane.sql db/postgres/README.md \
  ffl/communications/persistence.py ffl/persistence/schema.py \
  tests/ffl/test_communications_profiles.py
git commit -m "feat: add scoped communications profiles"
```

### Task 3: Resolve communications identity against portal role and allocation coverage

**Files:**

- Create: `ffl/communications/identity.py`
- Create: `ffl/communications/policy.py`
- Test: `tests/ffl/test_communications_identity.py`
- Modify: `ffl/services/allocation_relationship_coverage.py`

**Interfaces:**

- Consumes: Task 2 profile/endpoint/scoped-consent records and `active_person_allocation_coverage`.
- Produces: `resolve_communication_endpoint(conn, provider, address, portal_id, allocation_id=None, received_at=None) -> CommunicationResolution` and `may_dispatch(...) -> PolicyDecision`.

- [ ] **Step 1: Write failing resolution matrix tests**

```python
def test_resolution_requires_verified_endpoint_active_membership_and_scope(conn, portal):
    assert resolve_communication_endpoint(conn, "loopmessage", "+919876543210", portal.id).state == "known_unverified"
    verify_test_endpoint(conn, portal.id, "farmer-1", "+919876543210")
    assert resolve_communication_endpoint(conn, "loopmessage", "+919876543210", portal.id).state == "eligible_farmer"
    suspend_membership(conn, portal.id, "farmer-1")
    assert resolve_communication_endpoint(conn, "loopmessage", "+919876543210", portal.id).state == "known_ineligible"

def test_field_context_requires_current_allocation_coverage(conn, portal):
    resolution = resolve_communication_endpoint(
        conn, "loopmessage", "+919876543210", portal.id, allocation_id="allocation-outside-scope"
    )
    assert resolution.state == "ambiguous_scope"
```

- [ ] **Step 2: Run identity tests and verify they fail**

Run: `pytest tests/ffl/test_communications_identity.py -v`

Expected: FAIL because no communications resolution/policy module exists.

- [ ] **Step 3: Implement narrow, non-inferential resolution**

Implement `CommunicationResolution` exactly as declared in this plan. Query only
one verified profile/endpoint inside the supplied portal; check active portal
membership and map portal role to `eligible_*`. For allocation context, call
`active_person_allocation_coverage` at the event date. Return
`ambiguous_scope` for zero or multiple permitted allocation choices unless an
exact interaction supplies the allocation. Do not query TrackWick or compare
names.

Implement `PolicyDecision(allowed: bool, code: str)` and `may_dispatch` with
these explicit denials: `endpoint_not_verified`, `membership_inactive`,
`profile_inactive`, `scope_not_covered`, `consent_not_active`,
`quiet_hours`, and `frequency_cap`.

- [ ] **Step 4: Run identity, coverage, and portal regressions**

Run: `pytest tests/ffl/test_communications_identity.py tests/ffl/test_allocation_relationship_coverage.py tests/ffl/test_customer_portal.py -v`

Expected: PASS.

- [ ] **Step 5: Commit policy resolution**

```bash
git add ffl/communications/identity.py ffl/communications/policy.py \
  ffl/services/allocation_relationship_coverage.py tests/ffl/test_communications_identity.py
git commit -m "feat: resolve WhatsApp profiles by role and scope"
```

### Task 4: Replace open-prompt matching with immutable interaction runs

**Files:**

- Create: `ffl/communications/interactions.py`
- Modify: `ffl/communications/persistence.py`
- Modify: `ffl/communications/service.py`
- Modify: `db/postgres/0021_agro_communications_control_plane.sql`
- Modify: `ffl/persistence/schema.py`
- Test: `tests/ffl/test_communications_interactions.py`

**Interfaces:**

- Consumes: Tasks 1–3; a dispatched provider message ID or signed opaque context token.
- Produces: `create_interaction_run`, `record_interaction_dispatch`, `find_interaction_for_inbound`, and `route_inbound_interaction` for Task 7.

- [ ] **Step 1: Write the failure case that the current code cannot handle**

```python
def test_reply_to_message_resolves_exact_run_when_recipient_has_two_open_requests(conn):
    first = create_ready_run(conn, endpoint_id="endpoint-1", allocation_id="allocation-a")
    second = create_ready_run(conn, endpoint_id="endpoint-1", allocation_id="allocation-b")
    record_interaction_dispatch(conn, first.id, "provider-first")
    record_interaction_dispatch(conn, second.id, "provider-second")
    assert find_interaction_for_inbound(
        conn, "loopmessage", "endpoint-1", "provider-second", None
    ).id == second.id

def test_unmatched_reply_never_selects_the_latest_open_run(conn):
    create_ready_run(conn, endpoint_id="endpoint-1", allocation_id="allocation-a")
    assert find_interaction_for_inbound(conn, "loopmessage", "endpoint-1", None, "unknown-token") is None
```

- [ ] **Step 2: Run interaction tests and verify they fail**

Run: `pytest tests/ffl/test_communications_interactions.py -v`

Expected: FAIL because interaction runs and exact matching do not exist.

- [ ] **Step 3: Add interaction-run persistence and correlation rules**

Add `communication_interaction_runs` and `communication_interaction_dispatches`
to both schemas. Store profile, endpoint, optional allocation/work/field request,
workflow/campaign source, random opaque context-token hash, expected intents,
status, created/expiry timestamps, and provider message ID. Do not store a raw
token; issue it only in the outbound `passthrough` context and compare its
hash.

Update inbound processing to first resolve `reply_to_message_id`, then a valid
context token. Remove `single_open_prompt` from new routing. Retain the legacy
prompt code only as a compatibility adapter that creates one interaction run.

- [ ] **Step 4: Run new and legacy inbound tests**

Run: `pytest tests/ffl/test_communications_interactions.py tests/ffl/test_communications.py -v`

Expected: PASS; update the legacy ambiguous-prompt test so an unmatched reply
is visibly unresolved rather than becoming a guessed signal.

- [ ] **Step 5: Commit exact correlation**

```bash
git add ffl/communications/interactions.py ffl/communications/persistence.py \
  ffl/communications/service.py db/postgres/0021_agro_communications_control_plane.sql \
  ffl/persistence/schema.py tests/ffl/test_communications_interactions.py \
  tests/ffl/test_communications.py
git commit -m "feat: correlate WhatsApp replies to interaction runs"
```

### Task 5: Add versioned workflow definitions and the weekly farmer check-in

**Files:**

- Create: `ffl/communications/workflows.py`
- Modify: `ffl/communications/persistence.py`
- Modify: `db/postgres/0021_agro_communications_control_plane.sql`
- Modify: `ffl/persistence/schema.py`
- Test: `tests/ffl/test_communications_workflows.py`

**Interfaces:**

- Consumes: profile/policy resolution from Task 3 and interaction persistence from Task 4.
- Produces: `publish_workflow_version`, `eligible_workflow_targets`, and `create_workflow_runs` used by the scheduler in Task 8.

- [ ] **Step 1: Write the weekly-check-in eligibility test**

```python
def test_weekly_farmer_workflow_creates_one_run_per_eligible_allocation(conn, clock):
    version = publish_weekly_farmer_workflow(conn, owner_id="admin-1")
    runs = create_workflow_runs(conn, version.id, due_at="2026-08-10T04:00:00+00:00", now=clock.now())
    assert [(run.profile_id, run.allocation_id) for run in runs] == [
        ("farmer-profile", "allocation-a"), ("farmer-profile", "allocation-b")
    ]

def test_workflow_skips_revoked_or_out_of_quiet_hours_targets(conn, clock):
    runs = create_workflow_runs(conn, "weekly-v1", due_at="2026-08-10T04:00:00+00:00", now=clock.now())
    assert "revoked-profile" not in {run.profile_id for run in runs}
```

- [ ] **Step 2: Run workflow tests and verify they fail**

Run: `pytest tests/ffl/test_communications_workflows.py -v`

Expected: FAIL with no workflow definition or run creation function.

- [ ] **Step 3: Implement immutable workflow versions and safe targeting**

Persist workflow definitions/versions with purpose, owner, `draft|published|paused`
state, trigger JSON, audience rule JSON, template ID, expected intents,
response deadline, quiet-hours/frequency policy, and escalation owner. Validate
the first supported `weekly_farmer_checkin` definition exactly: active farmer
profile, active allocation coverage, scoped consent purpose, template locale,
and one interaction per `profile × allocation × workflow version × weekly
window`.

Do not create a generic query language in this task. Store a typed audience
descriptor such as `{"portal_id": "...", "portal_role": "farmer", "active_allocation": true}`
and reject unknown keys.

- [ ] **Step 4: Run workflow and eligibility regression tests**

Run: `pytest tests/ffl/test_communications_workflows.py tests/ffl/test_communications_identity.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the workflow model**

```bash
git add ffl/communications/workflows.py ffl/communications/persistence.py \
  db/postgres/0021_agro_communications_control_plane.sql ffl/persistence/schema.py \
  tests/ffl/test_communications_workflows.py
git commit -m "feat: add versioned farmer communication workflows"
```

### Task 6: Dispatch approved templates through the policy-controlled outbox

**Files:**

- Create: `ffl/communications/outbox.py`
- Modify: `ffl/communications/service.py`
- Modify: `ffl/communications/persistence.py`
- Modify: `ffl/communications/worker.py`
- Test: `tests/ffl/test_communications_outbox.py`

**Interfaces:**

- Consumes: Task 1 provider template send, Task 3 `may_dispatch`, Task 4 runs, Task 5 published workflow version.
- Produces: `dispatch_ready_interaction(conn, provider, run_id, now)` and `dispatch_due_workflows(conn, provider, now)`.

- [ ] **Step 1: Write failing dispatch and suppression tests**

```python
def test_dispatch_uses_approved_template_and_records_provider_message_id(conn, provider, clock):
    run = create_ready_run_with_template(conn, template_id="weekly-hi-v1")
    result = dispatch_ready_interaction(conn, provider, run.id, clock.now())
    assert result.status == "dispatched"
    assert provider.sent[0]["template_id"] == "weekly-hi-v1"
    assert interaction_dispatches(conn, run.id)[0]["provider_message_id"] == "fake-message-1"

def test_dispatch_refuses_revoked_consent_without_calling_provider(conn, provider, clock):
    run = create_ready_run_with_revoked_consent(conn)
    assert dispatch_ready_interaction(conn, provider, run.id, clock.now()).status == "suppressed"
    assert provider.sent == []
```

- [ ] **Step 2: Run outbox tests and verify they fail**

Run: `pytest tests/ffl/test_communications_outbox.py -v`

Expected: FAIL because no outbox dispatcher exists.

- [ ] **Step 3: Implement idempotent interaction dispatch**

Create a durable outbox row before the provider call. Recheck Task 3 policy and
template approval/locale/parameters immediately before sending. Call
`provider.send_template`; write provider message ID and dispatch status in the
same logical run without ever issuing a second provider call for the same
interaction. Preserve existing ambiguous-send reconciliation behavior by
marking the outbox `unknown` and reconciling by provider message ID or context
token, never re-sending blindly.

Make `send_work_prompt` a thin compatibility wrapper that creates a work
interaction and dispatches through this outbox.

- [ ] **Step 4: Run outbox, worker, and legacy prompt tests**

Run: `pytest tests/ffl/test_communications_outbox.py tests/ffl/test_communications.py -v`

Expected: PASS; legacy work prompt remains idempotent.

- [ ] **Step 5: Commit policy-controlled dispatch**

```bash
git add ffl/communications/outbox.py ffl/communications/service.py \
  ffl/communications/persistence.py ffl/communications/worker.py \
  tests/ffl/test_communications_outbox.py tests/ffl/test_communications.py
git commit -m "feat: dispatch WhatsApp interaction templates"
```

### Task 7: Route inbound field replies, evidence, and opt-outs through exact interactions

**Files:**

- Create: `ffl/communications/inbound.py`
- Modify: `ffl/communications/service.py`
- Modify: `ffl/communications/persistence.py`
- Modify: `ffl/communications/worker.py`
- Test: `tests/ffl/test_communications_inbound.py`

**Interfaces:**

- Consumes: Tasks 1–6 and existing evidence/exception/signal candidate services.
- Produces: `process_inbound_event(conn, provider, event, stored_event) -> InboundOutcome` used by the private worker.

- [ ] **Step 1: Write failing routing safety tests**

```python
def test_known_farmer_photo_reply_creates_review_candidate_for_exact_allocation(conn, provider):
    run = dispatched_farmer_photo_run(conn, allocation_id="allocation-a")
    outcome = process_test_reply(provider, reply_to_message_id=run.provider_message_id, attachments=["media-1"])
    assert outcome.kind == "review_candidate"
    assert candidate_for_event(conn, outcome.event_id)["allocation_id"] == "allocation-a"

def test_stop_revokes_scoped_consent_and_future_dispatch_is_suppressed(conn, provider):
    run = dispatched_farmer_checkin(conn)
    process_test_reply(provider, reply_to_message_id=run.provider_message_id, text="STOP")
    assert not has_scoped_consent(conn, run.endpoint_id, "weekly_farmer_checkin", "crop_allocation", run.allocation_id)

def test_unknown_or_unmatched_reply_creates_redacted_review_case_not_candidate(conn, provider):
    outcome = process_test_reply(provider, contact="+919999999999", text="my crop is sick")
    assert outcome.kind == "identity_review"
    assert candidate_for_event(conn, outcome.event_id) is None
```

- [ ] **Step 2: Run inbound tests and verify they fail**

Run: `pytest tests/ffl/test_communications_inbound.py -v`

Expected: FAIL because the current service maps all non-deviation text to a signal candidate.

- [ ] **Step 3: Implement constrained intent routing**

Implement only these initial intents: `confirm`, `decline`, `report_deviation`,
`submit_evidence`, `request_callback`, `help`, and `opt_out`. Use exact
interaction correlation before any allocation route. `opt_out` revokes the
interaction purpose/scope and marks affected future runs suppressed. Media is
added as protected attachments and becomes acceptable evidence only after the
existing private retention process succeeds.

Create explicit review states for `identity_review` and `context_review`; do
not coerce them into signal/exception candidates. Preserve the current
canonical acceptance methods for valid signal/exception candidates.

- [ ] **Step 4: Run all communications tests**

Run: `pytest tests/ffl/test_communications.py tests/ffl/test_communications_inbound.py tests/ffl/test_communications_interactions.py -v`

Expected: PASS.

- [ ] **Step 5: Commit safe inbound routing**

```bash
git add ffl/communications/inbound.py ffl/communications/service.py \
  ffl/communications/persistence.py ffl/communications/worker.py \
  tests/ffl/test_communications_inbound.py
git commit -m "feat: route WhatsApp replies by interaction context"
```

### Task 8: Schedule workflow runs and escalate failed/no-response interactions

**Files:**

- Create: `ffl/communications/scheduler.py`
- Create: `ffl/communications/escalations.py`
- Modify: `ffl/communications/worker.py`
- Modify: `ffl/communications/persistence.py`
- Modify: `db/postgres/0021_agro_communications_control_plane.sql`
- Modify: `ffl/persistence/schema.py`
- Test: `tests/ffl/test_communications_scheduler.py`

**Interfaces:**

- Consumes: published workflows and ready/dispatched interaction runs.
- Produces: `run_communications_schedule(conn, provider, now) -> ScheduleResult` and `open_escalation(...)`.

- [ ] **Step 1: Write deterministic schedule/escalation tests**

```python
def test_scheduler_creates_weekly_runs_once_and_dispatches_only_in_send_window(conn, provider):
    blocked = run_communications_schedule(conn, provider, "2026-08-10T00:00:00+00:00")
    assert blocked.dispatched == 0
    allowed = run_communications_schedule(conn, provider, "2026-08-10T05:00:00+00:00")
    assert allowed.created == 1 and allowed.dispatched == 1
    replay = run_communications_schedule(conn, provider, "2026-08-10T05:00:00+00:00")
    assert replay.created == 0 and replay.dispatched == 0

def test_expired_response_deadline_opens_named_fallback_escalation(conn, provider):
    run = dispatched_run_past_deadline(conn)
    result = run_communications_schedule(conn, provider, "2026-08-12T10:00:00+00:00")
    assert escalation_for_run(conn, run.id)["fallback_owner_id"] == "manager-2"
```

- [ ] **Step 2: Run scheduler tests and verify they fail**

Run: `pytest tests/ffl/test_communications_scheduler.py -v`

Expected: FAIL because the worker does not create workflow runs or meaningful escalations.

- [ ] **Step 3: Implement a bounded private schedule pass**

Use the existing one-minute Hetzner worker invocation. Each pass must:

1. create due workflow runs idempotently;
2. dispatch ready runs through Task 6;
3. reconcile unknown provider deliveries;
4. mark response deadlines as expired without changing work status;
5. create one open escalation per overdue/failed run with named owner/fallback;
6. return aggregate counts only to the alert webhook.

Do not introduce a public scheduler endpoint or sleep loop. Persist enough state
to make repeated worker executions safe.

- [ ] **Step 4: Run scheduler/worker regression tests**

Run: `pytest tests/ffl/test_communications_scheduler.py tests/ffl/test_communications.py tests/ffl/test_database_targets.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the schedule pass**

```bash
git add ffl/communications/scheduler.py ffl/communications/escalations.py \
  ffl/communications/worker.py ffl/communications/persistence.py \
  db/postgres/0021_agro_communications_control_plane.sql ffl/persistence/schema.py \
  tests/ffl/test_communications_scheduler.py
git commit -m "feat: schedule WhatsApp workflows and escalations"
```

### Task 9: Add audience snapshots and governed campaign execution

**Files:**

- Create: `ffl/communications/audience.py`
- Create: `ffl/communications/campaigns.py`
- Modify: `ffl/communications/policy.py`
- Modify: `ffl/communications/persistence.py`
- Modify: `db/postgres/0021_agro_communications_control_plane.sql`
- Modify: `ffl/persistence/schema.py`
- Test: `tests/ffl/test_communications_campaigns.py`

**Interfaces:**

- Consumes: profile/policy/workflow/outbox modules.
- Produces: `create_campaign_draft`, `freeze_campaign_audience`, `approve_campaign`, `launch_campaign`, `pause_campaign`, and `cancel_campaign` for Task 10/API use.

- [ ] **Step 1: Write failing campaign safety tests**

```python
def test_campaign_snapshot_excludes_revoked_and_uncovered_recipients(conn):
    campaign = create_campaign_draft(conn, "admin-1", "operational_checkin", "weekly-hi-v1", audience_rule())
    snapshot = freeze_campaign_audience(conn, campaign.id)
    assert snapshot.eligible_count == 2
    assert snapshot.exclusions == {"consent_not_active": 1, "scope_not_covered": 1}

def test_campaign_cannot_launch_without_required_owner_approval(conn, provider):
    campaign = high_impact_campaign(conn)
    assert launch_campaign(conn, provider, campaign.id).status == "blocked"
    approve_campaign(conn, campaign.id, "owner-1")
    assert launch_campaign(conn, provider, campaign.id).status == "launching"

def test_cancelled_campaign_never_sends_unsent_recipients(conn, provider):
    campaign = approved_campaign_with_three_targets(conn)
    pause_campaign(conn, campaign.id, "admin-1")
    assert launch_campaign(conn, provider, campaign.id).sent_count == 0
```

- [ ] **Step 2: Run campaign tests and verify they fail**

Run: `pytest tests/ffl/test_communications_campaigns.py -v`

Expected: FAIL because campaigns and audience snapshots do not exist.

- [ ] **Step 3: Implement typed audience snapshots and campaign policy**

Support the same typed audience descriptor as Task 5, not arbitrary SQL or a
free-form CRM query. Persist the frozen recipient/profile/allocation/context
snapshot, template/version, exclusions counts/reasons, initiator, approval
state, schedule, and `draft|approved|launching|paused|cancelled|completed`
state. Recheck current consent/profile/scope before each Task 6 dispatch.

Implement threshold policy as portal configuration with conservative seeded
defaults: routine campaigns require initiator confirmation; high-impact
campaigns require one active owner approval. Do not implement promotional use
in this task; only purpose-specific operational campaigns are eligible.

- [ ] **Step 4: Run campaign and outbox tests**

Run: `pytest tests/ffl/test_communications_campaigns.py tests/ffl/test_communications_outbox.py -v`

Expected: PASS.

- [ ] **Step 5: Commit campaign execution**

```bash
git add ffl/communications/audience.py ffl/communications/campaigns.py \
  ffl/communications/policy.py ffl/communications/persistence.py \
  db/postgres/0021_agro_communications_control_plane.sql ffl/persistence/schema.py \
  tests/ffl/test_communications_campaigns.py
git commit -m "feat: add governed WhatsApp campaigns"
```

### Task 10: Build owner/admin typed command proposals and WhatsApp confirmation

**Files:**

- Create: `ffl/communications/commands.py`
- Modify: `ffl/communications/inbound.py`
- Modify: `ffl/communications/persistence.py`
- Modify: `ffl/communications/policy.py`
- Modify: `db/postgres/0021_agro_communications_control_plane.sql`
- Modify: `ffl/persistence/schema.py`
- Test: `tests/ffl/test_communications_commands.py`

**Interfaces:**

- Consumes: `CommunicationResolution`, campaign/workflow services, and canonical operations services.
- Produces: `propose_command`, `confirm_command`, and `execute_command` with the `CommandProposal` shape declared above.

- [ ] **Step 1: Write failing command tests with no LLM dependency**

```python
def test_admin_command_creates_expiring_typed_campaign_proposal(conn, clock):
    proposal = propose_command(
        conn, actor="admin-1", portal_id="fortune", intent="campaign.create",
        arguments={"purpose": "weekly_farmer_checkin", "template_id": "weekly-hi-v1", "audience": farmer_rule()},
        now=clock.now(),
    )
    assert proposal.risk_class == "material"
    assert proposal.status == "awaiting_confirmation"
    assert confirm_command(conn, proposal.id, proposal.confirmation_token, "admin-1", clock.now()).status == "approved"

def test_farmer_cannot_execute_admin_command_and_stale_proposal_cannot_run(conn, clock):
    with pytest.raises(CommandDenied, match="portal_role_not_permitted"):
        propose_command(conn, actor="farmer-1", portal_id="fortune", intent="campaign.create", arguments={}, now=clock.now())
    assert execute_command(conn, expired_proposal(conn), clock.now()).status == "expired"
```

- [ ] **Step 2: Run command tests and verify they fail**

Run: `pytest tests/ffl/test_communications_commands.py -v`

Expected: FAIL because commands/proposals do not exist.

- [ ] **Step 3: Implement an allow-listed command executor**

Implement these initial intents only:

```text
operating.summary.read
work.assign
exception.assign_callback
workflow.pause
workflow.resume
campaign.create
campaign.pause
campaign.cancel
```

Each intent has a Pydantic argument model and an executor that calls existing
canonical services or Task 9 campaign/workflow functions. Persist proposal
arguments, expected record versions, rendered preview, risk class, token hash,
expiry, confirmation actor/time, policy decision, and execution result. A
natural-language/voice interpreter, if added, must only map input to one of
these typed intents; it cannot call the executor directly.

Treat `CONFIRM <token>` only as a confirmation of a matching, unexpired,
same-actor proposal. Re-evaluate role/scope/record versions before execution.

- [ ] **Step 4: Connect verified admin inbound messages to proposal routing**

In `inbound.py`, route only `eligible_owner`/`eligible_admin` command intent
to `propose_command` or `confirm_command`. Route a field-facing endpoint with
the same text as ordinary help/review content; never elevate from wording.

- [ ] **Step 5: Run command and inbound authorization tests**

Run: `pytest tests/ffl/test_communications_commands.py tests/ffl/test_communications_inbound.py -v`

Expected: PASS.

- [ ] **Step 6: Commit the command plane**

```bash
git add ffl/communications/commands.py ffl/communications/inbound.py \
  ffl/communications/persistence.py ffl/communications/policy.py \
  db/postgres/0021_agro_communications_control_plane.sql ffl/persistence/schema.py \
  tests/ffl/test_communications_commands.py
git commit -m "feat: add confirmed WhatsApp admin commands"
```

### Task 11: Expose manager-only communications APIs and redacted operations views

**Files:**

- Create: `ffl/api/communications_control_routes.py`
- Modify: `ffl/app.py`
- Modify: `ffl/api/routes.py`
- Test: `tests/ffl/test_communications_control_routes.py`

**Interfaces:**

- Consumes: all prior services; existing `require_manager` and portal session authority.
- Produces: manager-only HTTP projections for profiles, workflows, campaigns, commands, inbox, and health; all browser writes use these routes rather than raw tables.

- [ ] **Step 1: Write failing authorization/redaction tests**

```python
def test_farmer_cannot_list_communications_campaigns_or_profiles(client):
    assert client.get("/api/v1/communications-control/campaigns").status_code == 403

def test_manager_campaign_preview_is_redacted_and_has_no_phone_or_raw_payload(client):
    response = client.get("/api/v1/communications-control/campaigns/campaign-1")
    assert response.status_code == 200
    assert response.json()["audience"]["eligible_count"] == 2
    assert "address" not in response.text
    assert "ciphertext" not in response.text

def test_admin_can_pause_campaign_but_cannot_create_raw_provider_send(client):
    assert client.post("/api/v1/communications-control/campaigns/campaign-1/pause").status_code == 200
    assert client.post("/api/v1/communications-control/provider/send", json={}).status_code == 404
```

- [ ] **Step 2: Run API tests and verify they fail**

Run: `pytest tests/ffl/test_communications_control_routes.py -v`

Expected: FAIL because the control router is absent.

- [ ] **Step 3: Implement explicit, manager-only request/response models**

Add routes for profile status, consent grant/revoke, workflow draft/publish/pause,
campaign draft/preview/approve/pause/cancel, command-proposal read, and the
redacted review inbox. Require `require_manager` on every route. Return
endpoint last-four, aggregate exclusions, record IDs, policy codes, timestamps,
and evidence metadata only. Do not add an endpoint that sends arbitrary text,
returns raw provider event data, or allows a browser to set worker attestation.

Mount the router in `ffl/app.py`; leave the provider webhook on its dedicated
authorization path.

- [ ] **Step 4: Run control-route and existing session tests**

Run: `pytest tests/ffl/test_communications_control_routes.py tests/ffl/test_manager_session.py tests/ffl/test_password_identities.py -v`

Expected: PASS.

- [ ] **Step 5: Commit the control API**

```bash
git add ffl/api/communications_control_routes.py ffl/api/routes.py ffl/app.py \
  tests/ffl/test_communications_control_routes.py
git commit -m "feat: expose governed communications control APIs"
```

### Task 12: Build the manager Communications surface without a chat archive

**Files:**

- Modify: `apps/web/components/command-centre.tsx`
- Modify: `apps/web/app/globals.css`
- Modify: `apps/web/app/settings/page.tsx`
- Create: `apps/web/components/communications-control.tsx`
- Test: `apps/web/components/communications-control.test.tsx`
- Create: `apps/web/vitest.config.ts`
- Create: `apps/web/test/setup.ts`
- Modify: `apps/web/package.json`

**Interfaces:**

- Consumes: Task 11 redacted APIs only.
- Produces: an authenticated manager UI for readiness, review cases, workflows, campaign previews, and campaign pause/cancel.

- [ ] **Step 1: Add the focused web test harness**

Run:

```bash
cd apps/web
pnpm add -D vitest @testing-library/react @testing-library/jest-dom jsdom
```

Create `vitest.config.ts` with `environment: "jsdom"` and
`setupFiles: ["./test/setup.ts"]`; create `test/setup.ts` with
`import "@testing-library/jest-dom/vitest"`; add a `test` script that runs
`vitest run`; and confirm `pnpm test --help` succeeds. This is test
infrastructure only; do not create the product component in this step.

- [ ] **Step 2: Write a failing component test for privacy-safe rendering**

```tsx
it("shows a campaign audience summary without recipient addresses or message history", async () => {
  render(<CommunicationsControl api={fakeApi} />);
  expect(await screen.findByText("84 eligible recipients")).toBeVisible();
  expect(screen.queryByText("+919876543210")).not.toBeInTheDocument();
  expect(screen.queryByText("Conversation history")).not.toBeInTheDocument();
});
```

- [ ] **Step 3: Run the component test and verify it fails**

Run: `cd apps/web && pnpm test components/communications-control.test.tsx`

Expected: FAIL because the component is absent.

- [ ] **Step 4: Add the focused manager surface**

Create a tab/panel with four sections: **Needs review**, **Workflows**,
**Campaigns**, and **Health**. Use the same visual language as the current
command centre. Show redacted identity/scope state, candidate/evidence
availability, audience counts/exclusions, required approval, send state,
pause/cancel controls, and readiness gaps. Keep existing Settings’ disabled
WhatsApp row until Task 13 records controlled-pilot approval.

Do not render searchable conversations, raw payloads, phone numbers, source
contacts, or direct arbitrary-message composer.

- [ ] **Step 5: Run web type and component tests**

Run: `cd apps/web && pnpm typecheck && pnpm test components/communications-control.test.tsx`

Expected: PASS. The project has no lint script today, so do not claim a lint
check exists; TypeScript and component tests are the web verification gate.

- [ ] **Step 6: Commit the manager surface**

```bash
git add apps/web/components/communications-control.tsx \
  apps/web/components/communications-control.test.tsx apps/web/components/command-centre.tsx \
  apps/web/app/globals.css apps/web/app/settings/page.tsx apps/web/package.json apps/web/pnpm-lock.yaml \
  apps/web/vitest.config.ts apps/web/test/setup.ts
git commit -m "feat: add manager communications control surface"
```

### Task 13: Record readiness, deploy privately, and execute a controlled pilot

**Files:**

- Modify: `docs/ffl/LOOPMESSAGE-RUNBOOK.md`
- Modify: `docs/ffl/WHATSAPP-READINESS.md`
- Create: `docs/ffl/WHATSAPP-CONTROL-PLANE-ROLLOUT.md`
- Modify: `deploy/hetzner/ffl-communications-worker.service`
- Modify: `deploy/hetzner/ffl-communications-worker.timer`
- Modify: `tests/ffl/test_communications_readiness.py`

**Interfaces:**

- Consumes: complete software from Tasks 1–12 and the existing private worker/readiness endpoint.
- Produces: a deployment-owned approval record and a measured pilot that can be halted without data loss.

- [ ] **Step 1: Write readiness tests for the new live gates**

```python
def test_readiness_is_blocked_without_provider_contract_and_control_plane_migration():
    report = whatsapp_readiness(config(provider_contract_verified=False, control_plane_schema_ready=False))
    assert report["live_outbound_eligible"] is False
    assert "provider_contract_not_verified" in report["gaps"]
    assert "control_plane_schema_not_ready" in report["gaps"]
```

- [ ] **Step 2: Run readiness tests and verify they fail**

Run: `pytest tests/ffl/test_communications_readiness.py -v`

Expected: FAIL because the new readiness gates are absent.

- [ ] **Step 3: Add the deployment checklist and fail-closed gates**

The rollout document must require, in order:

1. reviewed PostgreSQL migration in the confirmed FFL project;
2. LoopMessage sandbox proof from Task 1 and dedicated sender binding;
3. verified worker service/timer and encrypted receipt/media directories;
4. named pilot owner, fallback owner, Hindi/English copy approval, retention
   approval, and rollback contact;
5. five-to-ten consented workers only; no farmer workflow/campaign until the
   worker pilot acceptance criteria pass;
6. daily aggregate review of delivery, suppression, unknown identity, media,
   candidate, no-response, and escalation outcomes;
7. immediate pause/cancel procedure that prevents future sends without
   deleting receipts/evidence/audit records.

Add readiness booleans for the provider contract and control-plane migration;
only the trusted deployment composition may set them. Update the worker unit
only if new schedule environment values are required; never insert secrets
into the unit file.

- [ ] **Step 4: Run readiness and worker tests**

Run: `pytest tests/ffl/test_communications_readiness.py tests/ffl/test_communications_readiness_route.py tests/ffl/test_database_targets.py -v`

Expected: PASS.

- [ ] **Step 5: Commit deployment and rollout controls**

```bash
git add docs/ffl/LOOPMESSAGE-RUNBOOK.md docs/ffl/WHATSAPP-READINESS.md \
  docs/ffl/WHATSAPP-CONTROL-PLANE-ROLLOUT.md \
  deploy/hetzner/ffl-communications-worker.service \
  deploy/hetzner/ffl-communications-worker.timer \
  tests/ffl/test_communications_readiness.py
git commit -m "docs: gate WhatsApp control plane rollout"
```

## Final verification gate

- [ ] Run the full backend suite: `pytest tests/ffl -v`.
- [ ] Run the existing non-FFL suite: `pytest tests -v`.
- [ ] Run web verification: `cd apps/web && pnpm typecheck && pnpm test`.
- [ ] Confirm private PostgreSQL migration review has occurred before applying it; do not apply migrations from app startup.
- [ ] Run the provider sandbox script/checklist with a non-production consented test number and attach its non-secret proof reference to deployment configuration.
- [ ] Manually verify: unknown phone gets no contextual reply; revoked consent suppresses send; two concurrent prompts resolve only through an exact interaction; campaign pause prevents unsent recipients; admin confirmation cannot execute a stale proposal; a worker reply leaves work open until normal review.
- [ ] Review `git status --short` before final commit and preserve unrelated user changes.

## Spec coverage self-check

| PRD requirement | Plan task(s) |
|---|---|
| LoopMessage proof, sender binding, templates, media, callbacks | 1, 6, 13 |
| Endpoint/profile/portal/scope/consent identity model | 2, 3 |
| Exact reply correlation and immutable interaction context | 4, 7 |
| Weekly farmer workflow and field-worker evidence loop | 5, 6, 7, 8 |
| Owner/admin command authority with confirmation/audit | 10 |
| Campaign audience snapshots, consent, approvals, pause/cancel | 9, 10, 11, 12 |
| Private worker, readiness, escalation and pilot controls | 6, 8, 13 |
| Manager UI without raw conversation archive | 11, 12 |
| PWA fallback and no false work completion | 6, 7, 12, final gate |
