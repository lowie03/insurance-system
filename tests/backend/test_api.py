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
    response = client.post("/policies", json={"quote_id": quote["quote_id"], "product_code": "HCN",
                                              "payment_reference": "SIM-0001"})
    assert response.status_code == 201
    policy = response.json()
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


def test_ineligible_product_is_refused(client, customers):
    quote = client.post("/quotes", json=quote_body(customers, "NG-SYN-00021")).json()
    response = client.post("/policies", json={"quote_id": quote["quote_id"], "product_code": "MTP",
                                              "payment_reference": "SIM-0002"})
    assert response.status_code == 422
    assert "requires a vehicle" in response.json()["detail"]


def test_same_payment_twice_gives_the_same_policy(client, customers):
    quote = client.post("/quotes", json=quote_body(customers, "NG-SYN-00021")).json()
    body = {"quote_id": quote["quote_id"], "product_code": "SHP", "payment_reference": "SIM-0003"}
    first, second = client.post("/policies", json=body).json(), client.post("/policies", json=body).json()
    assert first["policy_number"] == second["policy_number"]

    reused = client.post("/policies", json={**body, "product_code": "HCN"})     # same payment, other product
    assert reused.status_code == 422


def test_expired_quote_is_refused(tmp_path, customers):
    with make_client(tmp_path, quote_valid_hours=-1) as client:   # every quote is born expired
        quote = client.post("/quotes", json=quote_body(customers, "NG-SYN-00021")).json()
        response = client.post("/policies", json={"quote_id": quote["quote_id"], "product_code": "HCN",
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
                                                "product_code": quote["recommendations"][0]["product"],
                                                "payment_reference": f"SIM-T{i}"})
        assert policy.status_code == 201
        timings.append(float(policy.headers["X-Process-Time"]))
        if len(timings) == 20:
            break
    print(f"\nIssuance over HTTP: median {statistics.median(timings):.3f}s | max {max(timings):.3f}s")
    assert max(timings) < 60