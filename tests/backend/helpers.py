"""Plain helper functions shared by the backend tests."""
import json

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.schemas import ProfileIn
from backend.app.settings import Settings
from insurance_core.settings import MODEL_PATH, PROJECT_ROOT

DATA_PATH = PROJECT_ROOT / "data/synthetic/synthetic_ng_customers.csv"
TEST_KEY = "t" * 64
BROKER_TEST_TOKEN = "b" * 40
MODEL_PRODUCTS = ["MTP", "MCP", "HIN", "HFM", "TRV", "HCN", "SHP"]


def make_client(tmp_path, **overrides) -> TestClient:
    """A fresh app with its own temporary database. Certificates live in the database itself, not
    on disk, so no PDF folder is needed. Simulated payments unless overridden."""
    if not MODEL_PATH.exists():
        pytest.skip("no trained model: run python training/train_recommender.py")
    settings = Settings(**{"_env_file": None, "policy_signing_key": TEST_KEY, "broker_api_token": BROKER_TEST_TOKEN,
                           "database_url": f"sqlite:///{tmp_path / 'test.db'}",
                           "payment_mode": "simulated", **overrides})
    return TestClient(create_app(settings))


def quote_body(customers, customer_id) -> dict:
    """A synthetic customer as the frontend would send them."""
    row = json.loads(customers.loc[customer_id].to_json())            # native types, NaN -> None
    profile = {k: row[k] for k in ProfileIn.model_fields if k in row}
    profile["owned_products"] = [p for p in MODEL_PRODUCTS if row[p] == 1]
    return {"full_name": row["full_name"], "profile": profile}