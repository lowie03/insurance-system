"""Every database query lives here, so routes and services never write SQL themselves."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models import AuditLog, Policy, Quote


def get_quote(db: Session, quote_id: str) -> Quote | None:
    return db.get(Quote, quote_id)


def get_policy_by_number(db: Session, policy_number: str) -> Policy | None:
    return db.scalar(select(Policy).where(Policy.policy_number == policy_number))


def get_policy_by_payment_reference(db: Session, payment_reference: str) -> Policy | None:
    return db.scalar(select(Policy).where(Policy.payment_reference == payment_reference))


def log_event(db: Session, event: str, payload: dict, created_at: str,
              quote_id: str | None = None, policy_number: str | None = None) -> None:
    db.add(AuditLog(event=event, quote_id=quote_id, policy_number=policy_number,
                    payload=payload, created_at=created_at))