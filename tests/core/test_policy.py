from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from insurance_core.issuance.certificate import build_certificate
from insurance_core.issuance.policy import (IssuanceError, new_policy_record, one_year_cover,
                                            select_recommendation, verification_status)
from insurance_core.payments import payment_options
from insurance_core.pricing import quote

KEY = b"test-key-not-secret"
NOW = datetime(2026, 9, 11, 10, 30, tzinfo=ZoneInfo("Africa/Lagos"))


def make_rec(product, profile):
    """A recommendation entry built from pricing alone, so these tests don't need the model."""
    premium, breakdown = quote(product, profile)
    options, chosen = payment_options(premium, profile)
    return {"product": product, "match_score": 0.5, "premium_ngn": premium, "breakdown": breakdown,
            "payment_options": options, "suggested_plan": chosen, "notes": []}


@pytest.fixture
def trader_result(trader):
    return {"recommendations": [make_rec("HCN", trader), make_rec("SHP", trader)],
            "excluded": [{"product": "MTP", "kind": "eligibility", "reason": "requires a vehicle"}]}


def test_one_year_cover():
    assert one_year_cover(date(2026, 9, 11)) == date(2027, 9, 10)
    assert one_year_cover(date(2028, 2, 29)) == date(2029, 2, 28)     # leap day


def test_select_uses_suggested_plan_by_default(trader_result):
    rec, option = select_recommendation(trader_result, "HCN")
    assert option["plan"] == "monthly"


def test_ineligible_product_is_refused_with_its_reason(trader_result):
    with pytest.raises(IssuanceError, match="requires a vehicle"):
        select_recommendation(trader_result, "MTP")


def test_plan_that_breaks_cash_flow_is_refused(trader_result):
    with pytest.raises(IssuanceError, match="doesn't fit"):
        select_recommendation(trader_result, "HCN", plan="annual")    # ₦29,600 lump sum is too big


def test_new_record_matches_colab(trader, trader_result):
    rec, option = select_recommendation(trader_result, "HCN")
    record = new_policy_record(trader, rec, option, seq=1, now=NOW, payment_reference="TEST", key=KEY)
    assert record["policy_number"] == "NGI-HCN-2026-000001-1"
    assert (record["payment_ngn"], record["total_ngn"]) == (2_590, 31_080)
    assert (record["start_date"], record["end_date"]) == ("2026-09-11", "2027-09-10")


def test_verification_outcomes(trader, trader_result):
    rec, option = select_recommendation(trader_result, "HCN")
    record = new_policy_record(trader, rec, option, seq=1, now=NOW, payment_reference="TEST", key=KEY)
    pn, sig = record["policy_number"], record["signature"]
    today = date(2026, 12, 1)
    assert verification_status(pn, sig, record, KEY, today) == "VALID"
    assert verification_status(pn, "0" * 16, record, KEY, today) == "SIGNATURE_MISMATCH"
    assert verification_status("NGI-HCN-2026-000002-1", sig, None, KEY, today) == "INVALID_NUMBER"
    assert verification_status(pn, sig, None, KEY, today) == "NOT_FOUND"
    assert verification_status(pn, sig, {**record, "status": "cancelled"}, KEY, today) == "CANCELLED"
    assert verification_status(pn, sig, record, KEY, date(2027, 9, 11)) == "EXPIRED"


def test_certificate_is_a_pdf(trader, trader_result):
    rec, option = select_recommendation(trader_result, "HCN")
    record = new_policy_record(trader, rec, option, seq=1, now=NOW, payment_reference="TEST", key=KEY)
    pdf = build_certificate(record, rec, trader["full_name"],
                            verify_url=f"http://localhost/verify/{record['policy_number']}?s={record['signature']}")
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 2_000