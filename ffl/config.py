import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FFL_DATABASE_PATH = os.environ.get(
    "FFL_DATABASE_PATH",
    "/tmp/ffl.db" if os.environ.get("VERCEL") else str(PROJECT_ROOT / "data" / "ffl.db"),
)

# These are configuration handles only.  The browser never sees either value;
# the API configuration is parsed by the TrackOlap server-side adapter only
# when the lane is explicitly enabled.
FFL_TRACKOLAP_ENABLED = os.environ.get("FFL_TRACKOLAP_ENABLED", "").strip().lower() == "true"
FFL_TRACKOLAP_API_CONFIG_JSON = os.environ.get("FFL_TRACKOLAP_API_CONFIG_JSON")
FFL_TRACKOLAP_API_TOKEN_REFERENCE = os.environ.get(
    "FFL_TRACKOLAP_API_TOKEN_REFERENCE", "env://FFL_TRACKOLAP_API_TOKEN"
)
