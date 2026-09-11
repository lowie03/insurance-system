import math

from insurance_core.rules import apply_suitability, eligibility_failure


def test_no_vehicle_means_no_motor_cover(trader):
    assert eligibility_failure("MTP", trader) == "requires a vehicle"
    assert eligibility_failure("MCP", trader) == "requires a vehicle"   # first failing rule only


def test_old_vehicle_blocks_comprehensive_but_not_third_party(bus_owner):
    old_bus = {**bus_owner, "vehicle_year": 2005.0}
    assert eligibility_failure("MTP", old_bus) is None
    assert "2008 or later" in eligibility_failure("MCP", old_bus)


def test_family_cover_needs_dependents(unemployed, trader):
    assert eligibility_failure("HFM", unemployed) == "family cover needs at least one dependent"
    assert eligibility_failure("HFM", trader) is None


def test_missing_value_never_passes_a_rule(bus_owner):
    unknown_year = {**bus_owner, "vehicle_year": math.nan}      # pandas-style missing
    assert eligibility_failure("MCP", unknown_year) is not None
    unknown_year = {**bus_owner, "vehicle_year": None}          # API-style missing
    assert eligibility_failure("MCP", unknown_year) is not None


def test_employer_hmo_reduces_health_scores(trader):
    with_hmo = {**trader, "employer_hmo": True}
    for product in ["HIN", "HFM", "HMC"]:
        score, notes = apply_suitability(product, with_hmo, 0.5)
        assert score == 0.15
        assert notes == ["you already have an employer HMO"]
    score, notes = apply_suitability("HCN", with_hmo, 0.5)
    assert (score, notes) == (0.5, [])