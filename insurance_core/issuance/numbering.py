"""Policy numbers like NGI-HCN-2026-000001-1, where the last digit is a Luhn check digit."""


def luhn_check_digit(digits: str) -> int:
    """Luhn algorithm (used on bank cards): catches any single mistyped digit."""
    total = 0
    for i, d in enumerate(reversed(digits)):
        n = int(d)
        if i % 2 == 0:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return (10 - total % 10) % 10


def make_policy_number(product_code: str, year: int, seq: int, prefix: str = "NGI") -> str:
    core = f"{year}{seq:06d}"
    return f"{prefix}-{product_code}-{year}-{seq:06d}-{luhn_check_digit(core)}"


def is_well_formed(policy_number: str) -> bool:
    """True if the number has the right shape AND its check digit matches."""
    parts = policy_number.split("-")
    if len(parts) != 5:
        return False
    _, _, year, seq, check = parts
    if not (year.isdigit() and seq.isdigit() and check.isdigit() and len(check) == 1):
        return False
    return luhn_check_digit(f"{year}{seq}") == int(check)