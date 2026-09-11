"""Issuing a policy: the Colab issue_policy() flow, now around a real database transaction.

  1. load the saved quote (the profile comes from OUR database, not the browser)
  2. refuse expired quotes; return the existing policy if this payment was already used
  3. re-run recommend() and re-validate the chosen product + plan
  4. in ONE transaction: reserve a sequence number, build + sign the record, write the PDF,
     save the policy, write the audit log. Any failure rolls everything back.
"""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db import repository
from backend.app.db.models import Policy
from backend.app.settings import Settings
from insurance_core.issuance.certificate import build_certificate
from insurance_core.issuance.policy import IssuanceError, new_policy_record, select_recommendation
from insurance_core.recommender import recommend


class QuoteNotFound(Exception):
    pass


class QuoteExpired(Exception):
    pass


def verify_url(settings: Settings, record: dict) -> str:
    return f"{settings.verify_base_url}/{record['policy_number']}?s={record['signature']}"


def prepare_selection(db: Session, bundle: dict, settings: Settings, quote_id: str, product_code: str,
                      payment_plan: str | None, check_expiry: bool = True):
    """Load the saved quote and re-validate the chosen product + plan against the CURRENT rules and prices.
    Used both before taking payment and again before issuing. Returns (quote, profile, result, rec, option)."""
    quote = repository.get_quote(db, quote_id)
    if quote is None:
        raise QuoteNotFound(quote_id)
    if check_expiry and datetime.fromisoformat(quote.expires_at) < datetime.now(ZoneInfo(settings.timezone)):
        raise QuoteExpired(quote_id)
    profile = {**quote.profile, "customer_id": quote.customer_id}
    result = recommend(profile, bundle, top_k=100)             # every candidate, not just the top 3
    rec, option = select_recommendation(result, product_code, payment_plan)
    return quote, profile, result, rec, option


def issue_policy(db: Session, settings: Settings, bundle: dict, quote_id: str, product_code: str,
                 payment_plan: str | None, payment_reference: str, check_expiry: bool = True,
                 expected_payment_ngn: float | None = None) -> Policy:
    """check_expiry=False is used after a CONFIRMED payment that started while the quote was still valid.
    expected_payment_ngn guards against prices changing between payment and issuance."""
    now = datetime.now(ZoneInfo(settings.timezone))

    # 1-2. Load the quote; idempotency check (before expiry: a retried request must get its policy back)
    if repository.get_quote(db, quote_id) is None:
        raise QuoteNotFound(quote_id)
    existing = repository.get_policy_by_payment_reference(db, payment_reference)
    if existing is not None:
        if existing.quote_id != quote_id or existing.product_code != product_code:
            raise IssuanceError("this payment reference was already used for a different policy")
        return existing                        # same request retried (e.g. a double-click): same policy back

    # 3. Re-validate
    quote, profile, result, rec, option = prepare_selection(db, bundle, settings, quote_id, product_code,
                                                            payment_plan, check_expiry)
    if expected_payment_ngn is not None and option["payment_ngn"] != expected_payment_ngn:
        raise IssuanceError(f"the price changed since payment started "
                            f"(paid ₦{expected_payment_ngn:,.0f}, now ₦{option['payment_ngn']:,.0f})")

    # 4. One transaction
    pdf_path: Path | None = None
    try:
        policy = Policy(quote_id=quote.id, customer_id=quote.customer_id, product_code=product_code,
                        payment_reference=payment_reference, status="pending",
                        created_at=now.isoformat(timespec="seconds"))
        db.add(policy)
        db.flush()                              # sends the INSERT, so the database assigns policy.id

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
        db.commit()
    except IntegrityError:
        # Two identical requests arrived at the same moment and the other one won the race:
        # the unique payment_reference stopped a duplicate policy. Return the one that was created.
        db.rollback()
        if pdf_path is not None:
            pdf_path.unlink(missing_ok=True)
        existing = repository.get_policy_by_payment_reference(db, payment_reference)
        if existing is None:
            raise
        return existing
    except Exception:
        db.rollback()
        if pdf_path is not None:
            pdf_path.unlink(missing_ok=True)    # don't leave a certificate for a policy that doesn't exist
        raise
    return policy