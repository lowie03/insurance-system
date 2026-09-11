"""Payment plans: annual vs monthly, checked against budget AND cash flow."""
from insurance_core import config
from insurance_core.pricing import annual_budget
from insurance_core.profile import has_income, monthly_income


def payment_options(premium: float, profile: dict):
    """Returns (all plan options, name of the cheapest plan that fits, or None if none fits).

    fits_budget:    the plan's TOTAL cost is within the yearly budget
    fits_cash_flow: each single payment is small enough for one month's income
    If income is unknown, nothing can be checked, so every plan is allowed.
    """
    cfg = config.load("payment_plans")
    known = has_income(profile)
    max_single = cfg["cash_flow"]["max_single_payment_share_of_monthly_income"] * monthly_income(profile)
    budget = annual_budget(profile)

    options = []
    for name, plan in cfg["plans"].items():
        total = premium * (1 + plan["loading"])
        each = total / plan["payments"]
        options.append({
            "plan": name,
            "payments": plan["payments"],
            "payment_ngn": float(round(each, -1)),
            "total_ngn": float(round(total, -1)),
            "fits_budget": (not known) or total <= budget,
            "fits_cash_flow": (not known) or each <= max_single,
        })
    viable = [o for o in options if o["fits_budget"] and o["fits_cash_flow"]]
    chosen = min(viable, key=lambda o: o["total_ngn"])["plan"] if viable else None
    return options, chosen