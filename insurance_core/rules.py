"""Eligibility (hard) and suitability (soft) rules, driven by config/*.yaml."""
import operator

from insurance_core import config
from insurance_core.profile import is_missing

OPS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
    "in": lambda actual, allowed: actual in allowed,
}


def check_rule(profile: dict, rule: dict) -> bool:
    actual = profile.get(rule["field"])
    if is_missing(actual):
        return False                      # missing information never passes a rule
    return OPS[rule["op"]](actual, rule["value"])


def eligibility_failure(product: str, profile: dict):
    """Reason the customer is NOT eligible for `product`, or None if they are."""
    for rule in config.load("eligibility_rules")["rules"].get(product, []):
        if not check_rule(profile, rule):
            return rule["reason"]
    return None


def apply_suitability(product: str, profile: dict, score: float):
    """Returns (adjusted score, notes explaining any adjustment)."""
    notes = []
    for rule in config.load("suitability_rules")["rules"]:
        if product in rule["products"] and profile.get(rule["field"]) == rule["value"]:
            score *= rule["factor"]
            notes.append(rule["note"])
    return score, notes