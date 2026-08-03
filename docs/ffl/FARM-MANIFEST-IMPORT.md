# Reviewed farm-manifest import

This is the first useful bridge from Fortune's existing operations to AGRO CEO.
It produces **reviewable location context**, not fake field pins and not a new
farmer CRM.

The manager-only endpoint is `POST /api/v1/farm-manifests/csv`. It requires the
server-derived manager token and stores the CSV as private evidence. The normal
CSV routes deliberately cannot create or read a farm-manifest batch.

## Readiness before publication

`GET /api/v1/farm-manifests/{import_batch_id}/readiness` is also manager-only.
It returns a concise aggregate: total rows; village-context, verified point,
and verified boundary counts; active/inactive/pending-review/invalid/quarantined
counts; and how many rows still lack verified geometry evidence. It includes
the evidence artifact ID, SHA-256 content hash, and mapping version so a
manager can trace the review without exposing CSV rows, source identifiers,
coordinates, names, or other personal data.

The readiness response never publishes a field. Its `private_features_ready`
count stays zero until the existing manager review and publication gates pass;
`public_features_ready` is always zero. This importer is not a public-map data
source.

## Required CSV columns

```csv
source_farm_id,source_plot_id,plot_label,area_hectares,record_status,state_name,district_name,subdistrict_name,village_name,village_lgd_code,pincode,source_recorded_at,source_record_ref,crop_name,cultivar,season_name,latitude,longitude,boundary_geojson,location_precision,boundary_evidence_ref
```

- `source_farm_id`: opaque, stable ID from Fortune's approved source system.
- `source_plot_id`: optional opaque plot/block ID. Use it when one farm has
  more than one plot; do not reuse it across rows.
- `plot_label` and `area_hectares`: optional operational context. Area does
  not establish a land right.
- `subdistrict_name`, `village_lgd_code`, village, and PIN form the
  administrative hierarchy. **India uses a PIN, not a ZIP.** A PIN or village
  is context only, not geometry.
- `record_status`: `active`, `inactive`, or `pending_review`.
- `source_recorded_at`: ISO-8601 timestamp from the source system.
- `source_record_ref`: source-system reference, not a person identifier.
- `crop_name`, `cultivar`, and `season_name` are optional context.

Rows without geometry are accepted as **village context only**. A field point
requires a latitude/longitude pair, `location_precision=field_point` (the
legacy synonym `field_verified` is accepted), and a `boundary_evidence_ref`.
A proper plot shape requires quoted GeoJSON `boundary_geojson`,
`location_precision=field_boundary`, and a `boundary_evidence_ref`. Only a
published batch exposes verified private GeoJSON through the manager-only map
features endpoint. Village/PIN never creates a field marker, boundary, land
right, or agronomic recommendation.

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
