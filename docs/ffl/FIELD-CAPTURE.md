# Native field capture

The native field PWA is the assistive fallback for a person already assigned
to a crop allocation. It records a bounded, structured observation for manager
review. It is not a chat system, an open upload form, a location tracker, or a
way to complete a work item.

## Safe operating loop

1. A manager creates and marks ready a bilingual field-information request.
2. The request's target must have a current explicit relationship to its crop
   allocation. A village, contact, job title, purchase row, or GPS point never
   establishes that relationship.
3. A manager chooses one already-published signal template and issues a
   short-lived capture pass. The sole response containing the opaque bearer
token is given to the field person as a `/field#capture=…` link. The browser
removes the fragment after reading it, and the raw token is never stored in
the database. The standard Fortune launch login remains a separate access
gate where that deployment setting is enabled.
4. The field person sees only the scoped block/crop, bilingual request copy,
   due time, and template fields. They cannot name a person, allocation,
   template, reviewer, work status, or evidence artifact ID.
5. A submitted note creates a `review` candidate. Required photo proof is
   retained through the private content-addressed evidence store before the
   candidate is created. The PWA does not cache raw notes, photos, locations,
   or outbound requests locally.
6. A manager inspects the candidate and either rejects it or explicitly accepts
   it. Acceptance re-runs the canonical published-template validation and then
   creates one canonical field signal. It never completes linked work, resolves
   an exception, creates agronomic advice, or marks a request delivery state.

## Required server configuration

`FFL_FIELD_CAPTURE_SIGNING_KEY` is a server-only random secret of at least 32
characters. Its only purpose is keyed hashing of opaque capture passes. Do not
put it in Vercel client variables, a URL query string, seed data, tests, logs,
or source control.

In production, private evidence storage must be configured independently. If
the evidence store is unavailable, evidence-required field capture fails
closed. The browser does not receive a storage key, public evidence URL, or
bucket path.

## Deployment and migration

Apply [0007_agro_field_capture.sql](../../db/postgres/0007_agro_field_capture.sql)
manually using the reviewed private `agro` migration role, after migrations
`0001` through `0006`. This adds only `agro_field_capture_passes` and
`agro_field_capture_candidates`, keeps both private, and grants nothing to
`PUBLIC`.

This path has no TrackOlap/TrackWick, WhatsApp, LoopMessage, Hermes, live-send,
GPS, or public-data dependency.
