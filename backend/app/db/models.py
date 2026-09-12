"""Database tables."""
from sqlalchemy import JSON, Float, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.session import Base


class Quote(Base):
    """A saved recommendation. Issuance works from the profile stored HERE, never from the browser."""
    __tablename__ = "quotes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(20), index=True)
    full_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(20))
    profile: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(32))
    expires_at: Mapped[str] = mapped_column(String(32))
    # result["refer_reason"], duplicated out of the JSON blob and indexed so the broker queue can
    # query "which quotes need a broker" directly instead of loading + parsing every quote's JSON.
    refer_reason: Mapped[str | None] = mapped_column(String(64), index=True)
    referral_outcome: Mapped[str | None] = mapped_column(String(20))
    referral_note: Mapped[str | None] = mapped_column(String(1000))
    referral_resolved_at: Mapped[str | None] = mapped_column(String(32))


class Policy(Base):
    __tablename__ = "policies"
    __table_args__ = (
        # One payment can now cover a whole basket: it may yield several policies, but never more
        # than one per product (that's what protects against the same payment issuing HCN twice).
        UniqueConstraint("payment_reference", "product_code", name="uq_policy_payment_product"),
        # The database-level twin of duplicate_check.check_no_duplicate_products: a PARTIAL index
        # (only rows where status='active') so it says nothing about pending/cancelled/expired
        # policies, but refuses a second ACTIVE policy in the same exclusive_group on the same quote
        # even if two payment confirmations race past the application-level check concurrently.
        Index("uq_active_policy_per_quote_group", "quote_id", "exclusive_group", unique=True,
             sqlite_where=text("status = 'active'"), postgresql_where=text("status = 'active'")),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)   # the policy sequence number
    policy_number: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    quote_id: Mapped[str] = mapped_column(ForeignKey("quotes.id"))
    customer_id: Mapped[str] = mapped_column(String(20), index=True)
    product_code: Mapped[str] = mapped_column(String(8))
    # insurance_core.basket.group_of(product_code): the product's mutually-exclusive group name
    # (e.g. "health"), or product_code itself if it's in no group. See the partial index above.
    exclusive_group: Mapped[str] = mapped_column(String(20))
    # Float (not Decimal) on purpose: the signature is computed from str(total_ngn), so the value must
    # come back from the database exactly as it went in (31080.0, not Decimal('31080.00')).
    premium_ngn: Mapped[float | None] = mapped_column(Float)
    payment_plan: Mapped[str | None] = mapped_column(String(16))
    payment_ngn: Mapped[float | None] = mapped_column(Float)
    total_ngn: Mapped[float | None] = mapped_column(Float)
    start_date: Mapped[str | None] = mapped_column(String(10))
    end_date: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    signature: Mapped[str | None] = mapped_column(String(64))
    payment_reference: Mapped[str] = mapped_column(String(100), index=True)
    pdf_path: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[str] = mapped_column(String(32))
    # Set by a broker cancelling this policy. Once status != 'active' the partial unique index on
    # (quote_id, exclusive_group) no longer covers this row, so the group can be bought again.
    cancel_reason: Mapped[str | None] = mapped_column(String(300))
    cancel_note: Mapped[str | None] = mapped_column(String(1000))
    cancelled_at: Mapped[str | None] = mapped_column(String(32))

    def as_record(self) -> dict:
        """The plain-dict form that insurance_core's signing and verification functions expect."""
        return {c: getattr(self, c) for c in
                ["policy_number", "customer_id", "product_code", "premium_ngn", "payment_plan", "payment_ngn",
                 "total_ngn", "start_date", "end_date", "status", "signature", "payment_reference", "created_at"]}


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event: Mapped[str] = mapped_column(String(32))
    quote_id: Mapped[str | None] = mapped_column(String(36), index=True)
    policy_number: Mapped[str | None] = mapped_column(String(32), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(32))
    
class Payment(Base):
    """One Paystack transaction covering a whole BASKET (one or more products). A policy is issued
    for each item only after this is confirmed as paid. Per-product detail lives in PaymentItem;
    amount_kobo is the sum of every item's first payment."""
    __tablename__ = "payments"

    reference: Mapped[str] = mapped_column(String(64), primary_key=True)     # we generate it, Paystack echoes it
    quote_id: Mapped[str] = mapped_column(ForeignKey("quotes.id"), index=True)
    amount_kobo: Mapped[int] = mapped_column(Integer)
    email: Mapped[str] = mapped_column(String(200))
    # initialized -> issued | failed | paid_not_issued | abandoned
    #   issued:          every item was confirmed paid and issued
    #   failed:          Paystack reported an amount/currency mismatch
    #   paid_not_issued: customer paid but at least one item couldn't be issued: a broker must resolve
    #                    it (e.g. refund)
    #   abandoned:       superseded by a later payment for the same quote before it was ever paid
    status: Mapped[str] = mapped_column(String(20), default="initialized")
    status_detail: Mapped[str | None] = mapped_column(String(300))
    authorization_url: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[str] = mapped_column(String(32))
    confirmed_at: Mapped[str | None] = mapped_column(String(32))
    # Set by a broker resolving a paid_not_issued (or failed) payment. Distinct from `status`: the
    # outcome a broker records (refunded/issued_manually/no_action) isn't a payment-lifecycle state.
    resolved_outcome: Mapped[str | None] = mapped_column(String(20))
    resolved_note: Mapped[str | None] = mapped_column(String(1000))
    resolved_at: Mapped[str | None] = mapped_column(String(32))


class PaymentItem(Base):
    """One product within a basket payment. Priced and saved at initialization time; policy_number
    is filled in once that product's policy has actually been issued."""
    __tablename__ = "payment_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    payment_reference: Mapped[str] = mapped_column(ForeignKey("payments.reference"), index=True)
    product_code: Mapped[str] = mapped_column(String(8))
    payment_plan: Mapped[str] = mapped_column(String(16))
    first_payment_kobo: Mapped[int] = mapped_column(Integer)
    total_ngn: Mapped[float] = mapped_column(Float)
    policy_number: Mapped[str | None] = mapped_column(String(32))