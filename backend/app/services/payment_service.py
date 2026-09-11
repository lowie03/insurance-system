"""Taking payment with Paystack, then issuing the policy once payment is CONFIRMED.

  initialize_payment: re-validate the choice, compute the amount on the SERVER, create a Paystack
                      transaction with our own reference, return the checkout link.
  confirm_payment:    ask Paystack (never the browser) whether the reference was paid, check the
                      amount and currency match, then issue. Safe to call many times: from the redirect,
                      from the webhook, from a manual re-check. Only one policy can ever result.
"""
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.app.db import repository
from backend.app.db.models import Payment
from backend.app.services.issuance_service import QuoteExpired, QuoteNotFound, issue_policy, prepare_selection
from backend.app.services.paystack import naira_to_kobo
from backend.app.settings import Settings
from insurance_core.issuance.policy import IssuanceError


class PaymentNotFound(Exception):
    pass


class PaymentSetupError(Exception):
    """The payment can't be started; the message is safe to show the customer."""


def _now(settings: Settings) -> str:
    return datetime.now(ZoneInfo(settings.timezone)).isoformat(timespec="seconds")


def initialize_payment(db: Session, settings: Settings, bundle: dict, paystack, quote_id: str,
                       product_code: str, payment_plan: str | None, email: str | None) -> Payment:
    quote, _, _, rec, option = prepare_selection(db, bundle, settings, quote_id, product_code, payment_plan)
    email = email or quote.email
    if not email:
        raise PaymentSetupError("an email address is required for payment")

    payment = Payment(reference=f"INS-{uuid.uuid4().hex}", quote_id=quote.id, product_code=product_code,
                      payment_plan=option["plan"], amount_kobo=naira_to_kobo(option["payment_ngn"]),
                      email=email, status="initialized", created_at=_now(settings))
    data = paystack.initialize(email=email, amount_kobo=payment.amount_kobo, reference=payment.reference,
                               callback_url=settings.paystack_callback_url,
                               metadata={"quote_id": quote.id, "product_code": product_code,
                                         "payment_plan": option["plan"]})
    payment.authorization_url = data["authorization_url"]
    db.add(payment)
    repository.log_event(db, "payment_initialized", quote_id=quote.id, created_at=payment.created_at,
                         payload={"reference": payment.reference, "amount_kobo": payment.amount_kobo,
                                  "product_code": product_code, "payment_plan": option["plan"]})
    db.commit()
    return payment


def _mark(db: Session, settings: Settings, payment: Payment, status: str, detail: str | None) -> Payment:
    payment.status, payment.status_detail, payment.confirmed_at = status, detail, _now(settings)
    repository.log_event(db, f"payment_{status}", quote_id=payment.quote_id, created_at=payment.confirmed_at,
                         payload={"reference": payment.reference, "detail": detail})
    db.commit()
    return payment


def confirm_payment(db: Session, settings: Settings, bundle: dict, paystack, reference: str) -> Payment:
    payment = repository.get_payment(db, reference)
    if payment is None:
        raise PaymentNotFound(reference)
    if payment.status in ("issued", "failed", "paid_not_issued"):
        return payment                                     # already settled: nothing more to do

    tx = paystack.verify(reference)
    if tx.get("status") != "success":
        return payment                                     # not paid (yet): stays "initialized"
    if tx.get("amount") != payment.amount_kobo or tx.get("currency") != "NGN":
        return _mark(db, settings, payment, "failed",
                     f"amount mismatch: expected {payment.amount_kobo} kobo NGN, "
                     f"Paystack reported {tx.get('amount')} {tx.get('currency')}")

    # Paid in full. Issue, honouring the quote even if it expired while the customer was paying.
    try:
        policy = issue_policy(db, settings, bundle, payment.quote_id, payment.product_code,
                              payment.payment_plan, payment_reference=reference, check_expiry=False,
                              expected_payment_ngn=payment.amount_kobo / 100)
    except (IssuanceError, QuoteExpired, QuoteNotFound) as e:
        db.rollback()
        return _mark(db, settings, payment, "paid_not_issued", str(e))   # a broker must refund or resolve

    payment.policy_number = policy.policy_number
    return _mark(db, settings, payment, "issued", None)