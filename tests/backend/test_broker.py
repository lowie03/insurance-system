"""Broker routes: access control, the review queue, and the resolve/cancel actions."""
import pytest

from tests.backend.helpers import BROKER_TEST_TOKEN, make_client, quote_body
from tests.backend.test_payments import MOTORIST, paystack_client, start_payment  # noqa: F401 (fixture)

AUTH = {"X-Broker-Token": BROKER_TEST_TOKEN}

CIVIL_SERVANT = "NG-SYN-00012"      # employer HMO -> weak match -> referred (see test_recommender.py)


@pytest.mark.parametrize("method, path, body", [
    ("get", "/broker/queue", None),
    ("post", "/broker/referrals/any-id/resolve", {"outcome": "no_action", "note": "x"}),
    ("post", "/broker/payments/any-ref/resolve", {"outcome": "no_action", "note": "x"}),
    ("post", "/broker/policies/any-number/cancel", {"reason": "x", "note": "x"}),
])
def test_broker_routes_require_a_valid_token(client, method, path, body):
    call = getattr(client, method)
    no_token = call(path, json=body) if body is not None else call(path)
    assert no_token.status_code == 401

    wrong_headers = {"X-Broker-Token": "wrong"}
    wrong_token = call(path, json=body, headers=wrong_headers) if body is not None else call(path, headers=wrong_headers)
    assert wrong_token.status_code == 401


def test_empty_header_is_rejected_even_when_no_token_is_configured(tmp_path):
    """The dangerous case: if the comparison were hmac.compare_digest(header or "", configured or
    ""), an UNSET token ("" vs "") would match an EMPTY header. require_broker avoids this with an
    explicit `not configured` short-circuit that never reaches compare_digest in that case -- prove
    it stays that way."""
    with make_client(tmp_path, broker_api_token=None) as client:
        response = client.get("/broker/queue", headers={"X-Broker-Token": ""})
        assert response.status_code == 401


def test_referred_quote_appears_resolving_removes_it_and_reresolve_conflicts(client, customers):
    quote = client.post("/quotes", json=quote_body(customers, CIVIL_SERVANT)).json()
    assert quote["refer_to_broker"] is True

    queue = client.get("/broker/queue", params={"kind": "referral"}, headers=AUTH).json()
    item = next(i for i in queue["items"] if i["quote_id"] == quote["quote_id"])
    assert item["kind"] == "referral"
    assert item["refer_reason"] == quote["refer_reason"]
    assert [r["product"] for r in item["recommendations"]] == [r["product"] for r in quote["recommendations"]]
    assert [e["product"] for e in item["excluded"]] == [e["product"] for e in quote["excluded"]]

    resolved = client.post(f"/broker/referrals/{quote['quote_id']}/resolve", headers=AUTH,
                           json={"outcome": "advised_subsidy", "note": "told them about the state scheme"})
    assert resolved.status_code == 200
    body = resolved.json()
    assert body["status"] == "resolved" and body["outcome"] == "advised_subsidy"

    queue_after = client.get("/broker/queue", params={"kind": "referral"}, headers=AUTH).json()
    assert quote["quote_id"] not in [i["quote_id"] for i in queue_after["items"]]

    again = client.post(f"/broker/referrals/{quote['quote_id']}/resolve", headers=AUTH,
                        json={"outcome": "no_action", "note": "trying again"})
    assert again.status_code == 409
    assert again.json()["detail"]["outcome"] == "advised_subsidy"


def test_resolving_a_referral_that_was_never_one_is_refused(client, customers):
    quote = client.post("/quotes", json=quote_body(customers, "NG-SYN-00021")).json()     # the trader: not referred
    assert quote["refer_to_broker"] is False

    response = client.post(f"/broker/referrals/{quote['quote_id']}/resolve", headers=AUTH,
                           json={"outcome": "no_action", "note": "x"})
    assert response.status_code == 409


def test_stuck_payment_appears_and_resolving_as_refunded_removes_it(paystack_client, customers):
    client, fake = paystack_client
    _, response = start_payment(client, customers, product="SHP")
    reference = response.json()["reference"]
    fake.customer_pays(reference)

    # Force re-validation to fail after payment, same technique as
    # test_a_line_failing_revalidation_after_payment_is_paid_not_issued in test_payments.py.
    import backend.app.db.repository as repository
    with client.app.state.session_factory() as db:
        for item in repository.get_payment_items(db, reference):
            item.first_payment_kobo += 100_000_00
        db.commit()

    status = client.post(f"/payments/{reference}/verify").json()
    assert status["status"] == "paid_not_issued"

    queue = client.get("/broker/queue", params={"kind": "stuck_payment"}, headers=AUTH).json()
    item = next(i for i in queue["items"] if i["reference"] == reference)
    assert item["kind"] == "stuck_payment"
    assert item["amount_ngn"] == pytest.approx(response.json()["amount_ngn"])
    assert item["reason"]                                     # the price-mismatch detail, non-empty
    assert [l["product_code"] for l in item["lines"]] == ["SHP"]

    resolved = client.post(f"/broker/payments/{reference}/resolve", headers=AUTH,
                           json={"outcome": "refunded", "note": "refunded via the Paystack dashboard"})
    assert resolved.status_code == 200
    assert "does NOT call Paystack" in resolved.json()["message"]

    queue_after = client.get("/broker/queue", params={"kind": "stuck_payment"}, headers=AUTH).json()
    assert reference not in [i["reference"] for i in queue_after["items"]]


def test_failed_payment_appears_read_only(paystack_client, customers):
    client, fake = paystack_client
    _, response = start_payment(client, customers, product="HCN")
    reference = response.json()["reference"]
    fake.customer_pays(reference, amount_kobo=100)            # tampered amount -> "failed"
    status = client.get("/payments/callback", params={"reference": reference}).json()
    assert status["status"] == "failed"

    queue = client.get("/broker/queue", params={"kind": "failed_payment"}, headers=AUTH).json()
    item = next(i for i in queue["items"] if i["reference"] == reference)
    assert item["kind"] == "failed_payment"
    assert item["reason"]

    # no resolve action applies to a failed payment: it's not paid_not_issued
    response = client.post(f"/broker/payments/{reference}/resolve", headers=AUTH,
                           json={"outcome": "no_action", "note": "x"})
    assert response.status_code == 409


def test_cancelling_a_policy_frees_the_group_and_verify_shows_cancelled(client, customers):
    quote = client.post("/quotes", json=quote_body(customers, MOTORIST)).json()
    issued = client.post("/policies", json={"quote_id": quote["quote_id"], "items": [{"product_code": "HFM"}],
                                            "payment_reference": "SIM-CANCEL-1"}).json()[0]
    number, sig = issued["policy_number"], issued["signature"]

    cancel = client.post(f"/broker/policies/{number}/cancel", headers=AUTH,
                         json={"reason": "customer requested cancellation", "note": "confirmed by phone"})
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"

    verified = client.get(f"/verify/{number}", params={"s": sig}).json()
    assert verified["status"] == "CANCELLED"

    pdf = client.get(f"/policies/{number}/certificate.pdf", params={"s": sig})
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    # the group (HFM's "health") is free again on this quote: HIN, the same group, can now be bought
    again = client.post("/policies", json={"quote_id": quote["quote_id"], "items": [{"product_code": "HIN"}],
                                           "payment_reference": "SIM-CANCEL-2"})
    assert again.status_code == 201

    repeat = client.post(f"/broker/policies/{number}/cancel", headers=AUTH, json={"reason": "x", "note": "y"})
    assert repeat.status_code == 409
    assert repeat.json()["detail"]["reason"] == "customer requested cancellation"


def test_queue_filter_and_pagination(client, customers):
    for _ in range(3):
        client.post("/quotes", json=quote_body(customers, CIVIL_SERVANT))

    page1 = client.get("/broker/queue", params={"kind": "referral", "limit": 2}, headers=AUTH).json()
    assert len(page1["items"]) == 2
    assert page1["has_more"] is True
    assert all(i["kind"] == "referral" for i in page1["items"])

    page2 = client.get("/broker/queue", params={"kind": "referral", "limit": 2, "offset": 2},
                       headers=AUTH).json()
    assert len(page2["items"]) == 1
    assert page2["has_more"] is False
    assert {i["quote_id"] for i in page1["items"]}.isdisjoint({i["quote_id"] for i in page2["items"]})
