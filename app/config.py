from pathlib import Path
import os
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'copilot.db'}")
MODEL_PATH = Path(os.getenv("MODEL_PATH", str(ROOT / "data" / "win_probability_model.joblib")))
if not MODEL_PATH.is_absolute():
    MODEL_PATH = ROOT / MODEL_PATH
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
