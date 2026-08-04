# TrackWick live inventory — 04 August 2026

This is a read-only discovery snapshot of the Fortune TrackWick tenant. It was
made directly against the verified task and productivity APIs. No source rows,
names, phone numbers, Aadhaar numbers, photos, GPS, or credentials are
retained in this document or the application from this discovery step.

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

The existing live connector is intentionally narrower: it retains only
aggregated field context from **Farmer Visit** plus daily productivity. That is
enough for COO coverage, crop signals, and chemical-record cues, but it is not
yet the full people-and-farms CRM import.

## Import order

1. Connect the real Fortune private Postgres/Supabase database and apply the
   reviewed `agro` migrations. The Supabase environment currently available in
   this workspace is not the Fortune operating database and has no exposed
   `agro` schema.
2. Place the existing TrackWick credential in the server's production secret
   store and enable the read-only connector. It is never browser-visible.
3. Pull all task types into a private **staging** lane, excluding Aadhaar,
   mobile, signatures, photos, and raw GPS by default.
4. Review source identifiers to establish the three links that make the product
   real: TrackWick customer -> Farmer; registration/plot -> Farm and Field;
   TrackWick employee -> Field Worker.
5. Publish approved links and safe operational context. The manager surfaces
   then become real without treating an unreviewed form answer as an
   authoritative land or people record.

## What TrackWick access is proven today

- `GET /cust/1/api/task/list`: full historical task stream, including the
  forms above.
- `GET /cust/1/api/task/get`: detail for an individual task.
- `GET /cust/1/api/asset/productivity`: daily field-worker activity.

The supplied TrackWick guide names Customers, Employees, Leads, Attendance,
and Reports as API groups, but does not provide their exact endpoint contracts.
The full task stream already supplies the first real CRM intake; those separate
endpoints should be added only after their read-only paths and schemas are
confirmed.
