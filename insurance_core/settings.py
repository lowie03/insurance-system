"""Where things live. Every path can be overridden with an environment variable."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

CONFIG_DIR = Path(os.environ.get("INSURANCE_CONFIG_DIR", PROJECT_ROOT / "config"))
MODEL_PATH = Path(os.environ.get("MODEL_PATH", PROJECT_ROOT / "artifacts" / "models" / "ng_recommender_v1.joblib"))