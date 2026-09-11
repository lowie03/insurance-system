"""Backend settings, read from environment variables or the .env file in the project root."""
from pathlib import Path

from pydantic import field_validator
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

    @field_validator("policy_signing_key")
    @classmethod
    def key_must_be_long(cls, value: str) -> str:
        if len(value) < 32 or value.startswith("replace-with"):
            raise ValueError("POLICY_SIGNING_KEY must be a real random key of at least 32 characters. "
                             "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\"")
        return value

    @property
    def signing_key_bytes(self) -> bytes:
        return self.policy_signing_key.encode()