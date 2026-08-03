# Fortune purchase capture

Use this only when Fortune can export a **single season, single-date** snapshot
of grower harvest and Fortune purchase. It measures the share of *reported
harvest* bought by Fortune. It is not a district market-share claim.

The manager-only endpoint is `POST /api/v1/procurement-capture/csv`. It accepts
base64-encoded UTF-8 CSV with exactly these columns:

```csv
season_code,farmer_code,harvested_quantity_qtl,fortune_purchase_quantity_qtl,snapshot_date
Kharif-2026,opaque-code-from-trackwick,10,8,2026-11-10
```

- `farmer_code` must be the opaque TrackWick `customerIden` value—not a name,
  phone number, purchase number, bill number, or payment identifier.
- A farmer may appear once in the snapshot. `fortune_purchase_quantity_qtl`
  cannot exceed reported harvest.
- All rows must share one `season_code` and `snapshot_date`.

The importer uses the code only in memory to check a coherent snapshot. It
retains an aggregate with farmer count, reported harvest, Fortune purchase, and
the resulting share; the source code and any personal or payment data are not
stored. A named manager must review and publish the batch before it can affect
the private TrackWick metrics endpoint.

The Home card remains **Farmer reach** until such a published snapshot exists.
Then it becomes **Purchase share** and states its reported-harvest basis.
