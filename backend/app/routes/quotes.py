from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.db import repository
from backend.app.dependencies import get_bundle, get_db, get_settings
from backend.app.routes.presenters import basket_out, quote_out
from backend.app.schemas import BasketOut, BasketPreviewIn, QuoteIn, QuoteOut
from backend.app.services.duplicate_check import DuplicateProductError
from backend.app.services.issuance_service import QuoteExpired, QuoteNotFound, prepare_basket_selection
from backend.app.services.quote_service import create_quote
from backend.app.settings import Settings
from insurance_core.basket import BasketError

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


@router.post("/{quote_id}/basket", response_model=BasketOut)
def post_basket_preview(quote_id: str, body: BasketPreviewIn, db: Session = Depends(get_db),
                        settings: Settings = Depends(get_settings), bundle: dict = Depends(get_bundle)):
    """Live totals for the frontend's basket screen: same validate_basket() the real payment uses,
    but no Paystack call and nothing is saved."""
    items = [item.model_dump() for item in body.items]
    try:
        _, _, _, basket = prepare_basket_selection(db, bundle, settings, quote_id, items)
    except QuoteNotFound:
        raise HTTPException(404, "quote not found")
    except QuoteExpired:
        raise HTTPException(410, "this quote has expired; please request a new one")
    except DuplicateProductError as e:
        raise HTTPException(409, str(e))
    except BasketError as e:
        raise HTTPException(422, str(e))
    return basket_out(basket)
