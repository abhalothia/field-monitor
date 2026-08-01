import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FFL_DATABASE_PATH = os.environ.get(
    "FFL_DATABASE_PATH", str(PROJECT_ROOT / "data" / "ffl.db")
)
