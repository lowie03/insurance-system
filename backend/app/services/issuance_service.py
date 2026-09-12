"""Issuing a BASKET: one or more policies from one saved quote, in one database transaction.

  1. load the saved quote (the profile comes from OUR database, not the browser)
  2. refuse expired quotes; refuse products already active on this quote (Issue 1); return the
     existing policies if this payment reference was already used for the SAME basket
  3. re-run recommend() and re-validate/price the whole basket (insurance_core.basket)
  4. in ONE transaction: for each line, reserve a sequence number, build + sign the record, write
     the PDF, save the policy, write the audit log. Any failure rolls EVERYTHING back (all-or-nothing).
"""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db import repository
from backend.app.db.models import Policy
from backend.app.services.duplicate_check import check_no_duplicate_products
from backend.app.settings import Settings
from insurance_core.basket import group_of, validate_basket
from insurance_core.issuance.certificate import build_certificate
from insurance_core.issuance.policy import IssuanceError, new_policy_record
from insurance_core.recommender import recommend


class QuoteNotFound(Exception):
    pass


class QuoteExpired(Exception):
    pass


def verify_url(settings: Settings, record: dict) -> str:
    return f"{settings.verify_base_url}/{record['policy_number']}?s={record['signature']}"


def prepare_basket_selection(db: Session, bundle: dict, settings: Settings, quote_id: str, items: list,
                             check_expiry: bool = True):
    """Load the saved quote and re-validate + re-price the whole basket against the CURRENT rules
    and prices. Used before taking payment, again before issuing, and by the basket preview.
    Returns (quote, profile, result, basket)."""
    quote = repository.get_quote(db, quote_id)
    if quote is None:
        raise QuoteNotFound(quote_id)
    if check_expiry and datetime.fromisoformat(quote.expires_at) < datetime.now(ZoneInfo(settings.timezone)):
        raise QuoteExpired(quote_id)

    active_policies = repository.get_active_policies_for_quote(db, quote_id)
    check_no_duplicate_products({p.product_code for p in active_policies},
                                [i["product_code"] for i in items])

    profile = {**quote.profile, "customer_id": quote.customer_id}
    result = recommend(profile, bundle, top_k=100)
    already_committed_ngn = sum(p.total_ngn for p in active_policies)
    basket = validate_basket(result, items, profile, already_committed_ngn=already_committed_ngn)
    return quote, profile, result, basket


def _issue_one_policy(db: Session, settings: Settings, quote, profile: dict, result: dict, line: dict,
                      now: datetime, payment_reference: str) -> tuple[Policy, Path]:
    """INSERT one policy row and write its PDF. Does NOT commit: the caller owns the transaction,
    so several lines from one basket land in the database together or not at all."""
    rec = next(r for r in result["recommendations"] if r["product"] == line["product"])
    option = {"plan": line["payment_plan"], "payment_ngn": line["payment_ngn"], "total_ngn": line["total_ngn"]}

    policy = Policy(quote_id=quote.id, customer_id=quote.customer_id, product_code=line["product"],
                    exclusive_group=group_of(line["product"]), payment_reference=payment_reference,
                    status="pending", created_at=now.isoformat(timespec="seconds"))
    db.add(policy)
    db.flush()                                  # sends the INSERT, so the database assigns policy.id

    record = new_policy_record(profile, rec, option, seq=policy.id, now=now,
                               payment_reference=payment_reference, key=settings.signing_key_bytes)
    pdf = build_certificate(record, rec, quote.full_name, verify_url(settings, record),
                            versions_note=f"Model {result['model_version']}")
    settings.pdf_storage_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = settings.pdf_storage_dir / f"{record['policy_number']}.pdf"
    pdf_path.write_bytes(pdf)

    for field in ["policy_number", "premium_ngn", "payment_plan", "payment_ngn", "total_ngn",
                  "start_date", "end_date", "status", "signature"]:
        setattr(policy, field, record[field])
    policy.pdf_path = str(pdf_path)

    repository.log_event(db, "policy_issued", quote_id=quote.id, policy_number=record["policy_number"],
                         created_at=record["created_at"],
                         payload={"model_version": result["model_version"],
                                  "config_versions": result["config_versions"],
                                  "chosen": rec, "excluded": result["excluded"]})
    return policy, pdf_path


def issue_basket(db: Session, settings: Settings, bundle: dict, quote_id: str, items: list,
                 payment_reference: str, check_expiry: bool = True,
                 expected_line_payments_ngn: dict | None = None) -> list[Policy]:
    """check_expiry=False is used after a CONFIRMED payment that started while the quote was still
    valid. expected_line_payments_ngn ({product_code: first payment at charge time}) guards against
    prices changing between payment and issuance -- checked PER LINE, not just as a basket total."""
    now = datetime.now(ZoneInfo(settings.timezone))

    if repository.get_quote(db, quote_id) is None:
        raise QuoteNotFound(quote_id)
    requested_codes = {i["product_code"] for i in items}
    existing = repository.get_policies_by_payment_reference(db, payment_reference)
    if existing:
        if {p.product_code for p in existing} != requested_codes:
            raise IssuanceError("this payment reference was already used for a different basket")
        return existing                          # same request retried (e.g. a double-click): same policies back

    quote, profile, result, basket = prepare_basket_selection(db, bundle, settings, quote_id, items, check_expiry)
    if expected_line_payments_ngn is not None:
        for line in basket["lines"]:
            expected = expected_line_payments_ngn.get(line["product"])
            if expected is not None and line["payment_ngn"] != expected:
                raise IssuanceError(f"{line['product']}: the price changed since payment started "
                                    f"(paid ₦{expected:,.0f}, now ₦{line['payment_ngn']:,.0f})")

    pdf_paths: list[Path] = []
    try:
        policies = []
        for line in basket["lines"]:
            policy, pdf_path = _issue_one_policy(db, settings, quote, profile, result, line, now,
                                                 payment_reference)
            policies.append(policy)
            pdf_paths.append(pdf_path)
        db.commit()
    except IntegrityError:
        # Two different races land here. (a) A concurrent, IDENTICAL request for this same
        # payment_reference already inserted these exact policies (uq_policy_payment_product):
        # there's nothing new to do, return what's already there -- the existing idempotency
        # behaviour. (b) A DIFFERENT payment's basket won the race for the same product/group on
        # this quote (the exclusive_group partial index, Issue 1's last line of defense): there is
        # nothing of OURS to return, so refuse this basket cleanly instead of raising.
        db.rollback()
        for p in pdf_paths:
            p.unlink(missing_ok=True)
        existing = repository.get_policies_by_payment_reference(db, payment_reference)
        if {p.product_code for p in existing} == requested_codes:
            return existing
        raise IssuanceError("a policy for this product was issued by another payment moments earlier")
    except Exception:
        db.rollback()
        for p in pdf_paths:
            p.unlink(missing_ok=True)           # don't leave certificates for policies that don't exist
        raise
    return policies
