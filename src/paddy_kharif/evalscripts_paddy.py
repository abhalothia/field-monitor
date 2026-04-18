"""Evalscripts for the paddy kharif offshoot.

All statistical evalscripts follow the same pattern as src.evalscripts: they
return a single FLOAT32 output plus dataMask, which the Sentinel Hub
Statistical API aggregates into mean/min/max/stdev over the polygon.

SAR evalscripts query the sentinel-1-grd collection and deliberately do NOT
use SCL masking (it's optical-only). Instead they run on the entire polygon
and rely on Sentinel Hub's server-side orbit/polarization filters for
consistency.
"""

from src.evalscripts import _scl_validity_check


# ---------------------------------------------------------------------------
# Optical (Sentinel-2 L2A)
# ---------------------------------------------------------------------------

def statistical_lswi() -> str:
    """LSWI = (B08 - B11) / (B08 + B11).

    Xiao et al. 2005/2006 use LSWI on MODIS bands to detect flooded paddy
    fields. On Sentinel-2 we use B08 (842 nm, NIR) and B11 (1610 nm, SWIR-1).
    Numerically similar to NDMI but defined with B08 rather than B8A for
    consistency with the Xiao formulation.
    """
    return """//VERSION=3
function setup() {
  return {
    input: [{bands: ["B08", "B11", "SCL"]}],
    output: [{id: "lswi", bands: 1, sampleType: "FLOAT32"},
             {id: "dataMask", bands: 1}]
  };
}
function evaluatePixel(sample) {
  let scl = sample.SCL;
  """ + _scl_validity_check() + """
  if (!isValid) return {lswi: [0], dataMask: [0]};
  let val = (sample.B08 - sample.B11) / (sample.B08 + sample.B11 + 1e-10);
  return {lswi: [val], dataMask: [1]};
}"""


def imagery_paddy_ndvi_overlay() -> str:
    """RGBA NDVI overlay for Folium ImageOverlay.

    Transparent (alpha=0) outside valid SCL pixels so the overlay can sit on
    top of any base map without obscuring it with grey where clouds are. The
    colour ramp matches src.evalscripts.imagery_ndvi_map but adds the alpha
    channel.
    """
    return """//VERSION=3
function setup() {
  return {
    input: [{bands: ["B04", "B08", "SCL"]}],
    output: {bands: 4, sampleType: "AUTO"}
  };
}
function evaluatePixel(sample) {
  let scl = sample.SCL;
  // Invalid (clouds, shadows, nodata) -> transparent
  if (scl == 0 || scl == 1 || scl == 2 || scl == 3
      || scl == 8 || scl == 9 || scl == 10 || scl == 11) {
    return [0, 0, 0, 0];
  }
  let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04 + 1e-10);
  let a = 1.0;
  if (ndvi < 0.0)  return [0.05, 0.05, 0.05, a];
  if (ndvi < 0.2)  return [0.75, 0.15, 0.15, a];
  if (ndvi < 0.4)  return [0.90, 0.50, 0.15, a];
  if (ndvi < 0.6)  return [0.95, 0.90, 0.20, a];
  if (ndvi < 0.8)  return [0.40, 0.80, 0.20, a];
  return [0.10, 0.50, 0.10, a];
}"""


# ---------------------------------------------------------------------------
# Sentinel-1 SAR
# ---------------------------------------------------------------------------

def statistical_s1_vvvh_rvi() -> str:
    """Return VV and VH in dB plus RVI in one request.

    The Statistical API can return multiple named FLOAT32 outputs per pixel;
    this keeps three weekly SAR signals in a single round-trip. GAMMA0 is
    computed server-side via the `backCoeff` parameter passed in the request
    body (see sar_client.py), so we just read `sample.VV` and `sample.VH` here.
    RVI = 4*VH / (VV+VH) using linear-power values, then the VV/VH themselves
    are reported in dB for legibility.
    """
    return """//VERSION=3
function setup() {
  return {
    input: [{bands: ["VV", "VH"]}],
    output: [
      {id: "vv_db",  bands: 1, sampleType: "FLOAT32"},
      {id: "vh_db",  bands: 1, sampleType: "FLOAT32"},
      {id: "rvi",    bands: 1, sampleType: "FLOAT32"},
      {id: "dataMask", bands: 1}
    ]
  };
}
function evaluatePixel(sample) {
  let vv = sample.VV;
  let vh = sample.VH;
  // Reject invalid or extreme values
  if (vv <= 0 || vh <= 0 || !isFinite(vv) || !isFinite(vh)) {
    return {vv_db: [0], vh_db: [0], rvi: [0], dataMask: [0]};
  }
  let rvi = (4.0 * vh) / (vv + vh + 1e-10);
  let vv_db = 10.0 * Math.log(vv) / Math.LN10;
  let vh_db = 10.0 * Math.log(vh) / Math.LN10;
  return {
    vv_db: [vv_db],
    vh_db: [vh_db],
    rvi:   [rvi],
    dataMask: [1]
  };
}"""


def imagery_paddy_rvi_overlay() -> str:
    """RGBA RVI overlay. Used as the cloud-independent fallback tile when S2
    has no cloud-free pixels for a given slider week.

    RVI in {0..1}: 0 ~= bare/flooded, 0.65-0.75 ~= peak rice canopy.
    Colour ramp: blue-low -> green-high, with transparent at extreme edges.
    """
    return """//VERSION=3
function setup() {
  return {
    input: [{bands: ["VV", "VH"]}],
    output: {bands: 4, sampleType: "AUTO"}
  };
}
function evaluatePixel(sample) {
  let vv = sample.VV;
  let vh = sample.VH;
  if (vv <= 0 || vh <= 0 || !isFinite(vv) || !isFinite(vh)) {
    return [0, 0, 0, 0];
  }
  let rvi = (4.0 * vh) / (vv + vh + 1e-10);
  let a = 1.0;
  if (rvi < 0.15) return [0.20, 0.35, 0.65, a];   // bare/flooded - blue
  if (rvi < 0.30) return [0.35, 0.55, 0.75, a];
  if (rvi < 0.45) return [0.55, 0.75, 0.55, a];
  if (rvi < 0.60) return [0.40, 0.80, 0.35, a];
  if (rvi < 0.75) return [0.20, 0.65, 0.25, a];
  return [0.10, 0.50, 0.15, a];                   // peak canopy - deep green
}"""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

PADDY_OPTICAL_STATISTICAL: dict[str, callable] = {
    "LSWI": statistical_lswi,
}

PADDY_SAR_STATISTICAL = statistical_s1_vvvh_rvi

PADDY_IMAGERY_EVALSCRIPTS: dict[str, callable] = {
    "ndvi_overlay": imagery_paddy_ndvi_overlay,
    "rvi_overlay": imagery_paddy_rvi_overlay,
}
