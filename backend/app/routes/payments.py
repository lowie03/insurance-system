import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.app.db import repository
from backend.app.dependencies import get_bundle, get_db, get_paystack, get_settings
from backend.app.routes.presenters import policy_out
from backend.app.schemas import PaymentInitIn, PaymentInitOut, PaymentStatusOut
from backend.app.services.issuance_service import QuoteExpired, QuoteNotFound
from backend.app.services.payment_service import (PaymentNotFound, PaymentSetupError, confirm_payment,
                                                  initialize_payment)
from backend.app.services.paystack import PaystackError, webhook_signature_is_valid
from backend.app.settings import Settings
from insurance_core.issuance.policy import IssuanceError

router = APIRouter(prefix="/payments", tags=["payments"])

STATUS_MESSAGES = {
    "initialized": "Waiting for payment to be completed.",
    "issued": "Payment confirmed and policy issued.",
    "failed": "Payment could not be accepted. You have not been issued a policy.",
    "paid_not_issued": "Payment received, but the policy could not be issued automatically. "
                       "A broker will contact you to resolve this.",
}


def _status_out(db: Session, settings: Settings, payment) -> PaymentStatusOut:
    policy = repository.get_policy_by_number(db, payment.policy_number) if payment.policy_number else None
    return PaymentStatusOut(reference=payment.reference, status=payment.status,
                            message=STATUS_MESSAGES[payment.status],
                            policy=policy_out(policy, settings) if policy else None)


@router.post("/initialize", response_model=PaymentInitOut, status_code=201)
def post_initialize(body: PaymentInitIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
                    bundle: dict = Depends(get_bundle), paystack=Depends(get_paystack)):
    """Start paying for one product from a quote. Returns Paystack's checkout link."""
    try:
        payment = initialize_payment(db, settings, bundle, paystack, body.quote_id, body.product_code,
                                     body.payment_plan, body.email)
    except QuoteNotFound:
        raise HTTPException(404, "quote not found")
    except QuoteExpired:
        raise HTTPException(410, "this quote has expired; please request a new one")
    except (IssuanceError, PaymentSetupError) as e:
        raise HTTPException(422, str(e))
    except PaystackError as e:
        raise HTTPException(502, f"payment provider error: {e}")
    return PaymentInitOut(reference=payment.reference, authorization_url=payment.authorization_url,
                          amount_ngn=payment.amount_kobo / 100, payment_plan=payment.payment_plan)


def _confirm(db, settings, bundle, paystack, reference) -> PaymentStatusOut:
    try:
        payment = confirm_payment(db, settings, bundle, paystack, reference)
    except PaymentNotFound:
        raise HTTPException(404, "payment not found")
    except PaystackError as e:
        raise HTTPException(502, f"payment provider error: {e}")
    return _status_out(db, settings, payment)


@router.get("/callback", response_model=PaymentStatusOut)
def get_callback(reference: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
                 bundle: dict = Depends(get_bundle), paystack=Depends(get_paystack)):
    """Where Paystack sends the customer after checkout (?reference=...). The frontend page replaces this later."""
    return _confirm(db, settings, bundle, paystack, reference)


@router.post("/{reference}/verify", response_model=PaymentStatusOut)
def post_verify(reference: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
                bundle: dict = Depends(get_bundle), paystack=Depends(get_paystack)):
    """Ask Paystack again, e.g. if the customer closed the browser before being redirected."""
    return _confirm(db, settings, bundle, paystack, reference)


@router.get("/{reference}", response_model=PaymentStatusOut)
def get_status(reference: str, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    """Current status from OUR database (no call to Paystack). The reference is random, so it acts as a secret."""
    payment = repository.get_payment(db, reference)
    if payment is None:
        raise HTTPException(404, "payment not found")
    return _status_out(db, settings, payment)


@router.post("/webhook", include_in_schema=False)
async def post_webhook(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
                       bundle: dict = Depends(get_bundle), paystack=Depends(get_paystack)):
    """Paystack calls this server-to-server when a payment succeeds.

    - Wrong signature -> 401: it didn't come from Paystack.
    - Handled (or irrelevant) event -> 200, so Paystack stops retrying.
    - Unexpected crash -> 500, so Paystack retries later (it keeps retrying for up to 72 hours).
    """
    raw_body = await request.body()
    if not webhook_signature_is_valid(raw_body, request.headers.get("x-paystack-signature"),
                                      settings.paystack_secret_key or ""):
        raise HTTPException(401, "invalid signature")
    event = json.loads(raw_body)
    if event.get("event") == "charge.success":
        reference = event.get("data", {}).get("reference", "")
        if repository.get_payment(db, reference) is not None:        # ignore payments that aren't ours
            await run_in_threadpool(confirm_payment, db, settings, bundle, paystack, reference)
    return {"received": True}