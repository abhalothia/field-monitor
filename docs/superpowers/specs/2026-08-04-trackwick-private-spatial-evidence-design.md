# TrackWick private spatial evidence

## Goal

Import Fortune's TrackWick CRM, visits, registrations, plots, precise source
locations, and crop/plot-photo references into AGRO CEO's private `agro`
schema. The manager service can later render them on a private map and serve an
image through a controlled backend endpoint. Nothing in this lane creates a
canonical farm, land parcel, person relationship, crop allocation, diagnosis,
or chemical recommendation.

## Existing boundaries

`agro_trackolap_records` remains the existing safe, aggregate COO metrics
feed. It is not extended into a raw JSON source lake. `agro_people`,
`agro_land_parcels`, `agro_operational_blocks`, and
`agro_crop_allocations` remain reviewed operating truth. TrackWick rows become
candidates and connect to those records only through named review links.

The database schema remains private: `agro` is not a Supabase Data API schema;
`PUBLIC`, `anon`, and browser clients receive no table grants. Manager routes
use the existing server-side manager session. Photo URLs and exact locations
never enter an ordinary browser JSON response.

## Inbound allow-list

| TrackWick data | Destination | Rule |
|---|---|---|
| Customer code, name, status, owner, tag, created time | `agro_trackwick_parties` | Farmer source identity only; it is not an `agro_people` row. |
| Customer and registration mobile | `agro_trackwick_contact_points` | Restricted private contact vault; consent is initially `unknown`. |
| Assigned worker ID/name and productivity date | parties and worker-day rows | Source activity, not a reviewed worker relationship. |
| Task type/status/times | `agro_trackwick_tasks` | One current typed task row per provider task. |
| Farmer Visit crop timing, condition and kit | `agro_trackwick_visits` | A reported observation, not an agronomic conclusion. |
| Pest/disease and chemical answers | finding/input child rows | Preserve reported value and source field; do not infer severity or compliance. |
| Registration village/block/district/area | registration and plot rows | A farm/plot candidate, not a canonical farm. |
| Completion, visit, registration and photo GPS | location observations | Exact manager-only evidence points with explicit source kind and confidence. |
| Crop/plot photo URL, provider time, provider geo | media references | Remote reference only; manager proxy may fetch it. |

The importer rejects Aadhaar numbers/photos, signatures, free-text comments,
unknown media labels, and raw provider payloads.

The private contact value is not selected by ordinary manager list/map queries
and no route serialises it until Fortune adds a separate, reviewed contact
surface. Database privacy and the existing server-only connection boundary are
the V1 control; end-to-end field encryption is a future contact-service project,
not an unimplemented claim in this import.

## Tables and joins

Existing `agro_source_registry` and `agro_source_runs` identify TrackWick and
every pull. New source rows carry `source_id`, `source_run_id`, provider
identifier, provider timestamps, `first_seen_at`, `last_seen_at`, a
fingerprint, mapping version, and a quality state.

`agro_trackwick_parties` holds source farmers and workers. Contacts are kept
in a separate vault. Tasks join to optional farmer and worker parties. Farmer
Visit tasks have one visit row and zero or more reported findings/input events.
Registration tasks have one registration row and zero or more plot rows.

Locations point to a task, registration, and/or media reference, with a check
requiring at least one parent. Crop/plot media joins to the source task and
optional capture location. A crop photo resolves as:

`media reference -> capture location -> visit task -> farmer/worker -> visit facts`.

Three review-link tables preserve foreign keys: source party to
`agro_people`, source plot to a reviewed parcel/block, and source task to
`agro_crop_allocations`. Unlinked source rows remain valid and visibly
unresolved.

The PostgreSQL migration is mirrored by a minimal SQLite test schema with the
same relational fields and constraints except the generated PostGIS geography
column. This keeps the source normaliser and repository lane testable locally;
production remains the only place that creates the spatial index.

## Spatial and media contract

Each location stores typed latitude/longitude, a PostGIS
`geography(Point, 4326)`, source address detail, point kind, `observed_at`,
and one of `declared`, `observed`, or `verified`. A GiST index supports
bounds and distance queries. A location is a pin/evidence record, never a
field boundary.

Media is remote-only initially. The private table stores an allow-listed HTTPS
provider URL, provider-created time, media kind (`crop_photo` or
`plot_photo`), source state, and future EXIF/content metadata state. The
future serving route validates manager access and the fixed TrackWick image
host before streaming; it does not redirect a browser to the stored URL. If a
manager later retains a file, a content-hashed `agro_evidence_artifacts` row
is created and linked without changing the source reference.

## Intelligence-ready, not intelligence-built

No AI/vision request is made in this slice. A later provider adapter, such as
Brain.new if its contract is approved, writes a new immutable analysis run
linked to a retained media artifact or private media reference. It records
provider, model/version, requested purpose, input fingerprint, result, time,
confidence, and review state. It cannot alter photo metadata, source GPS,
visit facts, or field status. A result is a review candidate, never a diagnosis
or automatic action.

## Import semantics

The first manager-authorised run pages the full TrackWick history with `pn`
and `pt`. Later runs use the existing overlapping creation-time window. Each
run uses batch upserts keyed by source/provider identity, updates
`last_seen_at`, and changes a typed record only when its allow-listed
fingerprint changes. All rows for one source run commit atomically; a malformed
row is quarantined with a safe reason, while a failed transaction writes no
partial source state.

## Non-goals

- Farm or field geometry inferred from a point.
- Public, farmer, or field-worker access.
- Contact messaging, consent collection, or phone display.
- Image copying, AI vision, diagnosis, or agronomic recommendation.
- TrackWick write-back.
