# PRD 07 — Field Communications and WhatsApp

**Status:** V1, after evidence and season-execution foundations

## Objective

Make the FFL operating loop feel immediate in the channel field teams already use: a person can receive the right short prompt, submit a photo or deviation without wrestling with a desktop form, and see that it reached a responsible manager. WhatsApp reduces input friction and missed handoffs; FFL remains the only operational record.

## Product thesis

The magic is not a chatbot. It is a trustworthy handoff: one clear bilingual prompt knows the relevant work and crop stage; one field response becomes a linked, reviewable FFL candidate; one human owns the next action. The team should never have to reconstruct a decision from a lost chat, and the product must never mistake a message read for field work performed.

This PRD applies only the LoopMessage reliability and interaction lessons developed in the personal-assistant repository: event idempotency, explicit intent, delivery observability, consent, and approval before consequential action. It does not integrate, expose, copy, or depend on the personal-assistant product or its private data.

## Users and promises

| User | Promise FFL makes |
|---|---|
| Field operator | “I receive a short, understandable request and can report what I see with a photo, voice note, location, or structured reply.” |
| Farm manager | “Every WhatsApp-originated item is tied to a known sender and farm context, or clearly asks me to resolve it.” |
| Agronomist | “A message can surface a crop-stage deviation quickly, but it cannot fabricate a completion, diagnosis, or intervention.” |
| Operations lead | “I can see consent, delivery health, unresolved communications, and fallback failures without reading private conversations.” |

## First release: the work-to-deviation loop

1. A manager assigns a stage-critical work item in FFL and selects an approved, purpose-specific WhatsApp template.
2. FFL verifies current consent, locale, quiet-hours policy, and the approved sender identity; it sends only through the configured provider contract.
3. The operator receives a concise Hindi/English prompt with the farm and requested action, and can choose **confirm**, **report a deviation**, **send evidence**, or **request a call-back**.
4. FFL records the provider event once, preserves its source and evidence, and resolves it to the named work/allocation only when the relationship is unambiguous.
5. A valid structured response creates the normal FFL signal/exception candidate; missing evidence, unclear location, or unrecognized intent goes to manager review.
6. The responsible FFL user accepts, corrects, or rejects the candidate. Work, exception, decision, and audit state change only through their existing canonical paths.
7. If the send fails, is suppressed by consent, or receives no response by the configured threshold, the manager sees the work still open and the fallback route is invoked.

## Required records

| Record | Purpose |
|---|---|
| Communication endpoint | A reviewed WhatsApp destination associated with a person/contact, provider, locale, and scoped operating relationship. |
| Communication consent | Purpose-specific permission, proof, capture time, revocation, and retention basis. |
| Communication template | Versioned, provider-approved message/flow identity, variables, locale, owner, and allowed operational intent. |
| Communication event | Immutable inbound/outbound envelope keyed by provider event ID, direction, timing, sender/recipient, intent, and processing state. |
| Delivery attempt/status | Provider acceptance and later delivery/read/failure updates, separate from a user action. |
| Communication link | The explicit link from an event to a draft signal, exception candidate, evidence artifact, or work item. |

The original provider event remains attributable and append-only. Corrections are linked records; FFL does not mutate a historical message to make it fit a later understanding.

## Functional requirements

### Consent, identity, and trust

- No outgoing operational message is sent without current, purpose-specific opt-in for that contact and operating relationship. Capture consent and opt-out through an accountable, reviewable path; provider opt-out signals take immediate effect.
- FFL does not infer a person, farm, or allocation merely from a phone number, display name, language, or previous conversation. A conflict or ambiguity must enter review.
- Access to message content and media is role-scoped and purpose-limited. The manager dashboard shows operational status by default, not a searchable employee conversation archive.
- The implementation follows applicable WhatsApp Business policies and FFL's data-rights/privacy review before real numbers or live production messaging are enabled.

### Inbound reliability

- Verify the provider webhook handshake and signed request before parsing an event. Use constant-time signature comparison and preserve the exact provider event identifier for idempotency.
- Persist the minimal receipt atomically, then acknowledge promptly. Route slow media retrieval, transcription, normalization, and candidate creation through a recoverable background worker; no event is lost because FFL took too long to respond.
- Quarantine invalid signatures, malformed messages, unsupported types, unresolvable endpoints, duplicate conflicts, and exhausted processing retries. Managers can see and resolve the queue without the item silently disappearing.
- Persist observed/created time supplied by the operator separately from provider-received time and FFL-processed time.

### Outbound reliability and human authority

- A provider-approved template is required whenever the provider's conversation policy requires it. FFL versions templates, validates variables, records the initiating user/policy, and stops a send that has no valid template or consent.
- The product supports only direct operational communications: assigned-work prompts, safety/exception escalation, request-for-evidence, callback coordination, and non-material status acknowledgement. It does not run marketing, harvesting campaigns, generic chat, or group management.
- Deterministic reminders use a published FFL rule and an approved template. Free-form replies, material decision requests, and any crop-intervention content require a named human review and send approval.
- Delivery, read, and button-response data are observable events. None of them closes work, resolves an exception, or counts as evidence of execution.
- A hard failure or configurable no-response window escalates to the named fallback owner through FFL; it never changes the underlying work status to successful.

### Structured capture

- Render only context-specific, low-cognitive-load questions. Provider-supported buttons/lists/flows may collect an explicit intent; they may not create arbitrary fields or bypass signal-template validation.
- A location, photo, voice note, document, or text becomes an immutable evidence artifact and candidate input. High-risk or ambiguous information remains human-reviewed; optional transcription/extraction is a cited draft, not a farm fact.
- Every published result links to its communication event, template version, sender, consent, received time, evidence, allocation resolution, and accepting actor. Users can trace FFL facts outward without exposing unrelated thread content.

## Success criteria

- A consented field operator can report a material deviation with evidence in WhatsApp, and a manager can accept it into the canonical exception path without manual re-entry.
- Replayed provider webhooks produce exactly one communication event and no duplicated signal, exception, or work transition.
- An opt-out, invalid signature, unavailable template, undelivered prompt, or ambiguous sender is visible and cannot falsely show a work item as completed.
- A manager can trace a WhatsApp-originated operating record to its provider event, consent, template/version, timestamps, and evidence in under two minutes.
- The native field PWA remains fully usable when WhatsApp is unavailable, declined, delayed, or unsuitable.

## Non-goals

- A general-purpose AI agent, unbounded WhatsApp chat, group ingestion, contact synchronization, or marketing automation.
- Autonomous agronomic advice, pesticide/irrigation instruction, trial assignment, decision approval, or record publication through a message.
- A dependency on the personal-assistant repository, its data, its authentication, or its implementation.
- Treating message delivery/read status as consent, attendance, work completion, or agronomic evidence.
