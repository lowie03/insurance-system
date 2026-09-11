"""Objects that routes receive through FastAPI's dependency injection."""
from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from backend.app.settings import Settings


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_bundle(request: Request) -> dict:
    return request.app.state.bundle


def get_db(request: Request) -> Iterator[Session]:
    """One database session per request, always closed afterwards (even if the request fails)."""
    db = request.app.state.session_factory()
    try:
        yield db
    finally:
        db.close()
        
def get_paystack(request: Request):
    return request.app.state.paystack