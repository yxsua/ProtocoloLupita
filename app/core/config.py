from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
SCENARIOS_DIR = DATA_DIR / "scenarios"
DATABASE_PATH = DATA_DIR / "prototipo.sqlite3"
APP_TITLE = "Mosca Estéril | Protocolo Lupita"

