"""validate_basket() against real recommend() output for synthetic customers, plus two small
hand-built result fixtures for edge cases (a compulsory-only refusal, an impossible cash-flow
squeeze) that don't occur naturally anywhere in the synthetic dataset."""
import pandas as pd
import pytest

from insurance_core.basket import BasketError, validate_basket
from insurance_core.model_io import load_bundle
from insurance_core.recommender import recommend
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


def result_for(customers, bundle, customer_id):
    return profile(customers, customer_id), recommend(profile(customers, customer_id), bundle, top_k=100)


def lines_by_product(basket):
    return {l["product"]: l for l in basket["lines"]}


# --- customers used below, and why ---
# NG-SYN-00021: the trader from the thesis write-up. income 112,000/month; recommended HCN, HMC, SHP
#   (no group conflicts between them) -> good for the happy path.
# NG-SYN-00224: income 845,000/month, owns a 2018 car, recommended MTP+MCP (motor group) AND HFM+HIN
#   (health group) together with HCN -> covers both mutually-exclusive groups plus a cash-flow switch.
# NG-SYN-00833: income 98,000/month, recommended HMC+HCN+MCP whose combined suggested-plan cost is
#   123,580 against a 117,600 budget -> a real "over budget" basket with no group conflict.
# NG-SYN-00119: income unknown (NaN) -> nothing to check affordability against.

TRADER = "NG-SYN-00021"
MOTORIST = "NG-SYN-00224"
LOW_INCOME = "NG-SYN-00833"
UNKNOWN_INCOME = "NG-SYN-00119"


def test_happy_path_combines_pricing_across_the_basket(customers, bundle):
    profile_, result = result_for(customers, bundle, TRADER)
    items = [{"product_code": "HCN"}, {"product_code": "HMC"}, {"product_code": "SHP"}]
    basket = validate_basket(result, items, profile_)

    lines = lines_by_product(basket)
    assert set(lines) == {"HCN", "HMC", "SHP"}
    assert (lines["HCN"]["payment_plan"], lines["HMC"]["payment_plan"], lines["SHP"]["payment_plan"]) == \
           ("monthly", "monthly", "annual")                        # each line's own suggested plan, unchanged
    assert basket["first_payment_ngn"] == pytest.approx(2_590 + 4_810 + 15_000)    # SHP is annual: one payment
    assert basket["total_annual_ngn"] == pytest.approx(31_080 + 57_750 + 15_000)
    assert basket["budget_ngn"] == pytest.approx(0.10 * 112_000 * 12)
    assert basket["budget_remaining_ngn"] == pytest.approx(basket["budget_ngn"] - basket["total_annual_ngn"])
    assert basket["notes"] == []


@pytest.mark.parametrize("codes", [["HIN", "HFM"], ["MTP", "MCP"]])
def test_group_conflict_is_refused(customers, bundle, codes):
    profile_, result = result_for(customers, bundle, MOTORIST)
    items = [{"product_code": c} for c in codes]
    with pytest.raises(BasketError, match="conflicts with"):
        validate_basket(result, items, profile_)


def test_over_total_budget_is_refused(customers, bundle):
    profile_, result = result_for(customers, bundle, LOW_INCOME)
    items = [{"product_code": "HMC"}, {"product_code": "HCN"}, {"product_code": "MCP"}]
    with pytest.raises(BasketError, match="combined cost is above"):
        validate_basket(result, items, profile_)


def test_already_committed_pushes_it_over_budget(customers, bundle):
    profile_, result = result_for(customers, bundle, TRADER)      # budget = 134,400; SHP alone = 15,000
    items = [{"product_code": "SHP"}]
    validate_basket(result, items, profile_)                     # fits with nothing committed yet
    with pytest.raises(BasketError, match="combined cost is above"):
        validate_basket(result, items, profile_, already_committed_ngn=130_000)


def test_cash_flow_squeeze_switches_the_largest_annual_line_to_monthly(customers, bundle):
    profile_, result = result_for(customers, bundle, MOTORIST)    # cash-flow limit = 169,000/month
    # All three suggested annual: HCN 140,500 + HFM 100,000 + MCP 41,000 -> 281,500 first payment,
    # which is over the limit even though the combined ANNUAL total (281,500) is well inside budget.
    items = [{"product_code": "HCN"}, {"product_code": "HFM"}, {"product_code": "MCP"}]
    basket = validate_basket(result, items, profile_)

    lines = lines_by_product(basket)
    assert lines["HCN"]["payment_plan"] == "monthly"              # the largest annual line: switched first
    assert lines["HFM"]["payment_plan"] == "annual"                # switching HCN alone was already enough
    assert lines["MCP"]["payment_plan"] == "annual"
    assert any("switched to monthly" in n for n in lines["HCN"]["notes"])
    assert basket["first_payment_ngn"] == pytest.approx(12_290 + 100_000 + 41_000)
    assert basket["first_payment_ngn"] <= 0.20 * 845_000


def test_unknown_income_skips_affordability_checks(customers, bundle):
    profile_, result = result_for(customers, bundle, UNKNOWN_INCOME)
    items = [{"product_code": "MCP"}, {"product_code": "HFM"}]     # different groups: no conflict
    basket = validate_basket(result, items, profile_)

    assert basket["budget_ngn"] is None
    assert basket["budget_remaining_ngn"] is None
    assert "income not provided" in basket["notes"][0]
    lines = lines_by_product(basket)
    assert (lines["MCP"]["payment_plan"], lines["HFM"]["payment_plan"]) == ("annual", "annual")


def test_product_not_offered_reuses_the_exclusion_reason(customers, bundle):
    profile_, result = result_for(customers, bundle, TRADER)       # trader owns no vehicle: MTP is excluded
    with pytest.raises(BasketError, match="requires a vehicle"):
        validate_basket(result, [{"product_code": "MTP"}], profile_)


def test_empty_basket_is_refused(customers, bundle):
    profile_, result = result_for(customers, bundle, TRADER)
    with pytest.raises(BasketError, match="empty"):
        validate_basket(result, [], profile_)


def test_duplicate_product_is_refused(customers, bundle):
    profile_, result = result_for(customers, bundle, TRADER)
    items = [{"product_code": "HCN"}, {"product_code": "HCN"}]
    with pytest.raises(BasketError, match="more than once"):
        validate_basket(result, items, profile_)


def test_too_many_items_is_refused():
    # max_items is a basket-shape rule, so it doesn't need real pricing data to test.
    fake_result = {"recommendations": [], "excluded": []}
    items = [{"product_code": f"P{i}"} for i in range(6)]
    with pytest.raises(BasketError, match="at most 5"):
        validate_basket(fake_result, items, {})


# --- hand-built edge cases: neither occurs anywhere in the synthetic dataset, because a 10%-of-
# income annual budget is always far tighter than a 20%-of-MONTHLY-income cash-flow limit for any
# realistic single product. They're still real rules that need a direct test.

def _option(plan, payments, payment_ngn, total_ngn, fits_budget=True, fits_cash_flow=True):
    return {"plan": plan, "payments": payments, "payment_ngn": payment_ngn, "total_ngn": total_ngn,
           "fits_budget": fits_budget, "fits_cash_flow": fits_cash_flow}


def test_compulsory_only_basket_is_never_refused_for_cost():
    # A tiny income where even MTP's premium alone is above the 10%-of-income basket budget.
    profile_ = {"monthly_income_ngn": 1_000.0}                     # budget = 10%*12*1,000 = 1,200
    result = {"recommendations": [{
        "product": "MTP", "premium_ngn": 15_000.0, "breakdown": [("NAICOM tariff", 15_000.0)],
        "suggested_plan": "annual", "notes": [],
        "payment_options": [_option("annual", 1, 15_000.0, 15_000.0), _option("monthly", 12, 1_310.0, 15_750.0)],
    }], "excluded": []}
    basket = validate_basket(result, [{"product_code": "MTP"}], profile_)
    assert basket["total_annual_ngn"] == 15_000.0
    assert basket["budget_remaining_ngn"] < 0                      # informational: they ARE over, just not refused


def test_cash_flow_impossible_even_after_switching_everything_to_monthly():
    # Two products, each individually just inside its own cash-flow limit on annual (so each is
    # offered as "annual" on its own), but together their first payments blow the combined limit,
    # and monthly doesn't fit either product's cash flow on its own so there's nothing to switch to.
    profile_ = {"monthly_income_ngn": 50_000.0}                    # cash-flow limit = 20%*50,000 = 10,000
    def product(code, premium):
        return {"product": code, "premium_ngn": premium, "breakdown": [("premium", premium)],
                "suggested_plan": "annual", "notes": [],
                "payment_options": [_option("annual", 1, premium, premium, fits_cash_flow=True),
                                    _option("monthly", 12, premium / 12 * 1.05, premium * 1.05,
                                            fits_cash_flow=False)]}
    result = {"recommendations": [product("HIN", 8_000.0), product("TRV", 7_000.0)], "excluded": []}
    with pytest.raises(BasketError, match="monthly budget"):
        validate_basket(result, [{"product_code": "HIN"}, {"product_code": "TRV"}], profile_)
