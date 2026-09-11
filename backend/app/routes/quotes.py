from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.db import repository
from backend.app.dependencies import get_bundle, get_db, get_settings
from backend.app.routes.presenters import quote_out
from backend.app.schemas import QuoteIn, QuoteOut
from backend.app.services.quote_service import create_quote
from backend.app.settings import Settings

router = APIRouter(prefix="/quotes", tags=["quotes"])


@router.post("", response_model=QuoteOut, status_code=201)
def post_quote(quote_in: QuoteIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
               bundle: dict = Depends(get_bundle)):
    """Submit a profile; get recommendations, exclusions and a quote_id to issue from."""
    return quote_out(create_quote(db, settings, bundle, quote_in))


@router.get("/{quote_id}", response_model=QuoteOut)
def get_quote(quote_id: str, db: Session = Depends(get_db)):
    quote = repository.get_quote(db, quote_id)
    if quote is None:
        raise HTTPException(404, "quote not found")
    return quote_out(quote)