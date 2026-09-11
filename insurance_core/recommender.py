"""recommend(): the model predicts NEED, the rules decide what can actually be offered.

Pipeline for each product:
  already owned? -> eligibility (hard) -> price -> payment plan / affordability (hard)
  -> suitability (soft) -> rank -> broker referral if nothing strong remains
"""
from insurance_core import config
from insurance_core.evaluation import scores_from_model
from insurance_core.features import build_features, profile_to_frame
from insurance_core.payments import payment_options
from insurance_core.pricing import annual_budget, is_compulsory, quote
from insurance_core.profile import has_income
from insurance_core.rules import apply_suitability, eligibility_failure

REFER_SUBSIDY = "no product is affordable; may qualify for a subsidised state health scheme"
REFER_NOTHING_AFFORDABLE = "no eligible product is affordable at current prices"
REFER_WEAK_MATCH = "no strong match; a broker should review this profile"


def model_scores(profile: dict, bundle: dict) -> dict:
    """{product_code: model score} for the products the model knows."""
    products = bundle["products"]
    X = build_features(profile_to_frame(profile, products), bundle["encoder"], products)
    return dict(zip(products, scores_from_model(bundle["model"], X, products)[0]))


def _evaluate_product(product, profile, score):
    """Returns ("ok", candidate) or ("excluded", {product, kind, reason})."""
    failed = eligibility_failure(product, profile)
    if failed:
        return "excluded", {"product": product, "kind": "eligibility", "reason": failed}

    premium, breakdown = quote(product, profile)
    options, chosen = payment_options(premium, profile)
    notes = []
    if chosen is None:
        if not is_compulsory(product):
            share = config.load("pricing")["affordability"]["max_share_of_annual_income"]
            reason = (f"premium ₦{premium:,.0f} is above {share:.0%} of your yearly income "
                      f"(₦{annual_budget(profile):,.0f})")
            return "excluded", {"product": product, "kind": "affordability", "reason": reason}
        chosen = "monthly"
        notes.append("above the usual affordability limit, but third-party motor cover is required by law")

    if not has_income(profile):
        notes.append("income not provided, so affordability could not be checked")
    if chosen == "monthly":
        notes.append("monthly payments suggested: a single annual payment would strain your monthly budget")
    fallback = config.load("recommender")["fallback_tiers"].get(product)
    if fallback:
        notes.append(fallback["note"])

    score, suitability_notes = apply_suitability(product, profile, score)
    return "ok", {"product": product, "score": float(score), "premium_ngn": premium, "breakdown": breakdown,
                  "payment_options": options, "suggested_plan": chosen, "notes": notes + suitability_notes}


def recommend(profile: dict, bundle: dict, top_k: int | None = None) -> dict:
    cfg = config.load("recommender")
    top_k = top_k or cfg["top_k"]
    scores = model_scores(profile, bundle)

    candidates, excluded = {}, []

    def consider(product, score):
        if profile.get(product) == 1:
            return                                            # already owned
        status, result = _evaluate_product(product, profile, score)
        if status == "ok":
            candidates[product] = result
        else:
            excluded.append(result)

    for product in bundle["products"]:
        consider(product, scores[product])

    # Fallback tiers (e.g. Micro Health): only if none of the products they replace survived,
    # and the customer doesn't already own one of them. Scored by the replaced products' need signal.
    for product, tier in cfg["fallback_tiers"].items():
        replaced = tier["replaces"]
        if not any(r in candidates or profile.get(r) == 1 for r in replaced):
            consider(product, sum(scores[r] for r in replaced))

    ranked = sorted(candidates.values(), key=lambda c: -c["score"])[:top_k]
    recommendations = [{"product": c["product"], "match_score": round(c["score"], 3),
                        **{k: v for k, v in c.items() if k not in ("product", "score")}} for c in ranked]

    fallback_codes = set(cfg["fallback_tiers"])
    fallback_unaffordable = any(e["product"] in fallback_codes and e["kind"] == "affordability" for e in excluded)
    if not recommendations:
        refer_reason = REFER_SUBSIDY if fallback_unaffordable else REFER_NOTHING_AFFORDABLE
    elif recommendations[0]["match_score"] < cfg["min_match"]:
        refer_reason = REFER_WEAK_MATCH
    else:
        refer_reason = None

    return {
        "recommendations": recommendations,
        "excluded": excluded,
        "refer_to_broker": refer_reason is not None,
        "refer_reason": refer_reason,
        "model_version": bundle["model_version"],
        "config_versions": config.versions(),
    }