# TrackWick live inventory — 04 August 2026

This is a read-only discovery snapshot of the Fortune TrackWick tenant. It was
made directly against the verified task, Customer CRM, and productivity APIs.
No raw source rows, phone numbers, Aadhaar numbers, photos, GPS, or credentials
are retained in this document or from the discovery step. The reviewed
CRM-basics lane below admits a name only with its stable provider identifier.

## What is there

The task history contains **5,891** records across **59 pages**:

| TrackWick form / task type | Records | What it can contribute |
| --- | ---: | --- |
| Farmer Visit | 4,552 | Crop observations, visit history, kit use, pesticide and fertiliser records, transplanting, water, officer activity |
| New Farmer Registration | 1,273 | Farmer and farm intake candidates, village/block/district, acreage, variety/kit context, plot-detail candidates |
| 1509 Farmers Data | 30 | Multi-plot crop and transplanting context for 1509 |
| Farmer Query | 13 | Farmer-raised action context |
| New Farmer Soil Testing | 14 | Soil-test intake context |
| Agronomy Team Task | 6 | Agronomy follow-up context |
| Early Field Visit Form | 2 | Early-season crop context |
| Registered Farmer Soil Testing | 1 | Soil-test context for an existing farmer |

Task status at the time of the read:

- 5,296 completed
- 154 in progress
- 441 pending

## Basic entity tables

These are the records the CRM-basics lane is permitted to stage. They remain
private source context until a Fortune manager accepts the links into the
canonical operating model.

| Entity | Live source and coverage | Basics staged now | Explicitly not copied |
| --- | --- | --- | --- |
| Farmer | 2,584 active TrackWick Customers | Stable customer code, provider ID, name, active status, owner code, registration date | Mobile number, exact CRM geo, raw tags if unreviewed |
| Farm candidate | 1,273 New Farmer Registration tasks | Linked farmer code when present; village, block, district, declared total acres, PB1/1718 acres, declared plot count, registration state | Aadhaar, family details, signature, photo, mobile, exact `Geo`, free-text comment |
| Field candidate | Registration `formTable Plot Details` and 1509 multi-plot forms | Not yet canonicalised: the source has plot/acreage and transplanting detail, but no proven stable plot identifier | The full raw plot table and all evidence until its field schema is reviewed once |
| Crop context | 4,552 Farmer Visits plus kit/registration forms | Farmer code, visit state, transplanting date, crop stage, water condition, crop-condition score, kit status | Photo, comment, exact visit GPS, unapproved pesticide/fertiliser free text |
| Field worker | Task assignment and daily productivity | Stable employee ID, assigned name, most recent task activity and status | Phone, email, live location, raw productivity trace |
| Follow-up | 595 in-progress or pending tasks; including Farmer Query and Agronomy work | Stable task ID, linked farmer/worker ID when present, task kind, state, reported time | The free-text question/comment body |
| Soil context | 15 soil-testing tasks | Stable task and farmer ID, task state | Laboratory report, photo, exact sample location, or any result not mapped to a reviewed soil schema |

The existing Farmer Visit metrics remain intact. These new records only add
the missing basics needed for the Farms, Farmers, Field Workers, and Inbox
surfaces; they do not assert land ownership, field boundaries, chemical
compliance, or a diagnostic verdict.

## What the data means in AGRO CEO

```text
TrackWick registration      -> Farmer and farm candidates
TrackWick plot / acreage    -> Field candidates
TrackWick transplanting     -> Season + crop context
TrackWick visit             -> Observations, chemical record, follow-up
TrackWick employee/activity -> Field-worker activity
```

This is deliberately a candidate and evidence lane first. A registration does
not silently create a canonical Fortune farmer, farm, field, or crop allocation:
those records need a stable source identifier, a reviewed link, and (for a
farm map) approved location provenance.

## Data handling boundary

The registration forms contain private identity and compliance-sensitive
fields, including a name, family details, mobile number, Aadhaar number,
signature/photo, coarse location, acreage, and plot detail. These fields must
not enter browser responses, Git, logs, a public Supabase schema, or the
current aggregate TrackWick metrics lane.

The CRM-basics connector retains the reviewed allow-list in the table above,
alongside Farmer Visit metrics and daily productivity. That makes the source
useful for real people and farm-candidate review without copying a contact
directory or evidence archive.

## Import order

1. Apply the reviewed `0008_agro_trackwick_crm_basics.sql` migration to the
   real Fortune private `agro` schema. The other Supabase environment present
   in this workspace is unrelated and is not used.
2. Keep the TrackWick credential in the server's production secret store. It
   is never browser-visible.
3. Pull all task types and Customers into the private **staging** lane,
   excluding Aadhaar, mobile, signatures, photos, comments, and raw GPS.
4. Review source identifiers to establish the three links that make the product
   real: TrackWick customer -> Farmer; registration/plot -> Farm and Field;
   TrackWick employee -> Field Worker.
5. Publish approved links and safe operational context. The manager surfaces
   then become real without treating an unreviewed form answer as an
   authoritative land or people record.

## What TrackWick access is proven today

- `GET /cust/1/api/task/list`: full historical task stream, including the
  forms above.
- `GET /cust/1/api/customer/list`: active Fortune Customer CRM.
- `GET /cust/1/api/task/get`: detail for an individual task.
- `GET /cust/1/api/asset/productivity`: daily field-worker activity.

The supplied TrackWick guide names Customers, Employees, Leads, Attendance,
and Reports as API groups, but does not provide their exact endpoint contracts.
The full task stream already supplies the first real CRM intake; those separate
endpoints should be added only after their read-only paths and schemas are
confirmed.
