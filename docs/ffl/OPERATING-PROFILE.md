# Operating profile

The command surface has one optional, read-only operating profile. It lets a
single-user pilot show its name, public website, public operating-area label,
and a public hub map without turning a customer into application code.

Configure it at deployment time with `FFL_OPERATING_PROFILE_JSON`. It is not a
database record and it has no browser write endpoint.

```json
{
  "display_name": "Example Rice Operations",
  "website_url": "https://example.com",
  "coverage_label": "Western Uttar Pradesh",
  "public_hub_label": "Dadri public hub",
  "source_url": "https://example.com/operations",
  "map_embed_url": "https://www.openstreetmap.org/export/embed.html?bbox=76.6%2C27.4%2C79.0%2C29.7&layer=mapnik&marker=28.58%2C77.55"
}
```

All values are optional apart from `display_name` once a profile is present.
URLs must use HTTPS. The map is deliberately restricted to a standard
OpenStreetMap embed URL and requires a public-hub label. It must show only a
reviewed public operating area or public hub—never individual partner farms,
people, field boundaries, phone numbers, or evidence locations.

Leave the variable unset until the customer has confirmed the public profile.
The manager then shows an explicit empty state rather than guessing or
fabricating farm locations.
