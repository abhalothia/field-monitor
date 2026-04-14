"""Sentinel Hub evalscripts for vegetation indices and imagery.

Evalscripts are JavaScript code that runs server-side on Sentinel Hub.
Two categories:
  - Statistical: return numeric values for aggregation over polygons
  - Imagery: return RGB-encoded images for visualization
"""


def _scl_validity_check() -> str:
    """Common SCL cloud/shadow mask. Valid: vegetation(4), not-veg(5), water(6), unclassified(7)."""
    return "let isValid = (scl == 4 || scl == 5 || scl == 6 || scl == 7);"


# ---------------------------------------------------------------------------
# Statistical evalscripts (return float values for Statistical API)
# ---------------------------------------------------------------------------

def statistical_ndvi() -> str:
    return """//VERSION=3
function setup() {
  return {
    input: [{bands: ["B04", "B08", "SCL"]}],
    output: [{id: "ndvi", bands: 1, sampleType: "FLOAT32"},
             {id: "dataMask", bands: 1}]
  };
}
function evaluatePixel(sample) {
  let scl = sample.SCL;
  """ + _scl_validity_check() + """
  if (!isValid) return {ndvi: [0], dataMask: [0]};
  let val = (sample.B08 - sample.B04) / (sample.B08 + sample.B04 + 1e-10);
  return {ndvi: [val], dataMask: [1]};
}"""


def statistical_ndre() -> str:
    return """//VERSION=3
function setup() {
  return {
    input: [{bands: ["B05", "B08", "SCL"]}],
    output: [{id: "ndre", bands: 1, sampleType: "FLOAT32"},
             {id: "dataMask", bands: 1}]
  };
}
function evaluatePixel(sample) {
  let scl = sample.SCL;
  """ + _scl_validity_check() + """
  if (!isValid) return {ndre: [0], dataMask: [0]};
  let val = (sample.B08 - sample.B05) / (sample.B08 + sample.B05 + 1e-10);
  return {ndre: [val], dataMask: [1]};
}"""


def statistical_ndwi() -> str:
    return """//VERSION=3
function setup() {
  return {
    input: [{bands: ["B08", "B11", "SCL"]}],
    output: [{id: "ndwi", bands: 1, sampleType: "FLOAT32"},
             {id: "dataMask", bands: 1}]
  };
}
function evaluatePixel(sample) {
  let scl = sample.SCL;
  """ + _scl_validity_check() + """
  if (!isValid) return {ndwi: [0], dataMask: [0]};
  let val = (sample.B08 - sample.B11) / (sample.B08 + sample.B11 + 1e-10);
  return {ndwi: [val], dataMask: [1]};
}"""


def statistical_evi() -> str:
    return """//VERSION=3
function setup() {
  return {
    input: [{bands: ["B02", "B04", "B08", "SCL"]}],
    output: [{id: "evi", bands: 1, sampleType: "FLOAT32"},
             {id: "dataMask", bands: 1}]
  };
}
function evaluatePixel(sample) {
  let scl = sample.SCL;
  """ + _scl_validity_check() + """
  if (!isValid) return {evi: [0], dataMask: [0]};
  let val = 2.5 * ((sample.B08 - sample.B04) / (sample.B08 + 6*sample.B04 - 7.5*sample.B02 + 1));
  return {evi: [val], dataMask: [1]};
}"""


def statistical_savi() -> str:
    return """//VERSION=3
function setup() {
  return {
    input: [{bands: ["B04", "B08", "SCL"]}],
    output: [{id: "savi", bands: 1, sampleType: "FLOAT32"},
             {id: "dataMask", bands: 1}]
  };
}
function evaluatePixel(sample) {
  let scl = sample.SCL;
  """ + _scl_validity_check() + """
  if (!isValid) return {savi: [0], dataMask: [0]};
  let L = 0.428;
  let val = ((sample.B08 - sample.B04) / (sample.B08 + sample.B04 + L)) * (1.0 + L);
  return {savi: [val], dataMask: [1]};
}"""


def statistical_ndmi() -> str:
    return """//VERSION=3
function setup() {
  return {
    input: [{bands: ["B8A", "B11", "SCL"]}],
    output: [{id: "ndmi", bands: 1, sampleType: "FLOAT32"},
             {id: "dataMask", bands: 1}]
  };
}
function evaluatePixel(sample) {
  let scl = sample.SCL;
  """ + _scl_validity_check() + """
  if (!isValid) return {ndmi: [0], dataMask: [0]};
  let val = (sample.B8A - sample.B11) / (sample.B8A + sample.B11 + 1e-10);
  return {ndmi: [val], dataMask: [1]};
}"""


# ---------------------------------------------------------------------------
# Imagery evalscripts (return RGB images for Process API)
# ---------------------------------------------------------------------------

def imagery_true_color() -> str:
    return """//VERSION=3
function setup() {
  return {
    input: [{bands: ["B02", "B03", "B04"]}],
    output: {bands: 3, sampleType: "AUTO"}
  };
}
function evaluatePixel(sample) {
  return [3.5 * sample.B04, 3.5 * sample.B03, 3.5 * sample.B02];
}"""


def imagery_false_color() -> str:
    return """//VERSION=3
function setup() {
  return {
    input: [{bands: ["B03", "B04", "B08"]}],
    output: {bands: 3, sampleType: "AUTO"}
  };
}
function evaluatePixel(sample) {
  return [3.5 * sample.B08, 3.5 * sample.B04, 3.5 * sample.B03];
}"""


def imagery_ndvi_map() -> str:
    """Color-coded NDVI map: red(low) -> yellow -> green(high)."""
    return """//VERSION=3
function setup() {
  return {
    input: [{bands: ["B04", "B08", "SCL"]}],
    output: {bands: 3, sampleType: "AUTO"}
  };
}
function evaluatePixel(sample) {
  let scl = sample.SCL;
  if (scl == 3 || scl == 8 || scl == 9 || scl == 10) return [0.7, 0.7, 0.7];
  let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04 + 1e-10);
  if (ndvi < 0.0) return [0.05, 0.05, 0.05];
  if (ndvi < 0.2) return [0.75, 0.15, 0.15];
  if (ndvi < 0.4) return [0.9, 0.5, 0.15];
  if (ndvi < 0.6) return [0.95, 0.9, 0.2];
  if (ndvi < 0.8) return [0.4, 0.8, 0.2];
  return [0.1, 0.5, 0.1];
}"""


def imagery_ndwi_map() -> str:
    """Color-coded NDWI map: brown(dry) -> yellow -> blue(wet)."""
    return """//VERSION=3
function setup() {
  return {
    input: [{bands: ["B08", "B11", "SCL"]}],
    output: {bands: 3, sampleType: "AUTO"}
  };
}
function evaluatePixel(sample) {
  let scl = sample.SCL;
  if (scl == 3 || scl == 8 || scl == 9 || scl == 10) return [0.7, 0.7, 0.7];
  let ndwi = (sample.B08 - sample.B11) / (sample.B08 + sample.B11 + 1e-10);
  if (ndwi < -0.3) return [0.6, 0.3, 0.1];
  if (ndwi < -0.1) return [0.8, 0.6, 0.2];
  if (ndwi < 0.1) return [0.9, 0.9, 0.3];
  if (ndwi < 0.3) return [0.4, 0.7, 0.9];
  return [0.1, 0.3, 0.8];
}"""


# ---------------------------------------------------------------------------
# Registry for convenient lookup
# ---------------------------------------------------------------------------

STATISTICAL_EVALSCRIPTS: dict[str, callable] = {
    "NDVI": statistical_ndvi,
    "NDRE": statistical_ndre,
    "NDWI": statistical_ndwi,
    "EVI": statistical_evi,
    "SAVI": statistical_savi,
    "NDMI": statistical_ndmi,
}

IMAGERY_EVALSCRIPTS: dict[str, callable] = {
    "true_color": imagery_true_color,
    "false_color": imagery_false_color,
    "ndvi_map": imagery_ndvi_map,
    "ndwi_map": imagery_ndwi_map,
}
