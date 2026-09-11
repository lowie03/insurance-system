"""Paystack flow, tested against a FAKE Paystack (a "test double"), so tests need no internet and no
real key. The fake behaves like Paystack's API: initialize -> customer pays -> verify says success."""
import hashlib
import hmac
import json

import pytest
from pydantic import ValidationError

from backend.app.settings import Settings
from tests.backend.helpers import TEST_KEY, make_client, quote_body

PAYSTACK_TEST_SECRET = "sk_test_fake_secret_for_tests"


class FakePaystack:
    def __init__(self):
        self.transactions = {}

    def initialize(self, email, amount_kobo, reference, callback_url, metadata):
        self.transactions[reference] = {"reference": reference, "status": "abandoned",
                                        "amount": amount_kobo, "currency": "NGN"}
        return {"authorization_url": f"https://checkout.paystack.test/{reference}",
                "access_code": "fake", "reference": reference}

    def customer_pays(self, reference, amount_kobo=None):
        tx = self.transactions[reference]
        tx["status"] = "success"
        if amount_kobo is not None:
            tx["amount"] = amount_kobo

    def verify(self, reference):
        return self.transactions[reference]


@pytest.fixture
def paystack_client(tmp_path):
    with make_client(tmp_path, payment_mode="paystack", paystack_secret_key=PAYSTACK_TEST_SECRET) as client:
        fake = FakePaystack()
        client.app.state.paystack = fake          # swap the real client for the fake after startup
        yield client, fake


def start_payment(client, customers, product="HCN", **extra):
    quote = client.post("/quotes", json={**quote_body(customers, "NG-SYN-00021"),
                                         "email": "efe@example.com"}).json()
    response = client.post("/payments/initialize",
                           json={"quote_id": quote["quote_id"], "product_code": product, **extra})
    return quote, response


def signed_webhook(client, event: dict, secret=PAYSTACK_TEST_SECRET):
    raw = json.dumps(event).encode()
    signature = hmac.new(secret.encode(), raw, hashlib.sha512).hexdigest()
    return client.post("/payments/webhook", content=raw,
                       headers={"x-paystack-signature": signature, "content-type": "application/json"})


def test_amount_is_computed_by_the_server(paystack_client, customers):
    client, fake = paystack_client
    _, response = start_payment(client, customers)
    assert response.status_code == 201
    body = response.json()
    assert (body["payment_plan"], body["amount_ngn"]) == ("monthly", 2_590)       # first instalment
    assert fake.transactions[body["reference"]]["amount"] == 259_000             # kobo


def test_cannot_pay_for_an_ineligible_product(paystack_client, customers):
    client, _ = paystack_client
    _, response = start_payment(client, customers, product="MTP")
    assert response.status_code == 422
    assert "requires a vehicle" in response.json()["detail"]


def test_unpaid_payment_issues_nothing(paystack_client, customers):
    client, _ = paystack_client
    _, response = start_payment(client, customers)
    status = client.get("/payments/callback", params={"reference": response.json()["reference"]}).json()
    assert status["status"] == "initialized"
    assert status["policy"] is None


def test_paying_then_returning_issues_the_policy(paystack_client, customers):
    client, fake = paystack_client
    _, response = start_payment(client, customers)
    reference = response.json()["reference"]
    fake.customer_pays(reference)

    status = client.get("/payments/callback", params={"reference": reference}).json()
    assert status["status"] == "issued"
    policy = status["policy"]
    assert policy["product_code"] == "HCN" and policy["payment_ngn"] == 2_590
    pdf = client.get(f"/policies/{policy['policy_number']}/certificate.pdf", params={"s": policy["signature"]})
    assert pdf.content.startswith(b"%PDF")

    # Redirect, webhook and manual re-check all arriving: still exactly one policy
    again = client.post(f"/payments/{reference}/verify").json()
    assert again["policy"]["policy_number"] == policy["policy_number"]


def test_underpayment_is_rejected(paystack_client, customers):
    client, fake = paystack_client
    _, response = start_payment(client, customers)
    reference = response.json()["reference"]
    fake.customer_pays(reference, amount_kobo=100)          # someone tampered with the checkout amount
    status = client.get("/payments/callback", params={"reference": reference}).json()
    assert status["status"] == "failed"
    assert status["policy"] is None


def test_webhook_with_valid_signature_issues_once(paystack_client, customers):
    client, fake = paystack_client
    _, response = start_payment(client, customers)
    reference = response.json()["reference"]
    fake.customer_pays(reference)
    event = {"event": "charge.success", "data": {"reference": reference}}

    assert signed_webhook(client, event).status_code == 200
    assert signed_webhook(client, event).status_code == 200        # Paystack retries: must be harmless
    status = client.get(f"/payments/{reference}").json()
    assert status["status"] == "issued"


def test_webhook_with_wrong_signature_is_rejected(paystack_client, customers):
    client, fake = paystack_client
    _, response = start_payment(client, customers)
    reference = response.json()["reference"]
    fake.customer_pays(reference)
    event = {"event": "charge.success", "data": {"reference": reference}}
    assert signed_webhook(client, event, secret="sk_test_attacker_guess").status_code == 401
    assert client.get(f"/payments/{reference}").json()["status"] == "initialized"


def test_direct_issuance_is_disabled_in_paystack_mode(paystack_client, customers):
    client, _ = paystack_client
    quote, _ = start_payment(client, customers)
    response = client.post("/policies", json={"quote_id": quote["quote_id"], "product_code": "HCN",
                                              "payment_reference": "FREE-POLICY-PLEASE"})
    assert response.status_code == 403


def test_paystack_mode_requires_a_test_key():
    with pytest.raises(ValidationError, match="PAYSTACK_SECRET_KEY must be set"):
        Settings(_env_file=None, policy_signing_key=TEST_KEY, payment_mode="paystack")
    with pytest.raises(ValidationError, match="only allows test keys"):
        Settings(_env_file=None, policy_signing_key=TEST_KEY, payment_mode="paystack",
                 paystack_secret_key="sk_live_real_money")