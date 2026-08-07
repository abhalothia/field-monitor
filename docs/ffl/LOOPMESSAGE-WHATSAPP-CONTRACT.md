# LoopMessage WhatsApp contract boundary

Status: **BLOCKED — sandbox proof is unavailable.**

This repository does not contain credentials for a named non-production
LoopMessage sandbox account or an authorized test contact. No message was sent
while establishing this boundary. Public material did not provide an exact,
verified WhatsApp template-send and reply wire contract, so the production
adapter does not construct a template JSON payload and `send_template()` fails
closed.

## Required proof record

The table freezes the provider-neutral fields that downstream FFL code may use.
It does not claim that the similarly named fields are LoopMessage JSON keys.

| Capability | Sandbox result | Required adapter field |
|---|---|---|
| Template send | BLOCKED — no sandbox account/test contact; provider message ID not observed | template ID, locale, parameter map, passthrough |
| Inbound reply | BLOCKED — parent message/correlation field not observed | `reply_to_message_id` |
| Delivery callback | BLOCKED — status and configured sender callback not observed | provider message ID, status, sender |
| Media | BLOCKED — media retrieval flow not observed | opaque attachment reference |
| Opt-out | BLOCKED — provider event/text behavior not observed | `opt_out` intent |

## Frozen internal behavior

- `CommunicationsProvider.send_template()` accepts contact, sender, provider
  template ID, locale, a string parameter map, and passthrough context.
- `FakeLoopMessageProvider` preserves those values and returns deterministic
  provider message IDs without network access.
- A normalized inbound event carries an optional `reply_to_message_id`, one of
  the constrained FFL intents (or no intent), and opaque attachment references.
- The deterministic fake recognizes exact `STOP` text as `opt_out` and accepts
  the fake-only top-level `reply_to_message_id` used by contract tests.
- The real adapter deliberately returns no reply correlation mapping and refuses
  template sends because those production wire locations remain unverified.
- Raw payloads, contact addresses, and remote media URLs remain available only
  during sealed-receipt processing; routine event storage receives redacted
  metadata and opaque references.

## Evidence needed to unblock

Using a named, non-production LoopMessage sandbox account and authorized test
contact, capture immutable non-secret evidence for all five rows above. Record
the sandbox account label, UTC observation time, API/version reference, sanitized
request/response field paths, configured sender callback behavior, and provider
message/event IDs in redacted form. Only then may the real adapter map and send
the verified template payload. Credentials, full phone numbers, message content,
raw payloads, and remote media URLs must not be committed.
