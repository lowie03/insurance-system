"""Taking payment with Paystack for a whole BASKET, then issuing every item once payment is
CONFIRMED.

  initialize_payment: re-validate + re-price the basket, refuse duplicate products (Issue 1),
                      resolve any still-open payment on this quote, create ONE Paystack
                      transaction for the combined first payment, return the checkout link.
  confirm_payment:    ask Paystack (never the browser) whether the reference was paid, check the
                      amount and currency match, then issue every item in one transaction. Safe to
                      call many times: from the redirect, from the webhook, from a manual re-check.
                      An "abandoned" payment still has a live Paystack checkout link, so a customer
                      CAN still pay it: it's re-checked exactly like an "initialized" one rather than
                      ignored, and issuance is re-validated fresh (see issue_basket), so it correctly
                      becomes paid_not_issued if whatever it would issue has since become a duplicate.
"""
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.app.db import repository
from backend.app.db.models import Payment, PaymentItem
from backend.app.services.duplicate_check import DuplicateProductError
from backend.app.services.issuance_service import QuoteExpired, QuoteNotFound, issue_basket, prepare_basket_selection
from backend.app.services.paystack import naira_to_kobo
from backend.app.settings import Settings
from insurance_core.issuance.policy import IssuanceError


class PaymentNotFound(Exception):
    pass


class PaymentSetupError(Exception):
    """The payment can't be started; the message is safe to show the customer."""


def _now(settings: Settings) -> str:
    return datetime.now(ZoneInfo(settings.timezone)).isoformat(timespec="seconds")


def _line_pairs(lines: list) -> list:
    return sorted((l["product"], l["payment_plan"]) for l in lines)


def _item_pairs(items: list) -> list:
    return sorted((i.product_code, i.payment_plan) for i in items)


def initialize_payment(db: Session, settings: Settings, bundle: dict, paystack, quote_id: str,
                       items: list, email: str | None) -> tuple:
    """items: [{"product_code", "payment_plan"?}], the same shape the basket preview takes.
    Returns (Payment, basket) -- the route builds its response straight from `basket`, since the
    saved PaymentItem rows only keep what's needed to re-issue, not the full breakdown/notes."""
    quote, _, _, basket = prepare_basket_selection(db, bundle, settings, quote_id, items)
    email = email or quote.email
    if not email:
        raise PaymentSetupError("an email address is required for payment")

    open_payment = repository.get_open_payment_for_quote(db, quote_id)
    if open_payment is not None:
        if _item_pairs(repository.get_payment_items(db, open_payment.reference)) == _line_pairs(basket["lines"]):
            return open_payment, basket           # identical basket re-requested: idempotent init
        tx = paystack.verify(open_payment.reference)
        if tx.get("status") == "success":
            # It WAS paid without us knowing yet: confirm/issue that one and refuse this new request.
            confirm_payment(db, settings, bundle, paystack, open_payment.reference)
            raise DuplicateProductError(
                f"a different basket was already paid for on this quote (reference {open_payment.reference}); "
                f"refresh to see it")
        _mark(db, settings, open_payment, "abandoned", "superseded by a new basket before payment completed")

    payment = Payment(reference=f"INS-{uuid.uuid4().hex}", quote_id=quote.id,
                      amount_kobo=naira_to_kobo(basket["first_payment_ngn"]),
                      email=email, status="initialized", created_at=_now(settings))
    db.add(payment)
    for line in basket["lines"]:
        db.add(PaymentItem(payment_reference=payment.reference, product_code=line["product"],
                           payment_plan=line["payment_plan"], first_payment_kobo=naira_to_kobo(line["payment_ngn"]),
                           total_ngn=line["total_ngn"]))
    data = paystack.initialize(email=email, amount_kobo=payment.amount_kobo, reference=payment.reference,
                               callback_url=settings.paystack_callback_url,
                               metadata={"quote_id": quote.id, "products": [l["product"] for l in basket["lines"]]})
    payment.authorization_url = data["authorization_url"]
    repository.log_event(db, "payment_initialized", quote_id=quote.id, created_at=payment.created_at,
                         payload={"reference": payment.reference, "amount_kobo": payment.amount_kobo,
                                  "lines": [{"product": l["product"], "payment_plan": l["payment_plan"]}
                                           for l in basket["lines"]]})
    db.commit()
    return payment, basket


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
        return payment                                     # not paid (yet): stays "initialized" or "abandoned"
    if tx.get("amount") != payment.amount_kobo or tx.get("currency") != "NGN":
        return _mark(db, settings, payment, "failed",
                     f"amount mismatch: expected {payment.amount_kobo} kobo NGN, "
                     f"Paystack reported {tx.get('amount')} {tx.get('currency')}")

    # Paid in full. Issue every item, honouring the quote even if it expired while paying.
    payment_items = repository.get_payment_items(db, reference)
    basket_items = [{"product_code": it.product_code, "payment_plan": it.payment_plan} for it in payment_items]
    expected = {it.product_code: it.first_payment_kobo / 100 for it in payment_items}
    try:
        # issue_basket re-runs prepare_basket_selection, which re-checks Issue 1's duplicate/group
        # rule against whatever is active RIGHT NOW -- not just what was true at initialize time.
        # That's what catches two paid baskets racing for the same product: DuplicateProductError
        # here means someone else's basket won that race, so this one is refused, not double-issued.
        policies = issue_basket(db, settings, bundle, payment.quote_id, basket_items, payment_reference=reference,
                                check_expiry=False, expected_line_payments_ngn=expected)
    except (IssuanceError, DuplicateProductError, QuoteExpired, QuoteNotFound) as e:
        db.rollback()
        return _mark(db, settings, payment, "paid_not_issued", str(e))   # a broker must refund or resolve

    by_product = {p.product_code: p for p in policies}
    for it in payment_items:
        it.policy_number = by_product[it.product_code].policy_number
    return _mark(db, settings, payment, "issued", None)
