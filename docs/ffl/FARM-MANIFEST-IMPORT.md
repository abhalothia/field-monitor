# Reviewed farm-manifest import

This is the first useful bridge from Fortune's existing operations to AGRO CEO.
It produces **reviewable location context**, not fake field pins and not a new
farmer CRM.

The manager-only endpoint is `POST /api/v1/farm-manifests/csv`. It requires the
server-derived manager token and stores the CSV as private evidence. The normal
CSV routes deliberately cannot create or read a farm-manifest batch.

## Required CSV columns

```csv
source_farm_id,record_status,state_name,district_name,village_name,pincode,source_recorded_at,source_record_ref,crop_name,season_name,latitude,longitude,location_precision,boundary_evidence_ref
```

- `source_farm_id`: opaque, stable ID from Fortune's approved source system.
- `record_status`: `active`, `inactive`, or `pending_review`.
- `source_recorded_at`: ISO-8601 timestamp from the source system.
- `source_record_ref`: source-system reference, not a person identifier.
- `crop_name`, `cultivar`, and `season_name` are optional context.

Rows without coordinates are accepted as **village context only**. A field map
marker requires a latitude/longitude pair, `location_precision=field_verified`,
and a `boundary_evidence_ref`. Village/PIN never creates a field marker,
boundary, land right, or agronomic recommendation.

The whole batch is retained and profiled first. The same named manager must
review and publish it. Publishing only makes the reviewed manifest available
for the future map/satellite binding; it does not create operating units,
parcels, blocks, allocations, or field work.

## Never include

Do not include names, phone numbers, email addresses, bank/payment details,
Aadhaar, contact rosters, or raw traceability documents. The importer rejects
common personal/payment columns before evidence retention.

## The supplied historical purchase CSV

`all_purchases_Dec27.csv` is useful provenance for a **future private
procurement-history lane**: it has purchase date, village, rate, bag/quantity,
variety, and supply-bill fields. It also contains `Farmer Name`, so it is not a
farm manifest and has not been imported, retained, or used as farm-map data.

Before a procurement lane is built, Fortune must choose its purpose and approve
a private pseudonymization/key-management path. That lane can show aggregated
village/variety/procurement history; it still cannot assert an individual field
location.
