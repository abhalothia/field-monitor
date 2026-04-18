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

## Next steps for the next Claude Code session

The user's goal: **diagnostic depth for extension-agent triage** —
inspect a plot, read its crop signals, classify the stress type, and
decide which fields need a physical visit first. Everything below is
already scoped and approved by the user; pick it up in order.

### 1. Seed 20 additional plots (quick, no API cost)

Extend `SAMPLE_PLOTS` in `src/paddy_kharif/seed_fields.py` with the 20
plots under supervisor DEEPOO SINGH. Tuple format is
`(plot_id_str, owner, village, "ALIGARH", wkt)`. The WKT polygons are
in the previous user message in the transcript at
`/root/.claude/projects/-home-user-field-monitor/f6720085-ba81-468e-90f7-5e1569db42cc.jsonl`
(grep for `PAIMPUR|BHURGARHI|DETA KHURD|PIPLI`). Village counts:

- PAIMPUR × 17: 96307, 96306, 105702, 94805, 280601, 105003, 103103,
  344203, 104902, 290106, 395302, 406001, 405802, 105204, 105902,
  103105, plus one more if the transcript yields it
- BHURGARHI × 2: 102205 (SANJAY), 176801 (SUKHVEER SINGH)
- DETA KHURD × 1: 178303 (SATISH KUMAR)
- PIPLI NANGLA KADIRPUR × 1: 246401 (PRADEEP)

After editing, delete `db/field_monitor.db*` and relaunch streamlit to
re-seed from scratch (seeder is a no-op when `fields` is non-empty).

### 2. Build `dashboard/pages/inspect.py` — the diagnostic page

This is the core of the pivot away from the SmartRisk visual clone.
Signature: `render_inspect(conn, field)`. Two sections, both
deterministic and runnable without a fetched season:

**(a) Full signal stack, Plotly subplots sharing x-axis (weekly cadence):**

- Top panel: NDVI, NDRE, NDWI, LSWI lines from
  `get_season_readings(conn, field.field_id, index_name=<each>)`. Y-axis
  `[−0.2, 1.0]`. Overlay `PADDY_THRESHOLDS['NDVI']` healthy/stress/severe
  as horizontal dashed lines (colored green/amber/red).
- Middle panel: S1_VV, S1_VH in dB. Y-axis `[−25, −5]`.
- Bottom panel: S1_RVI. Y-axis `[0, 1]`.
- Shade phenology windows across all three panels using
  `plotly.graph_objects.layout.shape` with `xref="x"`, `yref="paper"`:
  - TRANSPLANT_WINDOW (blue, α=0.08)
  - Vegetative window = `transplant_date + VEGETATIVE_OFFSET_DAYS`
    (green, α=0.05); fall back to calendar Jul 20 – Aug 20 if no
    transplant event exists yet
  - Reproductive window = `transplant_date + REPRODUCTIVE_OFFSET_DAYS`
    (amber, α=0.08); fall back to Aug 15 – Oct 15
  - HARVEST_WINDOW (brown, α=0.08)
- Event markers from `get_paddy_events`: T / H / ! as text annotations
  anchored to the NDVI line at the event date, colored per
  `EVENT_MARKER` in `paddy_timeline.py` (reuse that dict).

**(b) Within-field NDVI band histogram, from the latest overlay PNG:**

Use PIL (already a dependency via folium → pillow) to classify pixels.
`evalscripts_paddy.imagery_paddy_ndvi_overlay` writes an RGBA PNG with
this color ramp (inspect that file for exact RGB values):

- α = 0: outside SCL validity → **skip**
- dark gray: NDVI < 0.0 (bare soil / water)
- red: 0.0 – 0.2
- orange: 0.2 – 0.4
- yellow: 0.4 – 0.6
- light green: 0.6 – 0.8
- dark green: 0.8 – 1.0

Algorithm: find the latest `ndvi_overlay` via
`list_overlays(conn, field.field_id)` filtered to `image_type ==
'ndvi_overlay'`; open PNG with `Image.open(rec.file_path).convert('RGBA')`;
iterate pixels (or numpy-vectorize — the overlays are ~200×200 so either
works); group buckets into **High (≥0.6)**, **Medium (0.4–0.6)**, **Low
(<0.4)** bands; render three `st.metric` cards showing hectares per band
(`field.area_hectares * band_count / valid_count`) plus a horizontal
stacked bar (`st.plotly_chart` or `st.progress` × 3).

Prefer numpy: `arr = np.asarray(img); mask = arr[..., 3] > 0`. Use
nearest-color matching against a 7-tuple lookup of the ramp RGBs.

### 3. Wire the new page in `dashboard/app.py`

```python
PAGES = ["Timeline map", "Inspect plot", "Fields"]
...
elif page == "Inspect plot":
    from dashboard.pages.inspect import render_inspect
    render_inspect(conn, field)
```

The sidebar "Active field" selectbox already drives `field` for this
page — no new state needed.

### 4. Deferred — layer once real season data is fetched

These need fetched `index_readings` + ground-truth observations, so
defer them until the user has run `scripts.fetch_paddy_kharif` for at
least one field:

- **(2) Stress-type inference** — map detected anomalies to rule
  buckets: `NDWI drop ∧ LSWI drop` → water stress; `NDRE drop ∧ NDVI
  stable` → nutrient; `VH drop sharp ∧ NDVI drop` → lodging / pest.
  Show as a single-line call-out on the Inspect page.
- **(4) Peer benchmark** — rank the active field's current NDVI
  against the median of other fields in the same village for the
  current week. Surface as "Δ vs MAUR median: +0.04 (4th of 11)".
- **(5) Triage ranking** — a simple sortable table on a new "Triage"
  page scoring every field `= 0.5·(1−NDVI_norm) + 0.3·event_severity
  + 0.2·days_since_last_visit`. Intended for the extension agent's
  morning planning.

### 5. Operational notes for the next session

- **Don't commit `.env`.** The user asked once and then
  retracted; git history is permanent. If asked again, push back.
- **Can't actually fetch data from this sandbox.** No Sentinel Hub
  creds, no outbound network, and a full-season pull for one field
  takes ~3–5 min wall time. Tell the user to run
  `python -m scripts.fetch_paddy_kharif --verbose` on their laptop.
- **Dropbox lock errors** are the #1 setup failure mode — see
  `Database quirks` above; tell the user to move the repo out before
  debugging anything else.
- **Feature branch** is `claude/paddy-field-monitor-W4KrU`. All
  commits should land there; don't push to `main`.
