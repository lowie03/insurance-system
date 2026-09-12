"""Broker-only routes: the review queue, plus the three ways a broker closes an item out.

Every route here requires require_broker (a shared X-Broker-Token header, see dependencies.py),
applied once at the router level rather than on each endpoint.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.dependencies import get_db, get_settings, require_broker
from backend.app.schemas import BrokerActionOut, PaymentResolveIn, PolicyCancelIn, QueueOut, ReferralResolveIn
from backend.app.services import broker_service
from backend.app.settings import Settings

router = APIRouter(prefix="/broker", tags=["broker"], dependencies=[Depends(require_broker)])

REFERRAL_MESSAGES = {
    "contacted": "Recorded as contacted.",
    "advised_subsidy": "Recorded as advised towards a subsidised scheme.",
    "no_action": "No action taken; marked as reviewed.",
}
PAYMENT_MESSAGES = {
    "refunded": ("Recorded as refunded. This does NOT call Paystack's refund API -- "
                "refund the customer there separately."),
    "issued_manually": "Recorded as issued manually outside the system.",
    "no_action": "No action taken; marked as reviewed.",
}


def _already_resolved(existing: dict) -> HTTPException:
    return HTTPException(409, {"message": "already resolved", **existing})


@router.get("/queue", response_model=QueueOut)
def get_queue(kind: str | None = Query(default=None, pattern="^(referral|stuck_payment|failed_payment)$"),
             limit: int = Query(default=20, ge=1, le=100), offset: int = Query(default=0, ge=0),
             db: Session = Depends(get_db)):
    """One feed, newest first across all kinds, or filtered to just one via ?kind=."""
    return broker_service.build_queue(db, kind, limit, offset)


@router.post("/referrals/{quote_id}/resolve", response_model=BrokerActionOut)
def resolve_referral(quote_id: str, body: ReferralResolveIn, db: Session = Depends(get_db),
                     settings: Settings = Depends(get_settings)):
    try:
        result = broker_service.resolve_referral(db, settings, quote_id, body.outcome, body.note)
    except broker_service.NotFound:
        raise HTTPException(404, "quote not found")
    except broker_service.WrongState as e:
        raise HTTPException(409, str(e))
    except broker_service.AlreadyResolved as e:
        raise _already_resolved(e.existing)
    return BrokerActionOut(status="resolved", outcome=result["outcome"], note=result["note"],
                           resolved_at=result["resolved_at"], message=REFERRAL_MESSAGES[result["outcome"]])


@router.post("/payments/{reference}/resolve", response_model=BrokerActionOut)
def resolve_payment(reference: str, body: PaymentResolveIn, db: Session = Depends(get_db),
                    settings: Settings = Depends(get_settings)):
    try:
        result = broker_service.resolve_payment(db, settings, reference, body.outcome, body.note)
    except broker_service.NotFound:
        raise HTTPException(404, "payment not found")
    except broker_service.WrongState as e:
        raise HTTPException(409, str(e))
    except broker_service.AlreadyResolved as e:
        raise _already_resolved(e.existing)
    return BrokerActionOut(status="resolved", outcome=result["outcome"], note=result["note"],
                           resolved_at=result["resolved_at"], message=PAYMENT_MESSAGES[result["outcome"]])


@router.post("/policies/{policy_number}/cancel", response_model=BrokerActionOut)
def cancel_policy(policy_number: str, body: PolicyCancelIn, db: Session = Depends(get_db),
                  settings: Settings = Depends(get_settings)):
    try:
        result = broker_service.cancel_policy(db, settings, policy_number, body.reason, body.note)
    except broker_service.NotFound:
        raise HTTPException(404, "policy not found")
    except broker_service.AlreadyResolved as e:
        raise _already_resolved(e.existing)
    return BrokerActionOut(status="cancelled", reason=result["reason"], note=result["note"],
                           resolved_at=result["resolved_at"], message="Policy cancelled.")
