import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FFL_DATABASE_PATH = os.environ.get(
    "FFL_DATABASE_PATH",
    "/tmp/ffl.db" if os.environ.get("VERCEL") else str(PROJECT_ROOT / "data" / "ffl.db"),
)
