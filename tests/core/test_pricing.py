import pytest

from insurance_core.pricing import annual_budget, is_compulsory, quote


@pytest.mark.parametrize("vehicle, expected", [
    ("Saloon Car", 15_000), ("SUV", 15_000), ("Bus", 20_000), ("Tricycle", 5_000), ("Motorcycle", 3_000),
])
def test_motor_third_party_follows_naicom_tariff(bus_owner, vehicle, expected):
    premium, _ = quote("MTP", {**bus_owner, "vehicle_type": vehicle})
    assert premium == expected


def test_comprehensive_is_five_percent_of_vehicle_value(bus_owner):
    premium, _ = quote("MCP", bus_owner)
    assert premium == 696_500          # 5% of ₦13,930,000


def test_trader_prices_match_colab(trader):
    assert quote("HIN", trader)[0] == 84_000       # 60,000 x 1.4 (age 52)
    assert quote("HFM", trader)[0] == 196_000      # (60,000 + 2 x 40,000) x 1.4
    premium, breakdown = quote("HCN", trader)
    assert premium == 29_600
    assert breakdown == [("contents est. ₦672,000 x 0.5%", 3_400.0),
                         ("building ₦17,490,000 x 0.15%", 29_600.0)]
    premium, breakdown = quote("SHP", trader)
    assert premium == 15_000
    assert breakdown[-1] == ("minimum premium applied", 15_000.0)


def test_smoker_loading(trader):
    assert quote("HIN", {**trader, "smoker": True})[0] == 105_000   # 84,000 x 1.25


@pytest.mark.parametrize("marital, dependents, expected", [
    ("Single", 0, 15_000),     # 1 person: individual rate
    ("Married", 0, 30_000),    # 2 people: 2 x 15,000 is cheaper than the family plan
    ("Married", 2, 55_000),    # 4 people: family-of-4 plan
    ("Married", 4, 80_000),    # 6 people: family-of-6 plan
    ("Married", 6, 100_000),   # 8 people: 80,000 + 2 x 10,000
])
def test_micro_health_charges_cheapest_valid_option(trader, marital, dependents, expected):
    premium, _ = quote("HMC", {**trader, "marital_status": marital, "dependents": dependents})
    assert premium == expected


def test_budget_is_five_percent_of_yearly_income(trader, unemployed):
    assert annual_budget(trader) == pytest.approx(67_200)
    assert annual_budget(unemployed) == pytest.approx(3_000)


def test_only_third_party_motor_is_compulsory():
    assert is_compulsory("MTP")
    assert not is_compulsory("MCP")


def test_unknown_product_raises(trader):
    with pytest.raises(KeyError):
        quote("XYZ", trader)