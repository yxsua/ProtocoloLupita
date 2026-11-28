import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.getenv("APP_DATA_DIR", PROJECT_ROOT / "data")).resolve()
SCENARIOS_DIR = PROJECT_ROOT / "data" / "scenarios"
DATABASE_PATH = DATA_DIR / "prototipo.sqlite3"
APP_TITLE = "Protocolo Lupita"

