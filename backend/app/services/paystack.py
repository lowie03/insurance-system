"""A small client for the three Paystack features we use: initialize, verify, webhook signatures.

Amounts are in KOBO (the smallest unit): ₦2,590 = 259000.
"""
import hashlib
import hmac

import httpx


class PaystackError(Exception):
    pass


def naira_to_kobo(amount_ngn: float) -> int:
    return int(round(amount_ngn * 100))


def webhook_signature_is_valid(raw_body: bytes, signature: str | None, secret_key: str) -> bool:
    """Paystack signs the RAW request body with HMAC-SHA512 (not SHA-256) using your secret key.
    It must be the exact bytes received: re-serialising parsed JSON can change them and break the check."""
    if not signature:
        return False
    expected = hmac.new(secret_key.encode(), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature)


class PaystackClient:
    def __init__(self, secret_key: str, base_url: str = "https://api.paystack.co", timeout: float = 15.0):
        self._http = httpx.Client(base_url=base_url, timeout=timeout,
                                  headers={"Authorization": f"Bearer {secret_key}"})

    def _data(self, response: httpx.Response) -> dict:
        try:
            body = response.json()
        except ValueError:
            raise PaystackError(f"Paystack returned a non-JSON response (HTTP {response.status_code})")
        if response.status_code >= 400 or not body.get("status"):
            raise PaystackError(body.get("message", f"Paystack error (HTTP {response.status_code})"))
        return body["data"]

    def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as e:                     # network down, timeout, DNS failure...
            raise PaystackError(f"could not reach Paystack: {e.__class__.__name__}") from e
        return self._data(response)

    def initialize(self, email: str, amount_kobo: int, reference: str, callback_url: str, metadata: dict) -> dict:
        """Returns data with authorization_url (the checkout page), access_code and reference."""
        return self._request("POST", "/transaction/initialize", json={
            "email": email, "amount": amount_kobo, "currency": "NGN", "reference": reference,
            "callback_url": callback_url, "metadata": metadata,
        })

    def verify(self, reference: str) -> dict:
        """The authoritative answer: data.status ("success", "failed", "abandoned"...), amount, currency."""
        return self._request("GET", f"/transaction/verify/{reference}")

    def close(self) -> None:
        self._http.close()