"""HMAC signatures that prove a policy was issued by this system.

The key is always passed in by the caller (the backend reads it from an environment
variable). It is never stored in code, config files, or next to the database.
"""
import hashlib
import hmac

SIGNED_FIELDS = ["policy_number", "customer_id", "product_code", "total_ngn", "start_date", "end_date"]
SIGNATURE_LENGTH = 16          # hex characters = 64 bits: short enough for a QR code, far too many to guess


def sign(record: dict, key: bytes) -> str:
    message = "|".join(str(record[field]) for field in SIGNED_FIELDS)
    return hmac.new(key, message.encode(), hashlib.sha256).hexdigest()[:SIGNATURE_LENGTH]


def signature_matches(record: dict, signature: str, key: bytes) -> bool:
    """Constant-time comparison, so response timing can't leak how much of a guess was right."""
    return hmac.compare_digest(sign(record, key), signature)