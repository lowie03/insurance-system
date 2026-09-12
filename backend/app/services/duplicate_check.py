"""Issue 1: stop the same product (or its mutually-exclusive alternative, e.g. HIN vs HFM) from
being bought twice on one quote. This is deliberately separate from insurance_core.basket:
"is this product already active on THIS quote" is database state, not a pricing rule.

This is the APPLICATION-level check: fast, and gives a clear message before any pricing/Paystack
work happens. It can still be raced past by two confirmations landing concurrently -- the database
partial unique index on (quote_id, exclusive_group) WHERE status='active' (see db/models.py) is the
layer that can never be raced past, and issue_basket() turns its IntegrityError into the same
customer-safe outcome (paid_not_issued) if that ever happens.

KNOWN LIMITATION: this only looks within one quote_id. There are no user accounts yet, and
customer_id is generated fresh per quote, so the same person requesting a second quote could
still buy the same product again under a different quote_id. See docs/assumptions.md.
"""
from insurance_core.basket import group_of


class DuplicateProductError(Exception):
    """A clear, customer-safe 409 message."""


def check_no_duplicate_products(active_products: set, requested_codes: list) -> None:
    active_by_group = {group_of(p): p for p in active_products}
    for code in requested_codes:
        if code in active_products:
            raise DuplicateProductError(f"{code} already has an active policy on this quote")
        clash = active_by_group.get(group_of(code))
        if clash:
            raise DuplicateProductError(f"{code} conflicts with {clash}, which already has an "
                                        f"active policy on this quote")
