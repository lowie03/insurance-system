"""Safe readers for a customer profile.

A profile is a plain dict of form answers. It can come from pandas (missing = NaN)
or from the API (missing = None), so every reader here handles both.
"""
import math


def is_missing(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def get(profile: dict, field: str, default=None):
    value = profile.get(field)
    return default if is_missing(value) else value


def has_income(profile: dict) -> bool:
    return not is_missing(profile.get("monthly_income_ngn"))


def monthly_income(profile: dict) -> float:
    """Monthly income, or 0 if not provided. Use has_income() when 'unknown' must differ from 'zero'."""
    return float(get(profile, "monthly_income_ngn", 0.0))


def household_size(profile: dict) -> int:
    spouse = 1 if profile.get("marital_status") == "Married" else 0
    return 1 + spouse + int(get(profile, "dependents", 0))