"""Creating quotes: run the recommender and save the result together with the profile."""
import secrets
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from backend.app.db import repository
from backend.app.db.models import Quote
from backend.app.schemas import QuoteIn
from backend.app.settings import Settings
from insurance_core.recommender import recommend


def new_customer_id() -> str:
    return f"CUS-{secrets.token_hex(4).upper()}"          # e.g. CUS-9F3A0B12


def create_quote(db: Session, settings: Settings, bundle: dict, quote_in: QuoteIn) -> Quote:
    now = datetime.now(ZoneInfo(settings.timezone))
    profile = quote_in.profile.to_core_profile()
    result = recommend(profile, bundle)

    quote = Quote(
        id=str(uuid.uuid4()),
        customer_id=new_customer_id(),
        full_name=quote_in.full_name,
        email=quote_in.email,
        phone=quote_in.phone,
        profile=profile,
        result=result,
        created_at=now.isoformat(timespec="seconds"),
        expires_at=(now + timedelta(hours=settings.quote_valid_hours)).isoformat(timespec="seconds"),
    )
    db.add(quote)
    repository.log_event(db, "quote_created", quote_id=quote.id, created_at=quote.created_at,
                         payload={"model_version": result["model_version"],
                                  "config_versions": result["config_versions"],
                                  "recommended": [r["product"] for r in result["recommendations"]],
                                  "excluded": result["excluded"],
                                  "refer_reason": result["refer_reason"]})
    db.commit()
    return quote