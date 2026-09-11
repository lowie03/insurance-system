from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.app.db import repository
from backend.app.dependencies import get_bundle, get_db, get_settings
from backend.app.routes.presenters import policy_out
from backend.app.schemas import PolicyIn, PolicyOut
from backend.app.services.issuance_service import QuoteExpired, QuoteNotFound, issue_policy
from backend.app.settings import Settings
from insurance_core.issuance.policy import IssuanceError
from insurance_core.issuance.signing import signature_matches

router = APIRouter(prefix="/policies", tags=["policies"])


@router.post("", response_model=PolicyOut, status_code=201)
def post_policy(policy_in: PolicyIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
                bundle: dict = Depends(get_bundle)):
    """SIMULATED-payment issuance, for tests and offline demos only. With PAYMENT_MODE=paystack this is
    switched off: policies are issued only after Paystack confirms payment (see /payments)."""
    if settings.payment_mode != "simulated":
        raise HTTPException(403, "direct issuance is disabled; pay via POST /payments/initialize")
    try:
        policy = issue_policy(db, settings, bundle, policy_in.quote_id, policy_in.product_code,
                              policy_in.payment_plan, policy_in.payment_reference)
    except QuoteNotFound:
        raise HTTPException(404, "quote not found")
    except QuoteExpired:
        raise HTTPException(410, "this quote has expired; please request a new one")
    except IssuanceError as e:
        raise HTTPException(422, str(e))
    return policy_out(policy, settings)


def _policy_for_holder(db: Session, settings: Settings, policy_number: str, s: str):
    """The signature in the link acts as a password for that one policy (until we add accounts).
    Wrong or missing signature -> 404, so outsiders can't even tell whether a policy exists."""
    policy = repository.get_policy_by_number(db, policy_number)
    if policy is None or not signature_matches(policy.as_record(), s, settings.signing_key_bytes):
        raise HTTPException(404, "policy not found")
    return policy


@router.get("/{policy_number}", response_model=PolicyOut)
def get_policy(policy_number: str, s: str, db: Session = Depends(get_db),
               settings: Settings = Depends(get_settings)):
    return policy_out(_policy_for_holder(db, settings, policy_number, s), settings)


@router.get("/{policy_number}/certificate.pdf")
def get_certificate(policy_number: str, s: str, db: Session = Depends(get_db),
                    settings: Settings = Depends(get_settings)):
    policy = _policy_for_holder(db, settings, policy_number, s)
    if not policy.pdf_path or not Path(policy.pdf_path).exists():
        raise HTTPException(404, "certificate file missing")
    return FileResponse(policy.pdf_path, media_type="application/pdf", filename=f"{policy_number}.pdf")