from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.app.db import repository
from backend.app.dependencies import get_bundle, get_db, get_settings
from backend.app.routes.presenters import policy_out
from backend.app.schemas import PolicyIn, PolicyOut
from backend.app.services.duplicate_check import DuplicateProductError
from backend.app.services.issuance_service import QuoteExpired, QuoteNotFound, issue_basket
from backend.app.settings import Settings
from insurance_core.issuance.policy import IssuanceError
from insurance_core.issuance.signing import signature_matches

router = APIRouter(prefix="/policies", tags=["policies"])

# The direct-issuance route lives on its OWN router, included by main.py only when
# PAYMENT_MODE=simulated -- so with PAYMENT_MODE=paystack the route doesn't exist at all (404, not
# a 403 from inside the handler), and it vanishes from /docs too. Kept separate from `router` so
# nothing here ever mutates a router shared across the many app instances the test suite creates.
simulated_router = APIRouter(prefix="/policies", tags=["policies"])


@simulated_router.post("", response_model=list[PolicyOut], status_code=201)
def post_policy(policy_in: PolicyIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
                bundle: dict = Depends(get_bundle)):
    """SIMULATED-payment issuance, for tests and offline demos only: any payment_reference is
    accepted, no Paystack call is made. Accepts the same basket shape real payments do."""
    items = [item.model_dump() for item in policy_in.items]
    try:
        policies = issue_basket(db, settings, bundle, policy_in.quote_id, items, policy_in.payment_reference)
    except QuoteNotFound:
        raise HTTPException(404, "quote not found")
    except QuoteExpired:
        raise HTTPException(410, "this quote has expired; please request a new one")
    except DuplicateProductError as e:
        raise HTTPException(409, str(e))
    except IssuanceError as e:
        raise HTTPException(422, str(e))
    return [policy_out(p, settings) for p in policies]


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
