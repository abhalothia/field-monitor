# Task 7 — WhatsApp inbound communications control

## Scope delivered

- Added `ffl.communications.inbound.process_inbound_event`, returning a small `InboundOutcome` for the private worker path.
- Replaced the legacy "all non-deviation text is a signal" behavior in `service._process_event` with exact interaction routing.
- Added durable, redacted `identity_review` and `context_review` records plus idempotent routing outcomes.  These records carry no contact, raw text, attachment URL, allocation, or inferred identity.
- Updated the worker's redacted health result with identity/context review counts.
- Updated legacy communications tests to remove assertions that uncorrelated/free-text replies create candidates.

## Routing and safety design

- The router recognizes only the approved exact tokens: `confirm`, `decline`, `report_deviation`, `submit_evidence`, `request_callback`, `help`, and `opt_out` (`STOP` is the explicit opt-out spelling).  It does not classify prose.
- A candidate is created only after `find_interaction_for_inbound` proves the exact reply-to message or context-token digest against the dispatched run.  Known endpoint/contact history is not a fallback authority.
- Unknown endpoints produce `identity_review`; known endpoints with unmatched context, unrecognized text, or an unexpected intent produce `context_review`.  None creates a signal or exception candidate.
- Only exact `report_deviation` and `submit_evidence` enter the existing exception/signal candidate lane.  Exact confirm/decline/help/callback replies remain review-only and cannot invoke the canonical acceptance APIs.
- Attachments retain only one-way source references until the existing private retention worker successfully creates linked evidence.  Candidate acceptance remains gated by `evidence_is_linked_to_event`.
- Exact opt-outs revoke only the interaction's `purpose` + `crop_allocation` scoped consent and suppress/cancel matching ready outbox interactions.  Future dispatch also remains blocked by the outbox's consent re-check.
- No inbound path completes work, accepts evidence, produces a diagnosis, or sends advice.

## Tests and verification

- TDD red: `.venv/bin/python -m pytest tests/ffl/test_communications_inbound.py -v` initially failed at collection because the inbound router did not exist.
- Focused inbound suite: 4 passed.
- Required combined suite: `.venv/bin/python -m pytest tests/ffl/test_communications.py tests/ffl/test_communications_inbound.py tests/ffl/test_communications_interactions.py -v` — 33 passed (one upstream Starlette/httpx deprecation warning).
- Static verification: `.venv/bin/python -m compileall -q ffl/communications` and `git diff --check` passed.

## Commit

`feat: route WhatsApp replies by interaction context` (the Task 7 commit in this worktree).

## Concerns / follow-up

- Resolved in review round 1: additive private PostgreSQL migration `0027_agro_communication_inbound_reviews.sql` creates the inbound review/outcome tables, constraints, foreign-key indexes, and PUBLIC revokes.  Translation parity is covered, so the private Postgres adapter maps both new relations.

## Review round 1 fixes

- Added the reviewed additive Postgres migration after `0026`; no already-applied migration was changed.
- Moved the retained-evidence proof check before both canonical candidate acceptance branches.  An exception candidate with media now rejects until an attachment has been privately retained and linked to the same event.
- Re-read exact mutable dispatch policy and outbox state after the durable claim and immediately before `send_template`; a scoped opt-out that revokes/suppresses in that interval wins without a provider call.  Matching ready and dispatching runs are suppressed/cancelled by exact scope.
- Replaced SQLite-only `profile_id IS ?` with an explicit NULL/non-NULL predicate that translates safely to PostgreSQL.
- Removed raw inbound text from new candidate drafts and candidate API projection.  They retain only a constrained lowercase intent and fixed redacted summary; raw text remains in the sealed receipt flow.
- Candidate-replay recovery now returns and records the existing exact interaction-run identifier when available.

### Review-round verification

- Red verification before the implementation: the new exception-media and normal-record redaction assertions failed (acceptance was incorrectly allowed and candidate/API records exposed raw text).
- `.venv/bin/python -m pytest tests/ffl/test_communications.py tests/ffl/test_communications_inbound.py tests/ffl/test_communications_interactions.py tests/ffl/test_communications_outbox.py tests/ffl/test_database_targets.py -q` — 66 passed.
- `.venv/bin/python -m pytest tests/ffl/test_communications_inbound.py -v` — 4 passed.
- `.venv/bin/python -m compileall -q ffl/communications` and `git diff --check` passed.

### Review-round commit

`fix: harden WhatsApp inbound review routing` (scoped follow-up commit in this worktree).

## Review round 2 — durable final-send gate

- Added additive private migration `0028_agro_communication_final_send_gate.sql` and SQLite schema parity for nullable `final_send_reserved_at` on the outbox.
- The sender atomically claims this marker after all policy checks and immediately before the one provider call.  This is the final send gate; it commits before provider I/O, so no provider call occurs inside an unbounded transaction.
- Exact opt-out suppression uses the reciprocal conditional update: it can transition only pending/dispatching entries with no final-send reservation.  If it wins first, the final gate fails and sends nothing.  If the final gate wins first, opt-out still revokes consent but cannot mark/cancel that already reserved provider attempt as suppressed.
- The outbox reconciliation path continues treating a crashed, reserved dispatch as unknown rather than attempting a second provider call.

### Review-round 2 verification

- TDD red: the new pre-gate regression initially failed because `claim_outbox_final_send` did not exist; the post-gate case also showed the older suppression path cancelled a run after provider entry.
- `.venv/bin/python -m pytest tests/ffl/test_communications_outbox.py tests/ffl/test_communications.py tests/ffl/test_communications_inbound.py tests/ffl/test_communications_interactions.py tests/ffl/test_database_targets.py -q` — 68 passed.
- Covered both committed orders: opt-out after all policy reads but before the final gate yields zero sends and `suppressed`; opt-out after the final gate yields one auditable `dispatched` attempt with a reservation marker, while consent is still revoked for future scope.
- Compile and whitespace checks are recorded with the scoped commit below.

### Review-round 2 commit

`fix: serialize WhatsApp opt-out final send gate` (scoped follow-up commit in this worktree).

## Review round 3 — atomic consent and outbox arbitration

- Refactored scoped-consent, outbox-entry, and reciprocal-suppression persistence helpers to support an explicit caller-owned transaction without changing their default committing behavior.
- Exact opt-out now starts one transaction, conditionally suppresses/unreserves every matching ready or dispatching outbox entry first, then writes the scoped-consent revocation and its immutable consent event, and commits all facts together.
- This ordering gives the outbox row a shared database arbitration point: when opt-out wins, the final gate blocks on that row and fails after commit; when the final gate wins, suppression updates zero rows and the opt-out records only its future-scope consent revocation.
- No provider call occurs in the transaction, and PostgreSQL uses the same private conditional updates through the adapter (its `BEGIN IMMEDIATE` compatibility statement starts the normal connection transaction).

### Review-round 3 verification

- Added a real two-connection SQLite interleaving: it pauses after the uncommitted consent/audit mutation, starts a concurrent final gate, proves the gate is blocked, then releases opt-out and proves the gate returns false.  The verifier observes the revoked consent, exactly one revoked consent event, and a suppressed unreserved outbox row together.
- Retained the post-gate test: consent is revoked for future scope but the already reserved send remains truthful/auditable and is not reported as suppressed.
- Focused Task 7/outbox/interaction/database suite: 48 passed.  Full combined communications/outbox/interaction/database suite: 69 passed; `compileall` and `git diff --check` also passed.

### Review-round 3 commit

`fix: atomically arbitrate WhatsApp opt-outs` (scoped follow-up commit in this worktree).
