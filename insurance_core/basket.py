"""Validating and pricing a BASKET of products bought together in one payment.

validate_basket() is pure, like the rest of insurance_core: given a fresh recommend() result, the
requested items and the customer's profile, it decides what's allowed and combines pricing across
the whole basket. It knows nothing about quotes, payments or the database — "what's already been
bought on this quote" enters only as `already_committed_ngn` (a budget number) and as 1-flags already
set on `profile` for owned products, exactly like the rest of insurance_core treats ownership.
"""
from insurance_core import config
from insurance_core.issuance.policy import IssuanceError
from insurance_core.pricing import is_compulsory
from insurance_core.profile import has_income, monthly_income


class BasketError(IssuanceError):
    """Raised when the basket as a whole must be refused. The message is safe to show the customer."""


def group_of(product: str) -> str:
    """The name of `product`'s mutually-exclusive group (e.g. "health"), or the product code itself
    if it's in no group. Used both for the within-basket check below and, at the database layer, as
    the value stored on Policy.exclusive_group -- one column both layers agree on the meaning of."""
    groups = config.load("basket")["mutually_exclusive_groups"]
    return next((name for name, members in groups.items() if product in members), product)


def _resolve_line(rec: dict, requested_plan: str | None) -> dict:
    """Pick this line's plan: the requested one if it's viable on its own, else the suggested one."""
    notes = []
    option = None
    if requested_plan:
        option = next((o for o in rec["payment_options"] if o["plan"] == requested_plan), None)
        if option is None:
            raise BasketError(f"{rec['product']}: unknown payment plan {requested_plan!r}")
        if not (option["fits_budget"] and option["fits_cash_flow"]):
            notes.append(f"{requested_plan} doesn't fit on its own; using {rec['suggested_plan']} instead")
            option = None
    if option is None:
        option = next(o for o in rec["payment_options"] if o["plan"] == rec["suggested_plan"])
    return {
        "product": rec["product"], "premium_ngn": rec["premium_ngn"], "breakdown": rec["breakdown"],
        "payment_plan": option["plan"], "payment_ngn": option["payment_ngn"], "total_ngn": option["total_ngn"],
        "notes": notes + list(rec["notes"]),
    }


def _combined_budget_ok(lines: list, budget_ngn: float | None, already_committed_ngn: float) -> bool:
    """Compulsory products (e.g. MTP) never cause a refusal on their own: only the NON-compulsory
    lines need to fit within what's left of the budget after compulsory costs. A basket with no
    non-compulsory lines at all (e.g. just MTP) is therefore always allowed, however much it costs."""
    if budget_ngn is None:
        return True
    non_compulsory_lines = [l for l in lines if not is_compulsory(l["product"])]
    if not non_compulsory_lines:
        return True
    compulsory = sum(l["total_ngn"] for l in lines if is_compulsory(l["product"]))
    non_compulsory = sum(l["total_ngn"] for l in non_compulsory_lines)
    return non_compulsory + already_committed_ngn <= max(budget_ngn - compulsory, 0)


def _switch_to_monthly(line: dict, rec: dict) -> dict:
    monthly = next(o for o in rec["payment_options"] if o["plan"] == "monthly")
    return {**line, "payment_plan": "monthly", "payment_ngn": monthly["payment_ngn"],
           "total_ngn": monthly["total_ngn"],
           "notes": line["notes"] + ["switched to monthly: the basket's combined single payment "
                                     "was more than your monthly budget allows"]}


def validate_basket(result: dict, items: list, profile: dict, already_committed_ngn: float = 0.0) -> dict:
    cfg = config.load("basket")
    max_items = cfg["max_items"]
    groups = cfg["mutually_exclusive_groups"]

    if not items:
        raise BasketError("the basket is empty")
    codes = [i["product_code"] for i in items]
    if len(codes) != len(set(codes)):
        raise BasketError("the basket has the same product more than once")
    if len(items) > max_items:
        raise BasketError(f"a basket can have at most {max_items} products")

    by_product = {r["product"]: r for r in result["recommendations"]}
    excluded_reason = {e["product"]: e["reason"] for e in result["excluded"]}

    lines, recs_by_product, chosen_group = [], {}, {}
    for item in items:
        code = item["product_code"]
        group_name = group_of(code)
        if group_name in groups:                    # a real group, not just the product's own code
            if group_name in chosen_group:
                raise BasketError(f"{code} conflicts with {chosen_group[group_name]} "
                                  f"(choose only one of {', '.join(groups[group_name])})")
            chosen_group[group_name] = code

        rec = by_product.get(code)
        if rec is None:
            reason = excluded_reason.get(code, "product not available for this customer")
            raise BasketError(f"{code} cannot be added to the basket: {reason}")
        recs_by_product[code] = rec
        lines.append(_resolve_line(rec, item.get("payment_plan")))

    known_income = has_income(profile)
    budget_ngn = (config.load("pricing")["affordability"]["max_total_share_of_annual_income"]
                 * monthly_income(profile) * 12) if known_income else None
    notes = [] if known_income else ["income not provided, so combined affordability could not be checked"]

    if not _combined_budget_ok(lines, budget_ngn, already_committed_ngn):
        raise BasketError(f"this basket's combined cost is above what your income supports "
                          f"(budget ₦{budget_ngn:,.0f}/year, already committed ₦{already_committed_ngn:,.0f})")

    # Combined cash flow: switch the largest ANNUAL lines to monthly, one at a time, until the
    # combined first payment fits — but only lines whose own monthly option is itself viable.
    # Compulsory lines (e.g. MTP) count towards the total but, like the budget check, can never be
    # the CAUSE of a refusal: they eat into the limit rather than being measured against it.
    if known_income:
        cash_flow_limit = (config.load("payment_plans")["cash_flow"]["max_single_payment_share_of_monthly_income"]
                           * monthly_income(profile))

        def noncompulsory_first_payment() -> float:
            return sum(l["payment_ngn"] for l in lines if not is_compulsory(l["product"]))

        compulsory_first_payment = sum(l["payment_ngn"] for l in lines if is_compulsory(l["product"]))
        effective_limit = max(cash_flow_limit - compulsory_first_payment, 0)

        switchable = sorted(
            [i for i, l in enumerate(lines) if l["payment_plan"] == "annual" and not is_compulsory(l["product"])
             and next(o for o in recs_by_product[l["product"]]["payment_options"] if o["plan"] == "monthly")
                     ["fits_budget"]
             and next(o for o in recs_by_product[l["product"]]["payment_options"] if o["plan"] == "monthly")
                     ["fits_cash_flow"]],
            key=lambda i: -lines[i]["payment_ngn"])
        for i in switchable:
            if noncompulsory_first_payment() <= effective_limit:
                break
            lines[i] = _switch_to_monthly(lines[i], recs_by_product[lines[i]["product"]])
        if noncompulsory_first_payment() > effective_limit:
            raise BasketError("even split across monthly instalments, this basket's combined first payment "
                              "is more than your monthly budget allows")
        # Switching to monthly raises total cost (instalment loading): re-check the annual budget.
        if not _combined_budget_ok(lines, budget_ngn, already_committed_ngn):
            raise BasketError("switching to monthly instalments to fit your cash flow would push this "
                              "basket's total cost above your annual budget")

    total_annual_ngn = sum(l["total_ngn"] for l in lines)
    return {
        "lines": lines,
        "first_payment_ngn": sum(l["payment_ngn"] for l in lines),
        "total_annual_ngn": total_annual_ngn,
        "budget_ngn": budget_ngn,
        "budget_remaining_ngn": (budget_ngn - already_committed_ngn - total_annual_ngn
                                 if budget_ngn is not None else None),
        "notes": notes,
    }
