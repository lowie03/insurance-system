"""Building and checking policy records (plain dicts, no database)."""
from datetime import date, datetime, timedelta

from insurance_core.issuance.numbering import is_well_formed, make_policy_number
from insurance_core.issuance.signing import sign, signature_matches


class IssuanceError(Exception):
    """Raised when a policy must not be issued; the message is safe to show the customer."""


def one_year_cover(start: date) -> date:
    """Last day of a 12-month policy. Handles 29 February, which doesn't exist the next year."""
    try:
        return start.replace(year=start.year + 1) - timedelta(days=1)
    except ValueError:
        return start.replace(year=start.year + 1, day=28)


def select_recommendation(result: dict, product_code: str, plan: str | None = None):
    """Server-side re-validation: pick the chosen product and plan out of a fresh recommend() result.

    Returns (recommendation, payment option). Raises IssuanceError if the product or plan isn't allowed.
    """
    rec = next((r for r in result["recommendations"] if r["product"] == product_code), None)
    if rec is None:
        reason = next((e["reason"] for e in result["excluded"] if e["product"] == product_code),
                      "product not available for this customer")
        raise IssuanceError(f"{product_code} cannot be issued: {reason}")
    plan = plan or rec["suggested_plan"]
    option = next((o for o in rec["payment_options"] if o["plan"] == plan), None)
    if option is None:
        raise IssuanceError(f"unknown payment plan {plan!r}")
    if plan != rec["suggested_plan"] and not (option["fits_budget"] and option["fits_cash_flow"]):
        raise IssuanceError(f"{plan} payment plan doesn't fit this customer's budget")
    return rec, option


def new_policy_record(profile: dict, rec: dict, option: dict, seq: int, now: datetime,
                      payment_reference: str, key: bytes) -> dict:
    """A complete, signed policy record. `seq` is the database's unique sequence number."""
    start = now.date()
    record = {
        "policy_number": make_policy_number(rec["product"], start.year, seq),
        "customer_id": profile["customer_id"],
        "product_code": rec["product"],
        "premium_ngn": rec["premium_ngn"],
        "payment_plan": option["plan"],
        "payment_ngn": option["payment_ngn"],
        "total_ngn": option["total_ngn"],
        "start_date": start.isoformat(),
        "end_date": one_year_cover(start).isoformat(),
        "status": "active",
        "payment_reference": payment_reference,
        "created_at": now.isoformat(timespec="seconds"),
    }
    record["signature"] = sign(record, key)
    return record


def verification_status(policy_number: str, signature: str, record: dict | None, key: bytes, today: date) -> str:
    """What the public verify page shows. `record` is the stored policy, or None if not found."""
    if not is_well_formed(policy_number):
        return "INVALID_NUMBER"
    if record is None:
        return "NOT_FOUND"
    if not signature_matches(record, signature, key):
        return "SIGNATURE_MISMATCH"
    if record["status"] != "active":
        return record["status"].upper()          # e.g. CANCELLED
    if record["end_date"] < today.isoformat():
        return "EXPIRED"
    return "VALID"