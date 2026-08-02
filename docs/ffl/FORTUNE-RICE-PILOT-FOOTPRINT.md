# Fortune Rice pilot footprint

This is a pilot-customer research note, not a product default and not a farm
directory. It records only public, first-party facts that are safe to use as
display context.

## What can be shown now

- **Network label:** contract farming in Western Uttar Pradesh.
- **Public network scale:** 2,500+ partner farmers, 15,000+ cultivated acres,
  and 250 villages.
- **Public hub:** K-378, G.T. Road, Village Nangla Chamru, Dadri, Uttar
  Pradesh 201314. Fortune describes this as its private mandi and lists a UP
  processing facility.
- **Other public infrastructure:** additional processing capacity in Central
  India and warehouses at Kandla Port, Gujarat. Neither page supplies an exact
  facility coordinate, so neither belongs on a precise map.

Sources: Fortune Rice's [model](https://www.fortunerice.in/our-model),
[operations](https://www.fortunerice.in/operations),
[about page](https://www.fortunerice.in/about), and
[contact page](https://www.fortunerice.in/contact), reviewed on 2026-08-02.

## What must not be inferred

The public pages do not enumerate partner farms, village names, boundaries,
field coordinates, current crop allocations, or device locations. An aggregate
network claim is not evidence that any particular farm is a Fortune farm.

Do not turn the public network count into 250 pins, scrape farmer identities,
or represent town-centre geocoding as a facility or parcel location.

## Optional display profile

Once Fortune confirms this public display context, set the reusable
`FFL_OPERATING_PROFILE_JSON` configuration from
[OPERATING-PROFILE.md](OPERATING-PROFILE.md). This draft deliberately marks
**Dadri town**, rather than guessing the exact gate or any partner farm.

```json
{
  "display_name": "Fortune Rice Limited",
  "website_url": "https://www.fortunerice.in",
  "coverage_label": "Contract-farming network in Western Uttar Pradesh",
  "network_summary": "Public company claim: 2,500+ partner farmers, 15,000+ cultivated acres, and 250 villages",
  "public_hub_label": "Dadri public mandi and processing hub (town-level marker)",
  "source_url": "https://www.fortunerice.in/our-model",
  "map_embed_url": "https://www.openstreetmap.org/export/embed.html?bbox=76.85%2C27.45%2C79.05%2C29.75&layer=mapnik&marker=28.5534523%2C77.5555503"
}
```

The configuration renders a zoomed-out Western UP map and one town-level
public-hub marker. It does **not** expose farms.

## The useful next dataset

Ask Fortune for a reviewed, minimum farm manifest from its existing approved
traceability or extension system. Each row should carry an opaque source farm
ID, village/PIN or approved geometry, active/inactive status, crop/season,
recorded-at time, source-system reference, and approval/provenance. Names,
phone numbers, payment data, and raw farmer documents do not belong in this
first import.

FFL should match and retain each row against an accountable operating unit,
land right, and season before any field pin becomes visible. A village/PIN only
provides administrative context; it does not prove a field boundary. This is
the point where satellite, weather, soil, and mandi data become genuinely
actionable rather than attractive background layers.
