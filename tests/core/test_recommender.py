"""End-to-end checks of recommend() on real synthetic customers.

These need the trained model and the synthetic CSV; if either is missing the tests are
SKIPPED (not failed), with a message saying what to run.
"""
import pandas as pd
import pytest

from insurance_core.features import ProfileEncoder
from insurance_core.model_io import load_bundle
from insurance_core.recommender import REFER_SUBSIDY, REFER_WEAK_MATCH, recommend
from insurance_core.settings import MODEL_PATH, PROJECT_ROOT

DATA_PATH = PROJECT_ROOT / "data/synthetic/synthetic_ng_customers.csv"


@pytest.fixture(scope="module")
def bundle():
    if not MODEL_PATH.exists():
        pytest.skip("no trained model: run python training/train_recommender.py")
    return load_bundle(MODEL_PATH)


@pytest.fixture(scope="module")
def customers():
    if not DATA_PATH.exists():
        pytest.skip(f"synthetic data not found at {DATA_PATH}")
    return pd.read_csv(DATA_PATH, dtype={"phone": str}).set_index("customer_id")


def profile(customers, customer_id):
    return {"customer_id": customer_id, **customers.loc[customer_id].to_dict()}


def test_encoder_has_a_permanent_import_path(bundle):
    # The pickle fix: the saved encoder must point at the package, not at __main__
    assert type(bundle["encoder"]) is ProfileEncoder
    assert type(bundle["encoder"]).__module__ == "insurance_core.features"


def test_unemployed_gets_subsidy_referral(bundle, customers):
    result = recommend(profile(customers, "NG-SYN-00008"), bundle)
    assert result["recommendations"] == []
    assert result["refer_reason"] == REFER_SUBSIDY
    kinds = {e["product"]: e["kind"] for e in result["excluded"]}
    assert kinds["HIN"] == "affordability"
    assert kinds["MTP"] == "eligibility"


def test_trader_matches_colab(bundle, customers):
    result = recommend(profile(customers, "NG-SYN-00021"), bundle)
    recs = result["recommendations"]
    assert [r["product"] for r in recs] == ["HCN", "HMC", "SHP"]
    assert [r["match_score"] for r in recs] == pytest.approx([0.364, 0.315, 0.25], abs=0.02)
    assert [r["suggested_plan"] for r in recs] == ["monthly", "monthly", "annual"]
    assert result["refer_to_broker"] is False


def test_civil_servant_with_hmo_is_referred(bundle, customers):
    result = recommend(profile(customers, "NG-SYN-00012"), bundle)
    assert result["refer_reason"] == REFER_WEAK_MATCH
    assert "you already have an employer HMO" in result["recommendations"][0]["notes"]


def test_owned_products_are_never_recommended(bundle, customers):
    trader = {**profile(customers, "NG-SYN-00021"), "HCN": 1}
    products = [r["product"] for r in recommend(trader, bundle)["recommendations"]]
    assert "HCN" not in products


def test_result_records_versions_for_the_audit_log(bundle, customers):
    result = recommend(profile(customers, "NG-SYN-00021"), bundle)
    assert result["model_version"] == "ng_recommender_v1"
    assert result["config_versions"]["pricing"] == "pricing-v3"


def test_works_with_api_style_missing_values(bundle, customers):
    # From the API, missing fields arrive as None rather than NaN
    api_profile = {k: (None if pd.isna(v) else v) for k, v in profile(customers, "NG-SYN-00021").items()}
    assert [r["product"] for r in recommend(api_profile, bundle)["recommendations"]] == ["HCN", "HMC", "SHP"]