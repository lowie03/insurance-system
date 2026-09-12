"""The broker review queue, and the three ways a broker closes an item out.

build_queue() merges three kinds of item -- referred quotes, paid-but-unissued payments, and failed
payments -- newest first, across all three, with pagination. Each per-kind query fetches at most
`offset + limit + 1` rows (already sorted newest-first, via indexed columns): that's provably enough
to get the requested page exactly right in a k-way merge of sorted sources, and enough to know
whether another page follows, without ever loading a quote's full JSON just to check refer_to_broker
(see Quote.refer_reason) or scanning more rows than the page could possibly need.

Every action here writes an audit_log entry (action, target, reason, broker_note, config_versions).
A shared broker token means the log proves SOME broker acted, not WHICH one -- see docs/assumptions.md.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.app.db import repository
from backend.app.routes.presenters import excluded_out, recommendations_out
from backend.app.settings import Settings
from insurance_core import config
from insurance_core.catalogue import product_name


class NotFound(Exception):
    pass


class WrongState(Exception):
    """The target exists but isn't in a state this action applies to (e.g. resolving a payment
    that was never paid_not_issued)."""


class AlreadyResolved(Exception):
    """Carries the EXISTING resolution so the route can return it in the 409 body."""

    def __init__(self, existing: dict):
        self.existing = existing
        super().__init__("already resolved")


def _now(settings: Settings) -> str:
    return datetime.now(ZoneInfo(settings.timezone)).isoformat(timespec="seconds")


def _audit(db: Session, settings: Settings, event: str, action: str, target: str, reason: str, note: str,
          quote_id: str | None = None, policy_number: str | None = None) -> None:
    repository.log_event(db, event, quote_id=quote_id, policy_number=policy_number, created_at=_now(settings),
                         payload={"action": action, "target": target, "reason": reason, "broker_note": note,
                                  "config_versions": config.versions()})


def _referral_item(quote) -> dict:
    result = quote.result
    return {"kind": "referral", "quote_id": quote.id, "created_at": quote.created_at,
           "refer_reason": quote.refer_reason, "recommendations": recommendations_out(result),
           "excluded": excluded_out(result)}


def _payment_lines(db: Session, payment) -> list[dict]:
    return [{"product_code": it.product_code, "product_name": product_name(it.product_code),
            "payment_plan": it.payment_plan, "payment_ngn": it.first_payment_kobo / 100,
            "total_ngn": it.total_ngn} for it in repository.get_payment_items(db, payment.reference)]


def _payment_item(db: Session, payment, kind: str) -> dict:
    return {"kind": kind, "reference": payment.reference, "created_at": payment.confirmed_at or payment.created_at,
           "amount_ngn": payment.amount_kobo / 100, "reason": payment.status_detail,
           "lines": _payment_lines(db, payment)}


def build_queue(db: Session, kind: str | None, limit: int, offset: int) -> dict:
    fetch = offset + limit + 1                      # +1: enough to know if a next page exists
    items = []
    if kind in (None, "referral"):
        items += [_referral_item(q) for q in repository.get_referral_quotes(db, fetch)]
    if kind in (None, "stuck_payment"):
        items += [_payment_item(db, p, "stuck_payment") for p in repository.get_stuck_payments(db, fetch)]
    if kind in (None, "failed_payment"):
        items += [_payment_item(db, p, "failed_payment") for p in repository.get_failed_payments(db, fetch)]
    items.sort(key=lambda i: i["created_at"], reverse=True)
    return {"items": items[offset:offset + limit], "has_more": len(items) > offset + limit}


def resolve_referral(db: Session, settings: Settings, quote_id: str, outcome: str, note: str) -> dict:
    quote = repository.get_quote(db, quote_id)
    if quote is None:
        raise NotFound("quote not found")
    if quote.referral_resolved_at is not None:
        raise AlreadyResolved({"outcome": quote.referral_outcome, "note": quote.referral_note,
                               "resolved_at": quote.referral_resolved_at})
    if quote.refer_reason is None:
        raise WrongState("this quote was never referred to a broker")

    quote.referral_outcome, quote.referral_note = outcome, note
    quote.referral_resolved_at = _now(settings)
    _audit(db, settings, "broker_referral_resolved", "resolve_referral", quote_id, outcome, note, quote_id=quote_id)
    db.commit()
    return {"outcome": outcome, "note": note, "resolved_at": quote.referral_resolved_at}


def resolve_payment(db: Session, settings: Settings, reference: str, outcome: str, note: str) -> dict:
    payment = repository.get_payment(db, reference)
    if payment is None:
        raise NotFound("payment not found")
    if payment.resolved_at is not None:
        raise AlreadyResolved({"outcome": payment.resolved_outcome, "note": payment.resolved_note,
                               "resolved_at": payment.resolved_at})
    if payment.status != "paid_not_issued":
        raise WrongState(f"this payment is {payment.status!r}, not something a broker can resolve")

    payment.resolved_outcome, payment.resolved_note = outcome, note
    payment.resolved_at = _now(settings)
    _audit(db, settings, "broker_payment_resolved", "resolve_payment", reference, outcome, note,
          quote_id=payment.quote_id)
    db.commit()
    return {"outcome": outcome, "note": note, "resolved_at": payment.resolved_at}


def cancel_policy(db: Session, settings: Settings, policy_number: str, reason: str, note: str) -> dict:
    policy = repository.get_policy_by_number(db, policy_number)
    if policy is None:
        raise NotFound("policy not found")
    if policy.status == "cancelled":
        raise AlreadyResolved({"reason": policy.cancel_reason, "note": policy.cancel_note,
                               "resolved_at": policy.cancelled_at})

    policy.status = "cancelled"                    # frees the exclusive_group partial index for this quote
    policy.cancel_reason, policy.cancel_note = reason, note
    policy.cancelled_at = _now(settings)
    _audit(db, settings, "broker_policy_cancelled", "cancel_policy", policy_number, reason, note,
          quote_id=policy.quote_id, policy_number=policy_number)
    db.commit()
    return {"reason": reason, "note": note, "resolved_at": policy.cancelled_at}
