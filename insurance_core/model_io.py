"""Saving and loading the model together with everything needed to use it correctly."""
from datetime import datetime, timezone
from importlib.metadata import version as pkg_version
from pathlib import Path

import joblib

REQUIRED_KEYS = {"model", "encoder", "products", "model_version"}


def save_bundle(path, model, encoder, products, model_version, metrics=None, data_info=None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    bundle = {
        "model": model,
        "encoder": encoder,
        "products": list(products),
        "model_version": model_version,
        "metrics": metrics or {},
        "data_info": data_info or {},
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        # A saved model is tied to the library versions that created it; record them.
        "library_versions": {lib: pkg_version(lib) for lib in ["lightgbm", "scikit-learn", "pandas", "numpy"]},
    }
    joblib.dump(bundle, path)
    return path


def load_bundle(path) -> dict:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"No model at {path}. Run: python training/train_recommender.py")
    bundle = joblib.load(path)
    missing = REQUIRED_KEYS - set(bundle)
    if missing:
        raise ValueError(f"Model bundle at {path} is missing {sorted(missing)}")
    return bundle