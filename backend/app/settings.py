"""Backend settings, read from environment variables or the .env file in the project root."""
from pathlib import Path
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from insurance_core.settings import MODEL_PATH, PROJECT_ROOT


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore", protected_namespaces=())

    database_url: str = f"sqlite:///{PROJECT_ROOT / 'dev.db'}"
    policy_signing_key: str                                   # REQUIRED: the app refuses to start without it
    verify_base_url: str = "http://localhost:5173/verify"     # where the QR code points (the frontend page)
    api_base_url: str = "http://localhost:8000"
    pdf_storage_dir: Path = PROJECT_ROOT / "backend" / "storage" / "policies"
    model_path: Path = MODEL_PATH
    timezone: str = "Africa/Lagos"
    quote_valid_hours: int = 72
    frontend_origins: list[str] = ["http://localhost:5173"]

    # Payments
    payment_mode: Literal["paystack", "simulated"] = "paystack"   # "simulated" = tests/offline demos only
    paystack_secret_key: str | None = None
    paystack_base_url: str = "https://api.paystack.co"
    paystack_callback_url: str | None = None                  # default: {api_base_url}/payments/callback
    allow_live_keys: bool = False                             # prototype: refuse to move real money

    # Brokers: a single shared token (no per-broker accounts yet -- see docs/assumptions.md).
    # Not required to start the app; only checked when a /broker route is actually called, and
    # since no correct token can ever match an unset one, leaving it unset just means every
    # broker route refuses everyone (safe default, not a startup error).
    broker_api_token: str | None = None

    @field_validator("broker_api_token")
    @classmethod
    def broker_token_must_be_long_enough(cls, value: str | None) -> str | None:
        if value is not None and len(value) < 32:
            raise ValueError("BROKER_API_TOKEN must be at least 32 characters when set")
        return value

    @field_validator("policy_signing_key")
    @classmethod
    def key_must_be_long(cls, value: str) -> str:
        if len(value) < 32 or value.startswith("replace-with"):
            raise ValueError("POLICY_SIGNING_KEY must be a real random key of at least 32 characters. "
                             "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\"")
        return value

    @model_validator(mode="after")
    def check_payment_settings(self):
        if self.payment_mode == "paystack":
            key = self.paystack_secret_key or ""
            if not key.startswith(("sk_test_", "sk_live_")):
                raise ValueError("PAYSTACK_SECRET_KEY must be set (sk_test_...) when PAYMENT_MODE=paystack")
            if key.startswith("sk_live_") and not self.allow_live_keys:
                raise ValueError("A LIVE Paystack key was supplied, but this prototype only allows test keys "
                                 "(set ALLOW_LIVE_KEYS=true only for a real, licensed deployment)")
        if self.paystack_callback_url is None:
            self.paystack_callback_url = f"{self.api_base_url}/payments/callback"
        return self

    @property
    def signing_key_bytes(self) -> bytes:
        return self.policy_signing_key.encode()