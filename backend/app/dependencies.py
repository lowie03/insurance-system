"""Objects that routes receive through FastAPI's dependency injection."""
import hmac
from collections.abc import Iterator

from fastapi import Depends, Header, HTTPException, Request
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


def require_broker(x_broker_token: str | None = Header(default=None, alias="X-Broker-Token"),
                   settings: Settings = Depends(get_settings)) -> None:
    """Every /broker route depends on this. Brokers are the first non-public users, and for now
    that's a single shared token, not per-broker accounts -- compare_digest so a wrong guess can't
    be timed, and an unset token can never match anything, so misconfiguration fails closed."""
    configured = settings.broker_api_token or ""
    if not configured or not hmac.compare_digest(x_broker_token or "", configured):
        raise HTTPException(401, "missing or invalid broker token")