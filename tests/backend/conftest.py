"""Fixtures available to every backend test automatically (pytest finds conftest.py by itself)."""
import pandas as pd
import pytest

from tests.backend.helpers import DATA_PATH, make_client


@pytest.fixture
def client(tmp_path):
    with make_client(tmp_path) as c:          # "with" runs the startup (model load, tables)
        yield c


@pytest.fixture(scope="session")
def customers():
    if not DATA_PATH.exists():
        pytest.skip(f"synthetic data not found at {DATA_PATH}")
    return pd.read_csv(DATA_PATH, dtype={"phone": str}).set_index("customer_id")