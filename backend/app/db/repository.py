"""Every database query lives here, so routes and services never write SQL themselves."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import AuditLog, Payment, PaymentItem, Policy, Quote


def get_quote(db: Session, quote_id: str) -> Quote | None:
    return db.get(Quote, quote_id)


def get_policy_by_number(db: Session, policy_number: str) -> Policy | None:
    return db.scalar(select(Policy).where(Policy.policy_number == policy_number))


def get_policy_by_payment_reference(db: Session, payment_reference: str, product_code: str) -> Policy | None:
    return db.scalar(select(Policy).where(Policy.payment_reference == payment_reference,
                                          Policy.product_code == product_code))


def get_policies_by_payment_reference(db: Session, payment_reference: str) -> list[Policy]:
    """Every policy a basket payment has issued so far (0..N, one per product)."""
    return list(db.scalars(select(Policy).where(Policy.payment_reference == payment_reference)))


def get_active_policies_for_quote(db: Session, quote_id: str) -> list[Policy]:
    """Used for both the duplicate-purchase check and already_committed_ngn: what THIS quote has
    already bought. Across DIFFERENT quotes we can't tell (see docs/assumptions.md)."""
    return list(db.scalars(select(Policy).where(Policy.quote_id == quote_id, Policy.status == "active")))


def log_event(db: Session, event: str, payload: dict, created_at: str,
              quote_id: str | None = None, policy_number: str | None = None) -> None:
    db.add(AuditLog(event=event, quote_id=quote_id, policy_number=policy_number,
                    payload=payload, created_at=created_at))


def get_payment(db: Session, reference: str) -> Payment | None:
    return db.get(Payment, reference)


def get_open_payment_for_quote(db: Session, quote_id: str) -> Payment | None:
    """The one payment (if any) still waiting for money on this quote. A quote never has more than
    one at a time: initialize_payment() resolves or abandons the previous one before starting a new."""
    return db.scalar(select(Payment).where(Payment.quote_id == quote_id, Payment.status == "initialized"))


def get_payment_items(db: Session, payment_reference: str) -> list[PaymentItem]:
    return list(db.scalars(select(PaymentItem).where(PaymentItem.payment_reference == payment_reference)))


def get_referral_quotes(db: Session, limit: int) -> list[Quote]:
    """Unresolved referrals, newest first. Filters on the indexed refer_reason column -- no quote's
    JSON `result` blob is loaded or parsed just to find out whether it needs a broker."""
    return list(db.scalars(select(Quote).where(Quote.refer_reason.isnot(None),
                                               Quote.referral_resolved_at.is_(None))
                           .order_by(Quote.created_at.desc()).limit(limit)))


def get_stuck_payments(db: Session, limit: int) -> list[Payment]:
    """Paid payments nobody holds a policy for yet, newest first."""
    return list(db.scalars(select(Payment).where(Payment.status == "paid_not_issued",
                                                 Payment.resolved_at.is_(None))
                           .order_by(Payment.confirmed_at.desc()).limit(limit)))


def get_failed_payments(db: Session, limit: int) -> list[Payment]:
    """Read-only: shown for visibility, nothing for a broker to resolve (see routes/broker.py)."""
    return list(db.scalars(select(Payment).where(Payment.status == "failed")
                           .order_by(Payment.confirmed_at.desc()).limit(limit)))