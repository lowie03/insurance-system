"""Database tables."""
from sqlalchemy import JSON, Float, ForeignKey, Integer, String
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


class Policy(Base):
    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)   # the policy sequence number
    policy_number: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    quote_id: Mapped[str] = mapped_column(ForeignKey("quotes.id"))
    customer_id: Mapped[str] = mapped_column(String(20), index=True)
    product_code: Mapped[str] = mapped_column(String(8))
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
    payment_reference: Mapped[str] = mapped_column(String(100), unique=True)   # one payment -> at most one policy
    pdf_path: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[str] = mapped_column(String(32))

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
    """One Paystack transaction. A policy is issued only after this is confirmed as paid."""
    __tablename__ = "payments"

    reference: Mapped[str] = mapped_column(String(64), primary_key=True)     # we generate it, Paystack echoes it
    quote_id: Mapped[str] = mapped_column(ForeignKey("quotes.id"), index=True)
    product_code: Mapped[str] = mapped_column(String(8))
    payment_plan: Mapped[str] = mapped_column(String(16))
    amount_kobo: Mapped[int] = mapped_column(Integer)
    email: Mapped[str] = mapped_column(String(200))
    # initialized -> issued | failed | paid_not_issued (customer paid but the policy couldn't be issued:
    # a broker must resolve it, e.g. refund)
    status: Mapped[str] = mapped_column(String(20), default="initialized")
    status_detail: Mapped[str | None] = mapped_column(String(300))
    authorization_url: Mapped[str | None] = mapped_column(String(300))
    policy_number: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[str] = mapped_column(String(32))
    confirmed_at: Mapped[str | None] = mapped_column(String(32))