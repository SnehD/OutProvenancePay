"""SQLAlchemy models. Money is stored as integer minor units (cents) to stay Decimal-safe."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class ApprovedSeller(Base):
    __tablename__ = "approved_sellers"

    name: Mapped[str] = mapped_column(String(120), primary_key=True)


class AgentManifestRecord(Base):
    """Payload and signature are stored in separate columns so tampering with one is detectable."""

    __tablename__ = "agent_manifests"

    agent_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payload_json: Mapped[str] = mapped_column(Text)
    signature_b64: Mapped[str] = mapped_column(String(200))
    key_id: Mapped[str] = mapped_column(String(64))
    digest_sha256: Mapped[str] = mapped_column(String(64))


class Product(Base):
    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    seller_name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(60))
    price_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    @property
    def price(self) -> Decimal:
        return (Decimal(self.price_cents) / 100).quantize(Decimal("0.01"))


class TransactionIntent(Base):
    """A server-generated purchase intent. All money/seller fields come from the trusted catalogue."""

    __tablename__ = "transaction_intents"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(64))
    manifest_digest: Mapped[str] = mapped_column(String(64))
    product_id: Mapped[str] = mapped_column(String(40))
    product_name: Mapped[str] = mapped_column(String(160))
    seller_name: Mapped[str] = mapped_column(String(120))
    category: Mapped[str] = mapped_column(String(60))
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    policy_version: Mapped[str] = mapped_column(String(40))
    policy_decision: Mapped[str] = mapped_column(String(20))
    details_digest: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(32), index=True)
    paypal_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    paypal_approval_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    paypal_capture_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    paypal_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(400), nullable=True)
    receipt_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class Approval(Base):
    """Internal human approval, bound to a digest of the exact transaction details."""

    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    intent_id: Mapped[str] = mapped_column(String(40), index=True)
    approver: Mapped[str] = mapped_column(String(120))
    details_digest: Mapped[str] = mapped_column(String(64))
    policy_version: Mapped[str] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ReceiptRecord(Base):
    """Signed receipt. Validity is never stored: it is always recomputed from payload + signature."""

    __tablename__ = "receipts"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    intent_id: Mapped[str] = mapped_column(String(40), index=True)
    receipt_type: Mapped[str] = mapped_column(String(32))
    payload_json: Mapped[str] = mapped_column(Text)
    signature_b64: Mapped[str] = mapped_column(String(200))
    key_id: Mapped[str] = mapped_column(String(64))
    digest_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class PaymentAttempt(Base):
    """One execution attempt against the processor (or one agent retry), keyed for idempotency.

    `idempotency_key` is the PayPal-Request-Id actually sent (or the derived key for an agent retry).
    `client_key` is the agent-supplied Idempotency-Key, unique per intent so a replay is recognised.
    """

    __tablename__ = "payment_attempts"
    __table_args__ = (UniqueConstraint("intent_id", "client_key", name="uq_attempt_client_key"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    intent_id: Mapped[str] = mapped_column(String(40), index=True)
    operation: Mapped[str] = mapped_column(String(24))  # create_order | capture | reconcile | agent_retry
    idempotency_key: Mapped[str] = mapped_column(String(120))
    client_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    paypal_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    paypal_capture_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    outcome: Mapped[str] = mapped_column(String(24))  # STARTED | SUCCEEDED | REJECTED | OUTCOME_UNKNOWN | REUSED | RECONCILED
    observed_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    detail: Mapped[str | None] = mapped_column(String(400), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class EvidenceEvent(Base):
    """Signed, hash-linked evidence event (TRACE-inspired, not a conformant TRACE/SCITT implementation).

    Payload and signature live in separate columns; validity is always recomputed, never stored.
    """

    __tablename__ = "evidence_events"
    __table_args__ = (UniqueConstraint("intent_id", "seq", name="uq_evidence_seq"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    intent_id: Mapped[str] = mapped_column(String(40), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(48))
    source: Mapped[str] = mapped_column(String(20))
    payload_json: Mapped[str] = mapped_column(Text)
    signature_b64: Mapped[str] = mapped_column(String(200))
    key_id: Mapped[str] = mapped_column(String(64))
    digest_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime)
