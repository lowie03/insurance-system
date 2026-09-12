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


def start_payment(client, customers, product="HCN", customer_id="NG-SYN-00021", **extra):
    quote = client.post("/quotes", json={**quote_body(customers, customer_id),
                                         "email": "efe@example.com"}).json()
    response = client.post("/payments/initialize",
                           json={"quote_id": quote["quote_id"], "items": [{"product_code": product, **extra}]})
    return quote, response


def start_basket_payment(client, customers, products, customer_id="NG-SYN-00021"):
    quote = client.post("/quotes", json={**quote_body(customers, customer_id),
                                         "email": "efe@example.com"}).json()
    response = client.post("/payments/initialize", json={"quote_id": quote["quote_id"],
                                                          "items": [{"product_code": p} for p in products]})
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
    assert (body["lines"][0]["payment_plan"], body["amount_ngn"]) == ("monthly", 2_590)   # first instalment
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
    assert status["policies"] == []


def test_paying_then_returning_issues_the_policy(paystack_client, customers):
    client, fake = paystack_client
    _, response = start_payment(client, customers)
    reference = response.json()["reference"]
    fake.customer_pays(reference)

    status = client.get("/payments/callback", params={"reference": reference}).json()
    assert status["status"] == "issued"
    policy = status["policies"][0]
    assert policy["product_code"] == "HCN" and policy["payment_ngn"] == 2_590
    pdf = client.get(f"/policies/{policy['policy_number']}/certificate.pdf", params={"s": policy["signature"]})
    assert pdf.content.startswith(b"%PDF")

    # Redirect, webhook and manual re-check all arriving: still exactly one policy
    again = client.post(f"/payments/{reference}/verify").json()
    assert len(again["policies"]) == 1
    assert again["policies"][0]["policy_number"] == policy["policy_number"]


def test_underpayment_is_rejected(paystack_client, customers):
    client, fake = paystack_client
    _, response = start_payment(client, customers)
    reference = response.json()["reference"]
    fake.customer_pays(reference, amount_kobo=100)          # someone tampered with the checkout amount
    status = client.get("/payments/callback", params={"reference": reference}).json()
    assert status["status"] == "failed"
    assert status["policies"] == []


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


def test_direct_issuance_route_does_not_exist_in_paystack_mode(paystack_client, customers):
    client, _ = paystack_client
    quote, _ = start_payment(client, customers)
    response = client.post("/policies", json={"quote_id": quote["quote_id"],
                                              "items": [{"product_code": "HCN"}],
                                              "payment_reference": "FREE-POLICY-PLEASE"})
    assert response.status_code == 404             # the route simply isn't registered in this mode
    assert "/policies" not in client.get("/openapi.json").json()["paths"] or \
           "post" not in client.get("/openapi.json").json()["paths"].get("/policies", {})


def test_multi_product_payment_issues_one_policy_per_product(paystack_client, customers):
    client, fake = paystack_client
    _, response = start_basket_payment(client, customers, ["HCN", "SHP"])
    assert response.status_code == 201
    body = response.json()
    assert {l["product"] for l in body["lines"]} == {"HCN", "SHP"}
    reference = body["reference"]
    assert fake.transactions[reference]["amount"] == body["amount_ngn"] * 100    # ONE combined charge

    fake.customer_pays(reference)
    status = client.get("/payments/callback", params={"reference": reference}).json()
    assert status["status"] == "issued"
    assert {p["product_code"] for p in status["policies"]} == {"HCN", "SHP"}
    assert len({p["policy_number"] for p in status["policies"]}) == 2
    for p in status["policies"]:
        pdf = client.get(f"/policies/{p['policy_number']}/certificate.pdf", params={"s": p["signature"]})
        assert pdf.content.startswith(b"%PDF")


def test_webhook_and_redirect_for_a_basket_still_yield_exactly_n_policies(paystack_client, customers):
    client, fake = paystack_client
    _, response = start_basket_payment(client, customers, ["HCN", "SHP"])
    reference = response.json()["reference"]
    fake.customer_pays(reference)
    event = {"event": "charge.success", "data": {"reference": reference}}

    assert signed_webhook(client, event).status_code == 200
    redirect = client.get("/payments/callback", params={"reference": reference}).json()
    manual = client.post(f"/payments/{reference}/verify").json()
    assert signed_webhook(client, event).status_code == 200            # Paystack retries: still harmless

    for status in (redirect, manual):
        assert len(status["policies"]) == 2
        assert {p["product_code"] for p in status["policies"]} == {"HCN", "SHP"}


def test_identical_reinit_returns_the_same_reference(paystack_client, customers):
    client, fake = paystack_client
    quote, first = start_basket_payment(client, customers, ["HCN", "SHP"])
    second = client.post("/payments/initialize", json={"quote_id": quote["quote_id"],
                                                        "items": [{"product_code": "HCN"},
                                                                 {"product_code": "SHP"}]})
    assert second.status_code == 201
    assert second.json()["reference"] == first.json()["reference"]
    assert len(fake.transactions) == 1              # no second Paystack transaction was created


def test_overlapping_unpaid_basket_abandons_the_old_payment(paystack_client, customers):
    client, fake = paystack_client
    quote, first = start_basket_payment(client, customers, ["HCN", "SHP"])
    old_reference = first.json()["reference"]

    second = client.post("/payments/initialize",
                         json={"quote_id": quote["quote_id"], "items": [{"product_code": "SHP"}]})
    assert second.status_code == 201
    assert second.json()["reference"] != old_reference

    old_status = client.get(f"/payments/{old_reference}").json()
    assert old_status["status"] == "abandoned"
    # the abandoned payment still has a live checkout link and a still-unpaid, non-conflicting SHP:
    # if the customer pays it anyway, it's issued rather than silently ignored (see the dedicated
    # abandoned-payment tests below for the case where it WOULD conflict with something newer)
    fake.customer_pays(old_reference)
    assert client.post(f"/payments/{old_reference}/verify").json()["status"] == "issued"


def test_overlapping_basket_already_paid_is_confirmed_and_the_new_one_refused(paystack_client, customers):
    client, fake = paystack_client
    quote, first = start_basket_payment(client, customers, ["HCN", "SHP"])
    old_reference = first.json()["reference"]
    fake.customer_pays(old_reference)                # paid, but neither webhook nor redirect has arrived yet

    second = client.post("/payments/initialize",
                         json={"quote_id": quote["quote_id"], "items": [{"product_code": "SHP"}]})
    assert second.status_code == 409
    assert old_reference in second.json()["detail"]
    # the old one got confirmed/issued as a side effect of discovering it was paid
    assert client.get(f"/payments/{old_reference}").json()["status"] == "issued"


def test_a_line_failing_revalidation_after_payment_is_paid_not_issued(paystack_client, customers):
    client, fake = paystack_client
    _, response = start_payment(client, customers, product="SHP")
    reference = response.json()["reference"]
    fake.customer_pays(reference)

    # A rule change between payment and confirmation makes SHP newly ineligible for this profile:
    # lower its config-driven affordability minimum won't do it, so instead simulate a rule tightening
    # by monkeypatching insurance_core.rules.eligibility_failure would reach past the API boundary;
    # instead we simulate "the price changed" by manually raising the saved item's expected amount.
    import backend.app.db.repository as repository
    with client.app.state.session_factory() as db:
        for item in repository.get_payment_items(db, reference):
            item.first_payment_kobo += 100_000_00     # what we "charged" no longer matches any real plan
        db.commit()

    status = client.get("/payments/callback", params={"reference": reference}).json()
    assert status["status"] == "paid_not_issued"
    assert status["policies"] == []


# NG-SYN-00224: income 845,000/month, owns a 2018 car. HFM (100,000 annual) and HCN (140,500 annual)
# are both recommended and don't share a mutually-exclusive group, so a basket with both is valid.
MOTORIST = "NG-SYN-00224"


def test_abandoned_payment_left_unpaid_stays_abandoned(paystack_client, customers):
    client, fake = paystack_client
    quote, first = start_basket_payment(client, customers, ["HFM"], customer_id=MOTORIST)
    old_reference = first.json()["reference"]
    client.post("/payments/initialize",                  # a different basket supersedes it
               json={"quote_id": quote["quote_id"], "items": [{"product_code": "HCN"}]})
    assert client.get(f"/payments/{old_reference}").json()["status"] == "abandoned"

    status = client.post(f"/payments/{old_reference}/verify").json()      # never paid
    assert status["status"] == "abandoned"
    assert status["policies"] == []


def test_abandoned_payment_paid_while_still_valid_is_issued(paystack_client, customers):
    client, fake = paystack_client
    quote, first = start_basket_payment(client, customers, ["HFM"], customer_id=MOTORIST)
    old_reference = first.json()["reference"]
    client.post("/payments/initialize",
               json={"quote_id": quote["quote_id"], "items": [{"product_code": "HCN"}]})
    assert client.get(f"/payments/{old_reference}").json()["status"] == "abandoned"

    fake.customer_pays(old_reference)              # customer pays the stale checkout link anyway
    status = client.post(f"/payments/{old_reference}/verify").json()
    assert status["status"] == "issued"
    assert [p["product_code"] for p in status["policies"]] == ["HFM"]


def test_abandoned_payment_paid_but_conflicts_with_a_newer_issued_basket(paystack_client, customers):
    client, fake = paystack_client
    quote, first = start_basket_payment(client, customers, ["HFM"], customer_id=MOTORIST)
    old_reference = first.json()["reference"]
    second = client.post("/payments/initialize", json={"quote_id": quote["quote_id"],
                                                        "items": [{"product_code": "HFM"},
                                                                 {"product_code": "HCN"}]})
    new_reference = second.json()["reference"]
    assert client.get(f"/payments/{old_reference}").json()["status"] == "abandoned"

    fake.customer_pays(new_reference)
    new_status = client.post(f"/payments/{new_reference}/verify").json()
    assert new_status["status"] == "issued"
    assert {p["product_code"] for p in new_status["policies"]} == {"HFM", "HCN"}

    fake.customer_pays(old_reference)               # customer pays the stale (abandoned) link too, late
    old_status = client.post(f"/payments/{old_reference}/verify").json()
    assert old_status["status"] == "paid_not_issued"
    assert old_status["policies"] == []              # zero NEW policies: HFM already belongs to the newer basket


def test_duplicate_check_at_issuance_time_blocks_the_second_paid_basket(paystack_client, customers):
    """Defense in depth: initialize_payment() normally never lets two "initialized" payments for the
    same quote coexist (it abandons or reuses the older one), so to exercise issue_basket's OWN
    duplicate check -- the thing that actually stops a double-issue if that guard is ever bypassed --
    a second "initialized" payment for the same product is inserted directly."""
    import uuid

    from backend.app.db.models import Payment, PaymentItem

    client, fake = paystack_client
    quote, first = start_basket_payment(client, customers, ["HFM"], customer_id=MOTORIST)
    first_reference = first.json()["reference"]

    second_reference = f"INS-{uuid.uuid4().hex}"
    with client.app.state.session_factory() as db:
        db.add(Payment(reference=second_reference, quote_id=quote["quote_id"], amount_kobo=100_000_00,
                       email="efe@example.com", status="initialized", created_at="2026-01-01T00:00:00+01:00"))
        db.add(PaymentItem(payment_reference=second_reference, product_code="HFM", payment_plan="annual",
                           first_payment_kobo=100_000_00, total_ngn=100_000.0))
        db.commit()
    fake.transactions[second_reference] = {"reference": second_reference, "status": "abandoned",
                                           "amount": 100_000_00, "currency": "NGN"}

    fake.customer_pays(first_reference)
    fake.customer_pays(second_reference)
    first_status = client.post(f"/payments/{first_reference}/verify").json()
    second_status = client.post(f"/payments/{second_reference}/verify").json()

    statuses = {first_status["status"], second_status["status"]}
    assert statuses == {"issued", "paid_not_issued"}
    issued, refused = ((first_status, second_status) if first_status["status"] == "issued"
                       else (second_status, first_status))
    assert [p["product_code"] for p in issued["policies"]] == ["HFM"]
    assert refused["policies"] == []


def test_exclusive_group_index_catches_what_the_app_check_misses(paystack_client, customers, monkeypatch):
    """Hardening test for the database-level guard: with the APPLICATION-level check neutralised,
    the only thing left to stop two active policies in the same group on one quote is the partial
    unique index on (quote_id, exclusive_group) WHERE status='active'. Prove it actually stops it,
    and that issue_basket turns the resulting IntegrityError into a clean paid_not_issued -- not an
    unhandled 500."""
    import backend.app.services.issuance_service as issuance_service
    from backend.app.db.models import Policy
    from insurance_core.basket import group_of

    monkeypatch.setattr(issuance_service, "check_no_duplicate_products", lambda *a, **k: None)

    client, fake = paystack_client
    quote, response = start_payment(client, customers, product="HFM", customer_id=MOTORIST)
    reference = response.json()["reference"]

    # Simulate another payment's confirmation having landed between the (neutralised) app-level
    # check and this basket's own insert: an active HFM policy already exists for this quote by the
    # time issue_basket actually writes.
    with client.app.state.session_factory() as db:
        db.add(Policy(quote_id=quote["quote_id"], customer_id=quote["customer_id"], product_code="HFM",
                      exclusive_group=group_of("HFM"), payment_reference="INS-OTHER", status="active",
                      total_ngn=100_000.0, created_at="2026-01-01T00:00:00+01:00"))
        db.commit()

    fake.customer_pays(reference)
    status = client.post(f"/payments/{reference}/verify").json()
    assert status["status"] == "paid_not_issued"
    assert status["policies"] == []


def test_paystack_mode_requires_a_test_key():
    with pytest.raises(ValidationError, match="PAYSTACK_SECRET_KEY must be set"):
        Settings(_env_file=None, policy_signing_key=TEST_KEY, payment_mode="paystack")
    with pytest.raises(ValidationError, match="only allows test keys"):
        Settings(_env_file=None, policy_signing_key=TEST_KEY, payment_mode="paystack",
                 paystack_secret_key="sk_live_real_money")