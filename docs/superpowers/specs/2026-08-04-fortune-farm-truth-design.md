# Fortune Farm Truth review design

## Purpose

Turn a very small number of the existing TrackWick registration and visit
records into Fortune's first reviewed operating records. The manager gets one
job: decide whether the evidence is sufficient to create a real farm/field
record for the current season.

This is the critical product wedge. It makes the map, Farms, Farmers, Field
Workers, and Inbox useful without pretending that a CRM row, village, GPS
point, or visit automatically proves a farm.

## Narrow scope

The first release is a private manager-only **Farm Truth review queue**. It
does exactly three things:

1. Proposes the best-supported TrackWick registration/plot candidates.
2. Shows the minimum private source context needed for a human decision.
3. Atomically accepts or rejects one candidate, retaining the decision and
   source links.

It does not bulk-publish TrackWick data, import contact information, display
source GPS/photos, draw a boundary, recommend a crop treatment, create a
purchase/compliance claim, or expose a farmer/worker portal.

## Why this comes before the other loops

Fortune now has 1,273 registration candidates, 2,584 active source farmers,
and 4,552 Farmer Visit records. None is yet a reviewed Farm, Field, Farmer,
Crop season, or worker assignment. The shared join for purchase capture,
chemical proof, and intervention is a reviewed crop allocation on a field.

The Farm Truth queue creates that join for the first 25–50 farms. It requires
one existing Fortune operating unit and a current season before a case can be
accepted. Procurement, approved kit schedules, image intelligence, Hindi
self-service, and map layers remain separate later projects.

## Domain mapping

The UI uses Fortune language; the private schema preserves the existing
durable model.

| Manager term | Canonical record | Source context | Rule |
|---|---|---|---|
| Farm | `agro_land_parcels` within the Fortune operating unit | TrackWick registration | A registration does not create it until review. |
| Field | `agro_operational_blocks` linked to its parcel | TrackWick registration plot | One accepted source plot creates one field; a registration with no plot is held. |
| Crop | `agro_crop_allocations` for a selected existing/current season | registration/visit cultivar and transplanting context | The reviewer confirms crop, cultivar, area, and season. |
| Farmer | `agro_people` plus an active `grower` relationship | TrackWick farmer party | A source name/ID is linked through a reviewed party-person link. |
| Field worker | `agro_people` plus an active `field_operator` relationship when known | TrackWick employee party/task activity | Leave unassigned when evidence is insufficient; never guess. |

The acceptance transaction also records reviewed source links in
`agro_trackwick_party_person_links`,
`agro_trackwick_plot_operating_links`, and, when a visit is explicitly tied to
the accepted allocation, `agro_trackwick_task_allocation_links`.

## Candidate selection

The queue has no opaque quality score. It lists candidates when all of the
following are true:

- a valid, completed TrackWick registration exists;
- the registration has a linked farmer party and at least one valid plot row;
- the candidate has a declared positive plot/registration area; and
- a completed Farmer Visit exists for that farmer in the selected active
  season window.

Rows are ordered by a transparent, stable priority: open linked field work
first, then most recent completed visit, then registration date. Each card
states the reasons it was proposed—for example, `registration + 2 recent
visits + open follow-up`—rather than displaying a numerical score.

The first session is limited to 50 candidates. A candidate already accepted,
rejected, or awaiting evidence is not proposed again unless a new source
receipt changes its supporting context.

## The one review screen

One card is open at a time. It contains only:

- proposed farm/field label, village/block/district context, declared area,
  plot count, source crop/transplanting context, and latest visit date;
- named farmer source party and, only when linked by source work, field-worker
  source party;
- a short source-evidence strip: registration, plot, recent visit count, and
  open-work count;
- the manager-confirmed inputs: Fortune operating unit, field label, managed
  area, current season, crop/cultivar, grower effective date, and dated
  right-to-operate basis; and
- three actions: **Accept farm**, **Needs evidence**, and **Reject**.

The review screen never shows phone numbers, Aadhaar, raw GPS, source media,
free text, or an unreviewed location. A map pin/boundary remains absent unless
the separate reviewed farm-manifest geometry gate is satisfied.

## Decision semantics

### Accept farm

Acceptance is one database transaction. It validates the manager-entered
fields, creates the reviewed canonical records and reviewed source links,
creates active grower/field-operator relationships when confirmed, and writes
an audit event with reviewer, time, and reason. An allocation can link only
the exact source visits selected by the reviewer.

The manager must confirm a dated right-to-operate basis. This records
Fortune's operating relationship; it does not establish legal land ownership.

### Needs evidence

No canonical record is created. The case records a structured missing item:
plot/area, crop/season, right-to-operate basis, farmer identity, or worker
assignment. It appears in Inbox as one owner-assigned request. Geometry is a
separate map-publication gate and never blocks an otherwise valid operating
record.

### Reject

No canonical record is created. The source row remains private and immutable.
The reviewer records a concise reason such as duplicate, outside programme,
or incorrect source linkage. A later source change can create a new review
case; rejection never mutates the receipt.

## Data and access boundary

- TrackWick remains a read-only source; AGRO CEO does not write back tasks,
  people, attendance, or crop data.
- Source rows retain provider IDs, source run, mapping version, observed time,
  received time, and source fingerprint.
- The new review-case and canonical records stay in the private `agro` schema.
  They receive no Supabase Data API/browser grant.
- Only a current verified owner/admin manager session can list or decide a
  case. The server derives the reviewer identity; the browser cannot supply
  it.
- Acceptance is idempotent by review-case ID. A retry returns the first result
  and cannot duplicate land parcels, blocks, people, allocations, or links.

## Failure handling

If required source links are missing, the current season is absent, managed
area is invalid, or a canonical/source link conflicts with an existing
reviewed record, acceptance fails without writing any canonical record. The
case stays reviewable and explains the missing/contradictory field. Runtime
errors never downgrade a rejected or needs-evidence case into an accepted one.

## Success measure

The release is complete when one named Fortune reviewer accepts 25 real farms
in a single session or set of sessions, and each accepted record has:

- a reviewed farmer source link;
- a reviewed plot-to-field link;
- one active crop allocation in the selected season;
- a named grower relationship;
- a recorded right-to-operate basis; and
- an audit event naming the reviewer.

The manager's Farms map/card/table can show these accepted records, but only
records with separately published verified geometry appear on the map. The
test suite proves that a raw TrackWick row, source GPS point, failed
acceptance, duplicate retry, or rejected candidate cannot produce a canonical
farm or map feature.

## Explicit non-goals

- No production purchase-share number until Fortune supplies reviewed harvest
  and procurement data for the same linked grower/crop allocation.
- No EU/export/compliance conclusion from reported input usage.
- No pest/disease diagnosis, cure, or autonomous recommendation.
- No photo download, EXIF extraction, or vision model in this release.
- No customer phone portal launch dependence; DNS and Supabase phone-auth
  activation are independent infrastructure work.
