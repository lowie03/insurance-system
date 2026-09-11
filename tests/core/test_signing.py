from insurance_core.issuance.signing import SIGNATURE_LENGTH, sign, signature_matches

KEY = b"test-key-not-secret"
RECORD = {"policy_number": "NGI-HCN-2026-000001-1", "customer_id": "NG-SYN-00021", "product_code": "HCN",
          "total_ngn": 31080.0, "start_date": "2026-09-11", "end_date": "2027-09-10"}


def test_genuine_signature_verifies():
    signature = sign(RECORD, KEY)
    assert len(signature) == SIGNATURE_LENGTH
    assert signature_matches(RECORD, signature, KEY)


def test_changing_any_signed_field_breaks_the_signature():
    signature = sign(RECORD, KEY)
    for field, new_value in [("total_ngn", 3108.0), ("end_date", "2030-09-10"),
                             ("customer_id", "NG-SYN-99999"), ("product_code", "MCP")]:
        assert not signature_matches({**RECORD, field: new_value}, signature, KEY)


def test_wrong_key_cannot_produce_a_valid_signature():
    forged = sign(RECORD, b"attacker-guess")
    assert not signature_matches(RECORD, forged, KEY)