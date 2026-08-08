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

- The task's approved file list did not include a new PostgreSQL migration.  The new SQLite/private-schema tables are created by `create_communications_schema`; production PostgreSQL deployment needs the equivalent reviewed migration before enabling this routing path there.  Until then, a missing-table error requeues the sealed receipt and fails closed rather than creating a candidate.
