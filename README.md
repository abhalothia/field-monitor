# Field Monitor

Satellite-based pest, disease, and crop stress monitoring tool for agricultural fields. Uses Sentinel-2 imagery via Sentinel Hub to track vegetation health indices over time, detect anomalies, and score risk.

## Setup

```bash
cd field-monitor
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Configure credentials

Copy `.env.example` to `.env` and fill in your Sentinel Hub credentials:

```bash
cp .env.example .env
```

The tool supports two endpoints:

- **Sentinel Hub** (default): Register at [sentinel-hub.com](https://www.sentinel-hub.com/)
- **Copernicus Data Space (CDSE)** (free): Register at [dataspace.copernicus.eu](https://dataspace.copernicus.eu/), create OAuth credentials in the dashboard, and set `SENTINEL_HUB_ENDPOINT=cdse` in `.env`

### Initialize the database

```bash
python scripts/setup_db.py
```

This parses the KML file, extracts the field polygon, and registers it in SQLite.

## Usage

### Fetch satellite data

```bash
# Fetch last 90 days of data
python scripts/fetch_data.py --lookback 90

# Verbose output
python scripts/fetch_data.py --lookback 180 -v
```

### Launch the dashboard

```bash
streamlit run dashboard/app.py
```

The dashboard opens at `http://localhost:8501` with five pages:

- **Overview** -- Map with field overlay, health score gauge, latest index values, recent alerts
- **Time series** -- Interactive charts for each vegetation index with threshold lines and anomaly markers
- **Imagery** -- Satellite images (true color, false color, NDVI map, NDWI map) with date comparison
- **Alerts** -- Filterable anomaly alert table with acknowledge and CSV export
- **Observations** -- Log ground-truth pest/disease observations to calibrate the risk model

You can also click "Fetch latest data" in the sidebar to pull new satellite data directly from the dashboard.

## Architecture

```
KML file --> parse polygon --> GeoJSON
                                  |
                OAuth2 token  <---+--> Sentinel Hub Statistical API (6 indices)
                                  +--> Sentinel Hub Process API (satellite images)
                                  v
                         anomaly detection + risk scoring
                                  |
                               SQLite
                                  |
                         Streamlit dashboard
```

### Vegetation indices monitored

| Index | What it detects |
|-------|----------------|
| NDVI  | General vegetation health and chlorophyll density |
| NDRE  | Nitrogen/chlorophyll stress, early disease indicator |
| NDWI  | Canopy water content and drought stress |
| EVI   | Canopy structure (corrected for atmosphere/soil) |
| SAVI  | Vegetation health with soil brightness correction |
| NDMI  | Leaf moisture content and irrigation effectiveness |

### Anomaly detection

Three complementary methods run on each index time series:

1. **Rolling baseline deviation** -- z-score against last 6 readings; flags at 2-sigma drops
2. **Absolute threshold breach** -- per-index stress/severe thresholds from agronomic literature
3. **Trend decline** -- linear regression over last 10 readings; flags if projected to cross stress threshold within 14 days

### Risk scoring

Four categories (pest, disease, water stress, nutrient stress), each a weighted combination of index stress scores. Overall risk = max of the four categories. Ground-truth observations boost the relevant category.

## Testing

```bash
pytest tests/ -v
```

## Field details

- **Name**: Untitled polygon
- **Location**: 28.09N, 77.81E (near Delhi/NCR)
- **Area**: 0.38 hectares (~38 pixels at Sentinel-2's 10m resolution)
