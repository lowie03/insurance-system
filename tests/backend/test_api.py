"""The whole flow over HTTP: quote -> issue -> verify -> download (simulated payments).

Each test gets a fresh app with a temporary database and PDF folder, so tests never touch dev.db.
"""
import statistics

import pytest

from insurance_core.issuance.numbering import is_well_formed
from tests.backend.helpers import MODEL_PRODUCTS, make_client, quote_body


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["model_version"] == "ng_recommender_v1"


def test_quote_matches_core_results(client, customers):
    response = client.post("/quotes", json=quote_body(customers, "NG-SYN-00021"))
    assert response.status_code == 201
    quote = response.json()
    assert [r["product"] for r in quote["recommendations"]] == ["HCN", "HMC", "SHP"]
    assert quote["recommendations"][0]["product_name"] == "Home & Contents"
    assert quote["recommendations"][0]["breakdown"][-1] == {"step": "building ₦17,490,000 x 0.15%",
                                                            "running_total_ngn": 29_600.0}
    assert quote["customer_id"].startswith("CUS-")


@pytest.mark.parametrize("change, message", [
    ({"age": 10}, "greater than or equal to 18"),
    ({"owns_vehicle": True}, "required when owns_vehicle is true"),
    ({"favourite_colour": "blue"}, "Extra inputs are not permitted"),
    ({"owned_products": ["XYZ"]}, "unknown products"),
])
def test_bad_profiles_are_rejected(client, customers, change, message):
    body = quote_body(customers, "NG-SYN-00021")
    body["profile"].update(change)
    response = client.post("/quotes", json=body)
    assert response.status_code == 422
    assert message in response.text


def test_full_flow_quote_issue_verify_download(client, customers):
    quote = client.post("/quotes", json=quote_body(customers, "NG-SYN-00021")).json()
    response = client.post("/policies", json={"quote_id": quote["quote_id"],
                                              "items": [{"product_code": "HCN"}],
                                              "payment_reference": "SIM-0001"})
    assert response.status_code == 201
    policy = response.json()[0]
    assert policy["policy_number"].startswith("NGI-HCN-")
    assert is_well_formed(policy["policy_number"])
    assert (policy["payment_plan"], policy["payment_ngn"], policy["total_ngn"]) == ("monthly", 2_590, 31_080)

    # Public verification: status + product + expiry only, nothing personal
    number, sig = policy["policy_number"], policy["signature"]
    verified = client.get(f"/verify/{number}", params={"s": sig}).json()
    assert verified == {"status": "VALID", "product_name": "Home & Contents", "valid_until": policy["end_date"]}
    assert client.get(f"/verify/{number}", params={"s": "0" * 16}).json() == {
        "status": "SIGNATURE_MISMATCH", "product_name": None, "valid_until": None}

    # The certificate needs the signature; without it the policy "doesn't exist"
    pdf = client.get(f"/policies/{number}/certificate.pdf", params={"s": sig})
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert client.get(f"/policies/{number}/certificate.pdf", params={"s": "wrong"}).status_code == 404


def test_basket_preview_combines_pricing_without_saving_anything(client, customers):
    quote = client.post("/quotes", json=quote_body(customers, "NG-SYN-00021")).json()
    response = client.post(f"/quotes/{quote['quote_id']}/basket",
                           json={"items": [{"product_code": "HCN"}, {"product_code": "HMC"},
                                          {"product_code": "SHP"}]})
    assert response.status_code == 200
    basket = response.json()
    assert {l["product"] for l in basket["lines"]} == {"HCN", "HMC", "SHP"}
    assert basket["first_payment_ngn"] == pytest.approx(2_590 + 4_810 + 15_000)
    assert basket["total_annual_ngn"] == pytest.approx(31_080 + 57_750 + 15_000)
    # a preview never writes anything: the same quote can be previewed again with a different basket
    again = client.post(f"/quotes/{quote['quote_id']}/basket", json={"items": [{"product_code": "SHP"}]})
    assert again.status_code == 200


def test_basket_issuance_yields_one_policy_per_product(client, customers):
    quote = client.post("/quotes", json=quote_body(customers, "NG-SYN-00021")).json()
    response = client.post("/policies", json={"quote_id": quote["quote_id"],
                                              "items": [{"product_code": "HCN"}, {"product_code": "SHP"}],
                                              "payment_reference": "SIM-BASKET-1"})
    assert response.status_code == 201
    policies = response.json()
    assert {p["product_code"] for p in policies} == {"HCN", "SHP"}
    assert len({p["policy_number"] for p in policies}) == 2          # distinct numbers
    for p in policies:
        pdf = client.get(f"/policies/{p['policy_number']}/certificate.pdf", params={"s": p["signature"]})
        assert pdf.content.startswith(b"%PDF")


def test_buying_the_same_product_twice_from_one_quote_is_refused(client, customers):
    quote = client.post("/quotes", json=quote_body(customers, "NG-SYN-00021")).json()
    body = {"quote_id": quote["quote_id"], "items": [{"product_code": "HCN"}]}
    first = client.post("/policies", json={**body, "payment_reference": "SIM-DUP-1"})
    assert first.status_code == 201

    second = client.post("/policies", json={**body, "payment_reference": "SIM-DUP-2"})
    assert second.status_code == 409
    assert "already has an active policy" in second.json()["detail"]


def test_buying_a_group_alternative_after_the_original_is_refused(client, customers):
    # NG-SYN-00224: income 845,000/month, both HFM and HIN (same mutually-exclusive group) recommended.
    quote = client.post("/quotes", json=quote_body(customers, "NG-SYN-00224")).json()
    first = client.post("/policies", json={"quote_id": quote["quote_id"], "items": [{"product_code": "HFM"}],
                                           "payment_reference": "SIM-GROUP-1"})
    assert first.status_code == 201

    conflict = client.post("/policies", json={"quote_id": quote["quote_id"], "items": [{"product_code": "HIN"}],
                                              "payment_reference": "SIM-GROUP-2"})
    assert conflict.status_code == 409
    assert "conflicts with HFM" in conflict.json()["detail"]


def test_ineligible_product_is_refused(client, customers):
    quote = client.post("/quotes", json=quote_body(customers, "NG-SYN-00021")).json()
    response = client.post("/policies", json={"quote_id": quote["quote_id"],
                                              "items": [{"product_code": "MTP"}],
                                              "payment_reference": "SIM-0002"})
    assert response.status_code == 422
    assert "requires a vehicle" in response.json()["detail"]


def test_same_payment_twice_gives_the_same_policy(client, customers):
    quote = client.post("/quotes", json=quote_body(customers, "NG-SYN-00021")).json()
    body = {"quote_id": quote["quote_id"], "items": [{"product_code": "SHP"}], "payment_reference": "SIM-0003"}
    first, second = client.post("/policies", json=body).json(), client.post("/policies", json=body).json()
    assert first[0]["policy_number"] == second[0]["policy_number"]

    # same payment reference, different basket -> refused (not silently swapped for a new policy)
    reused = client.post("/policies", json={**body, "items": [{"product_code": "HCN"}]})
    assert reused.status_code == 422


def test_expired_quote_is_refused(tmp_path, customers):
    with make_client(tmp_path, quote_valid_hours=-1) as client:   # every quote is born expired
        quote = client.post("/quotes", json=quote_body(customers, "NG-SYN-00021")).json()
        response = client.post("/policies", json={"quote_id": quote["quote_id"],
                                                  "items": [{"product_code": "HCN"}],
                                                  "payment_reference": "SIM-0004"})
        assert response.status_code == 410


def test_objective_2_issuance_time_over_http(client, customers):
    """Quote + issue for 20 real prospects, timed end to end through the API."""
    prospects = customers[customers[MODEL_PRODUCTS].sum(axis=1) == 0]
    timings = []
    for i, customer_id in enumerate(prospects.index):
        quote = client.post("/quotes", json=quote_body(customers, customer_id)).json()
        if quote["refer_to_broker"]:
            continue
        policy = client.post("/policies", json={"quote_id": quote["quote_id"],
                                                "items": [{"product_code": quote["recommendations"][0]["product"]}],
                                                "payment_reference": f"SIM-T{i}"})
        assert policy.status_code == 201
        timings.append(float(policy.headers["X-Process-Time"]))
        if len(timings) == 20:
            break
    print(f"\nIssuance over HTTP: median {statistics.median(timings):.3f}s | max {max(timings):.3f}s")
    assert max(timings) < 60