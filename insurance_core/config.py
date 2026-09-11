"""Loads the YAML/CSV files in config/. Each file is read once and cached."""
from functools import lru_cache

import yaml

from insurance_core.settings import CONFIG_DIR

CONFIG_FILES = ["eligibility_rules", "suitability_rules", "pricing", "payment_plans", "recommender"]


@lru_cache(maxsize=None)
def load(name: str) -> dict:
    """load("pricing") -> contents of config/pricing.yaml as a dict."""
    with open(CONFIG_DIR / f"{name}.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def versions() -> dict:
    """Version of every config file in force right now. Written to the audit log with each decision."""
    return {name: load(name)["version"] for name in CONFIG_FILES}


def reload() -> None:
    """Forget cached files, e.g. after editing a YAML file in a running session."""
    load.cache_clear()