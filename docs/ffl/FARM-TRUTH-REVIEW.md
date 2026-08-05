# Farm Truth manager review

Farm Truth is the deliberate, manager-only bridge from private TrackWick
evidence to Fortune's canonical operating records. It is a review queue, not
an importer. TrackWick remains read-only, and no candidate becomes a farm,
field, crop allocation, person relationship, land right, or map feature until
the relevant review gate is completed.

## Start one review session

1. Confirm the accountable manager is signed in and manager access is
   unlocked.
2. In **Farms**, open **Review candidates**.
3. Choose the operating unit and season you intend to review. If more than one
   valid context is available, select it explicitly; do not infer one from a
   village, farmer, visit, or crop label.
4. Refresh the candidate queue for that context. Refresh reads the existing
   typed private evidence only; it does not contact or update TrackWick.
5. Review one candidate at a time, make one decision, and continue to the next
   candidate.

The card is intentionally focused. Use its safe place, reported area,
registration, crop timing, people, recent-visit/open-work counts, and reason
chips to decide whether the evidence supports one operating record. Phone,
Aadhaar, raw GPS, media, raw forms, provider identifiers, and source free text
are outside this review surface and must not be copied into decision fields.

## What each decision means

### Accept

Accept means the manager has reviewed the evidence and deliberately asserts
one canonical parcel, its operational block, active seasonal crop allocation,
scoped grower relationship, dated right to operate, and—when supported and
selected—field-worker relationship. The transaction also records reviewed
source links and one acceptance audit event. An exact retry returns the same
canonical IDs and does not create a second set.

Acceptance is an operating-record decision, not a claim that the source GPS is
a surveyed boundary, that a pesticide event proves compliance, or that the
crop is export-ready.

### Needs evidence

Use **Needs evidence** when the candidate is plausible but a constrained fact
such as plot area, crop season, right to operate, farmer identity, or worker
assignment is not sufficiently supported. Give a short operational reason.
The case records the manager as reviewer and owner, remains visible through
the safe Inbox item, and creates **zero** canonical records, rights,
relationships, reviewed source links, or acceptance audits.

Resolve the evidence gap in its proper source/governance process. If later
typed evidence changes the supporting receipt, refresh can produce the new
reviewable candidate; do not edit the old decision or manufacture a canonical
record around it.

### Reject

Reject means the evidence does not belong in the selected operating unit and
season or should not become a Fortune operating record. Record a short reason.
The case retains its reviewer and review time for accountability and creates
zero canonical claims, source links, or acceptance audits. Rejection does not
delete or overwrite TrackWick evidence.

## Map publication is a separate review

Farm Truth acceptance does not publish geometry. Home and Farms maps consume
only the current separately reviewed and published farm-manifest geometry.
This second gate exists because a visit point, registration point, address,
village label, media capture point, or other TrackWick location is evidence of
activity—not proof of a field boundary.

Review the geometry manifest through the process in
[Reviewed farm-manifest import](FARM-MANIFEST-IMPORT.md). Until a permitted
point or boundary is reviewed and published there, the map must remain empty
for that record. Never use TrackWick raw GPS or an accepted record's place text
as an automatic map fallback.

## First-session success and rollout gate

The first review session succeeds when the manager has individually accepted
**25 evidence-backed records** in the chosen operating unit and season and the
resulting source links and audits pass review. Success is not a bulk import,
not 25 discovered candidates, and not 25 map pins.

Before production rollout:

- verify every accepted case produced one coherent canonical set and exact
  retries return its established IDs;
- verify needs-evidence and rejected cases produced no canonical claims;
- review the private source links and acceptance audit trail;
- separately review and publish only the permitted geometry manifest; and
- run the complete FFL test suite and production migration review.

Production deployment follows the 25-record manager review and these checks;
it is not the environment in which to discover whether bulk evidence maps
cleanly.
