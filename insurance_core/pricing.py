"""Premium calculation: base premium x rating factors, driven by config/pricing.yaml.

Every pricing function returns (annual premium, breakdown), where breakdown is a list of
(step description, running total) so the customer can see how the price was built.
"""
from insurance_core import config
from insurance_core.profile import get, household_size, monthly_income


def _cfg(product: str) -> dict:
    return config.load("pricing")["products"][product]


def _age_factor(age: int) -> float:
    for low, high, factor in config.load("pricing")["health_age_bands"]["bands"]:
        if low <= age <= high:
            return factor
    raise ValueError(f"no health age band covers age {age}")


def _motor_third_party(p):
    vehicle = p["vehicle_type"]
    premium = _cfg("MTP")["tariff"][vehicle]
    return premium, [(f"NAICOM tariff for {vehicle}", premium)]


def _motor_comprehensive(p):
    value = p["vehicle_value_ngn"]
    premium = _cfg("MCP")["min_rate"] * value
    return premium, [(f"5% of vehicle value ₦{value:,.0f}", premium)]


def _health(product, p):
    cfg = _cfg(product)
    if product == "HIN":
        premium = cfg["base"]
        steps = [("base premium", premium)]
    else:
        deps = min(int(get(p, "dependents", 0)), cfg["max_dependents"])
        premium = cfg["principal"] + deps * cfg["per_dependent"]
        steps = [(f"principal + {deps} dependent(s)", premium)]
    factor = _age_factor(p["age"])
    premium *= factor
    steps.append((f"age factor x{factor}", premium))
    if get(p, "smoker", False):
        premium *= 1 + cfg["smoker_loading"]
        steps.append((f"smoker loading +{cfg['smoker_loading']:.0%}", premium))
    return premium, steps


def _travel(p):
    cfg = _cfg("TRV")
    trips = max(int(get(p, "foreign_trips_per_year", 0)), 1)
    premium = cfg["per_trip"] * trips
    steps = [(f"{trips} trip(s) x ₦{cfg['per_trip']:,}", premium)]
    if p["age"] >= cfg["senior_age"]:
        premium *= 1 + cfg["senior_loading"]
        steps.append((f"age {cfg['senior_age']}+ loading +{cfg['senior_loading']:.0%}", premium))
    return premium, steps


def _home_contents(p):
    cfg = _cfg("HCN")
    contents = cfg["contents_months_income"] * monthly_income(p)
    premium = cfg["contents_rate"] * contents
    steps = [(f"contents est. ₦{contents:,.0f} x {cfg['contents_rate']:.1%}", premium)]
    building_value = get(p, "property_value_ngn")
    if p.get("home_status") == "Owner" and building_value is not None:
        premium += cfg["building_rate"] * building_value
        steps.append((f"building ₦{building_value:,.0f} x {cfg['building_rate']:.2%}", premium))
    if premium < cfg["minimum"]:
        premium = cfg["minimum"]
        steps.append(("minimum premium applied", premium))
    return premium, steps


def _shop(p):
    cfg = _cfg("SHP")
    stock = cfg["stock_months_income"] * monthly_income(p)
    premium = cfg["rate"] * stock
    steps = [(f"stock est. ₦{stock:,.0f} x {cfg['rate']:.0%}", premium)]
    if premium < cfg["minimum"]:
        premium = cfg["minimum"]
        steps.append(("minimum premium applied", premium))
    return premium, steps


def _micro_health(p):
    cfg = _cfg("HMC")
    size = household_size(p)
    per_head = size * cfg["individual"]
    if size <= 4:
        family = cfg["family_4"]
    elif size <= 6:
        family = cfg["family_6"]
    else:
        family = cfg["family_6"] + (size - 6) * cfg["extra_dependent"]
    premium = min(per_head, family)                  # always charge the cheaper valid option
    how = "individual rate per person" if premium == per_head else "family plan rate"
    return premium, [(f"{size} person(s), {how}", premium)]


# Dispatch table: product code -> pricing function
_PRICERS = {
    "MTP": _motor_third_party,
    "MCP": _motor_comprehensive,
    "HIN": lambda p: _health("HIN", p),
    "HFM": lambda p: _health("HFM", p),
    "TRV": _travel,
    "HCN": _home_contents,
    "SHP": _shop,
    "HMC": _micro_health,
}


def quote(product: str, profile: dict):
    """Annual premium (rounded to the nearest ₦100) and its breakdown."""
    if product not in _PRICERS:
        raise KeyError(f"no pricing defined for product {product!r}")
    premium, steps = _PRICERS[product](profile)
    return float(round(premium, -2)), [(step, float(round(amount, -2))) for step, amount in steps]


def annual_budget(profile: dict) -> float:
    """Most a customer should spend on one product per year (5% of yearly income by default)."""
    share = config.load("pricing")["affordability"]["max_share_of_annual_income"]
    return share * monthly_income(profile) * 12


def is_compulsory(product: str) -> bool:
    return product in config.load("pricing")["compulsory_products"]