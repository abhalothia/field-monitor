# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this app does

Streamlit dashboard that monitors **Pusa Basmati 1 (PB1) paddy plots in
Aligarh / Bulandshahr, western UP** across the 2025 kharif season
(Jun 1 2025 – Jan 15 2026). It pulls Sentinel-1 SAR and Sentinel-2 L2A
time series via Sentinel Hub / CDSE (plus CropSAR on openEO when
available), runs rule-based transplanting / harvesting / stress
detection, and renders weekly NDVI / RVI overlays on a Folium map
driven by a date slider.

The project started as a generic vegetation monitor. The generic
modules are still in `src/`, but the **app is paddy-only** — the
dashboard only wires up `Timeline map` and `Fields` pages. Other page
files under `dashboard/pages/` (overview, time_series, imagery, alerts,
observations) are dead code from the older flow and can be ignored.

## Common commands

```bash
# First-time setup
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set SENTINEL_HUB_CLIENT_ID, SENTINEL_HUB_CLIENT_SECRET
# and SENTINEL_HUB_ENDPOINT=cdse if using the free CDSE tier.

# Run
streamlit run dashboard/app.py
# First launch auto-creates the SQLite schema and seeds 11 sample
# PB1 plots in Maur/Aligarh (src/paddy_kharif/seed_fields.py).

# CLI alternative to the dashboard's "Fetch kharif 2025 season" button
python -m scripts.fetch_paddy_kharif --field-id plot_19902 --year 2025 --verbose

# Tests — only the paddy suite is maintained
pytest tests/paddy_kharif/ -q
pytest tests/paddy_kharif/test_phenology.py::test_harvest_optical_peak_drop -v
```

Legacy tests in `tests/test_kml_parser.py`, `tests/test_sentinel_client.py`
depend on `lxml` / `responses` and aren't maintained — skip them.

## Architecture highlights

### Season tagging is load-bearing

Every `index_readings`, `imagery`, `alerts`, and `fetch_log` row has a
`season_tag` column. Paddy data is tagged `'kharif_2025'`; legacy
generic data stays at `'generic'`. The `UNIQUE` constraints on
`index_readings` and `imagery` include `season_tag`, so the same
(field, index, date) can coexist across seasons.

`db/schema.py::create_tables` runs idempotent in-place migrations:
(1) execute `TABLES_SQL`, (2) run `MIGRATION_SQL` ALTERs that add
`season_tag` to pre-existing tables, (3) rebuild the UNIQUE constraint
via `_rebuild_*_unique` helpers, (4) execute `INDEXES_SQL`. Ordering
matters — season-aware indexes reference the column that the ALTERs
add. The migration parser strips `--` comment lines before splitting
on `;` (a comment glued to the next ALTER will cause the whole
statement to be skipped).

### Credit conservation in `src/paddy_kharif/paddy_fetcher.py`

Sentinel Hub bills per HTTP request, so a rerun on a fully-populated DB
must make **zero** API calls. Four guards enforce this:

- **G1 Pre-flight DB diff** — `_missing_weeks_for_index` queries the DB
  for every (field, index, season_tag) before any HTTP call and skips
  indices whose weekly grid is already populated.
- **G2 CropSAR-then-skip** — if CropSAR covers NDVI for the season via
  openEO, the Sentinel Hub Statistical NDVI call is suppressed and
  NDVI is marked covered.
- **G3 Chunk coalescing** — `_coalesce_missing` merges contiguous
  missing weeks into a single `fetch_statistics(date_from, date_to, P7D)`
  per index (Sentinel Hub returns the whole time series in one
  response).
- **G4 Overlay fetch gated on `sampleCount`** — an NDVI PNG for a week
  with zero cloud-free pixels would render grey; skip the Process API
  call and try an SAR-based RVI overlay instead. The UI map always has
  a tile to show.

This is covered by `test_fetch_kharif_season_rerun_makes_zero_api_calls`
and `test_fetch_kharif_season_fresh_run_makes_chunked_calls`.

### Dual-path phenology (`src/paddy_kharif/phenology.py`)

Transplanting, harvesting, and stress each run two independent
detectors in parallel:

- **Optical path** on Sentinel-2 LSWI/NDVI (Xiao 2005/2006 flood rule
  for transplant, NDVI peak-then-drop for harvest).
- **SAR path** on Sentinel-1 VV/VH/RVI (GAMMA0_ELLIPSOID, DESCENDING
  orbit for time-series consistency).

Monsoon clouds can blank the optical path for weeks in Jun–Sep western
UP, so the SAR path must fire independently. When both paths fire
within ±7 days, `_merge_dual_path` dedupes and upgrades confidence to
0.95.

Thresholds in `src/paddy_kharif/config.py` are literature defaults
(Xiao 2005/2006 for LSWI+0.05≥NDVI; Mosleh 2015, Son 2014 for
phenology windows). Run `calibration.calibrate_thresholds(conn)` after
a full season to override defaults from the `observations` table.

### Overlay lookup and map rendering

`dashboard/pages/paddy_timeline.py` renders one Folium `ImageOverlay`
per selected field, driven by a weekly date slider that snaps to the
same week-centers used by the fetcher. For each week,
`overlay_renderer.pick_overlay_for_week` prefers the NDVI PNG, falls
back to the SAR RVI PNG, then to the nearest-date overlay within ±7
days. Overlay bounds come from `src/geometry.py::get_bbox`.

### CDSE vs. legacy Sentinel Hub

`config.settings.get_sentinel_config()` auto-selects based on
`SENTINEL_HUB_ENDPOINT`:
- default `sentinel-hub` → `services.sentinel-hub.com`
- `cdse` → `identity.dataspace.copernicus.eu` (OAuth) and
  `sh.dataspace.copernicus.eu` (data API)

Credentials are **not** interchangeable between the two. CropSAR is
CDSE-only.

## Database quirks

- The DB file lives at `db/field_monitor.db` and is regeneratable.
- Do NOT run the project from inside Dropbox / iCloud / OneDrive — sync
  clients hold shared locks on the file and SQLite migrations fail with
  "database is locked". Move the repo to a non-synced path if you see
  lock errors.
- `@st.cache_resource` caches the single shared connection, but stale
  streamlit processes against the same file still cause lock errors:
  `pkill -f streamlit` before relaunching if the schema migration
  hangs.

## When adding new paddy signals or pages

- Fetcher changes should preserve the four no-double-pull guards above;
  add a regression test in `tests/paddy_kharif/test_paddy_fetcher.py`.
- Detector changes should go through `_merge_dual_path` so
  optical+SAR dedup stays consistent; add synthetic-series tests under
  `test_phenology.py`.
- Any new weekly-scoped data must be tagged with `season_tag`; re-use
  `repository_paddy.get_season_readings` / `get_existing_reading_dates`
  rather than reaching into `index_readings` directly.
