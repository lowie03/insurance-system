"""Turning core/database objects into API response shapes."""
from backend.app.db.models import Policy, Quote
from backend.app.schemas import PolicyOut, QuoteOut
from backend.app.services.issuance_service import verify_url
from backend.app.settings import Settings
from insurance_core.catalogue import product_name


def quote_out(quote: Quote) -> QuoteOut:
    result = quote.result
    return QuoteOut(
        quote_id=quote.id,
        customer_id=quote.customer_id,
        expires_at=quote.expires_at,
        recommendations=[
            {**r, "product_name": product_name(r["product"]),
             "breakdown": [{"step": s, "running_total_ngn": a} for s, a in r["breakdown"]]}
            for r in result["recommendations"]],
        excluded=[{**e, "product_name": product_name(e["product"])} for e in result["excluded"]],
        refer_to_broker=result["refer_to_broker"],
        refer_reason=result["refer_reason"],
    )


def policy_out(policy: Policy, settings: Settings) -> PolicyOut:
    record = policy.as_record()
    return PolicyOut(
        **{k: record[k] for k in PolicyOut.model_fields if k in record},
        product_name=product_name(policy.product_code),
        certificate_url=(f"{settings.api_base_url}/policies/{policy.policy_number}/certificate.pdf"
                         f"?s={policy.signature}"),
        verify_url=verify_url(settings, record),
    )