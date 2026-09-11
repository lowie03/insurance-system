from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.db import repository
from backend.app.dependencies import get_db, get_settings
from backend.app.schemas import VerificationOut
from backend.app.settings import Settings
from insurance_core.catalogue import product_name
from insurance_core.issuance.policy import verification_status

router = APIRouter(prefix="/verify", tags=["verification"])


@router.get("/{policy_number}", response_model=VerificationOut)
def verify(policy_number: str, s: str = "", db: Session = Depends(get_db),
           settings: Settings = Depends(get_settings)):
    """PUBLIC: what scanning the QR code shows. Always 200; the status field carries the answer."""
    policy = repository.get_policy_by_number(db, policy_number)
    record = policy.as_record() if policy else None
    today = datetime.now(ZoneInfo(settings.timezone)).date()
    status = verification_status(policy_number, s, record, settings.signing_key_bytes, today)
    if status in ("VALID", "EXPIRED", "CANCELLED"):
        return VerificationOut(status=status, product_name=product_name(policy.product_code),
                               valid_until=policy.end_date)
    return VerificationOut(status=status)