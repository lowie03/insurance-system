import math

from insurance_core.payments import payment_options
from insurance_core.pricing import quote


def plan(options, name):
    return next(o for o in options if o["plan"] == name)


def test_large_lump_sum_switches_to_monthly(trader):
    premium, _ = quote("HCN", trader)                        # ₦29,600 > 20% of ₦112,000
    options, chosen = payment_options(premium, trader)
    assert chosen == "monthly"
    assert plan(options, "monthly")["payment_ngn"] == 2_590
    assert plan(options, "monthly")["total_ngn"] == 31_080   # includes 5% instalment loading
    assert not plan(options, "annual")["fits_cash_flow"]


def test_small_premium_stays_annual(trader):
    options, chosen = payment_options(15_000, trader)        # shop cover
    assert chosen == "annual"


def test_unaffordable_product_has_no_viable_plan(unemployed):
    _, chosen = payment_options(60_000, unemployed)
    assert chosen is None


def test_unknown_income_allows_every_plan(trader):
    no_income = {**trader, "monthly_income_ngn": math.nan}
    options, chosen = payment_options(500_000, no_income)
    assert chosen == "annual"
    assert all(o["fits_budget"] and o["fits_cash_flow"] for o in options)