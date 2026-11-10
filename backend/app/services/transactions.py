"""Transaction intents, internal human approval and the shared "is this still safe?" validation.

Internal approval (this module) is distinct from PayPal's buyer approval (services/payments.py).

State machine (allowed transitions only):
  AWAITING_INTERNAL_APPROVAL -> READY_FOR_PAYMENT            (explicit approval, one-time use)
  READY_FOR_PAYMENT          -> ORDER_CREATING -> ORDER_CREATED | READY_FOR_PAYMENT (create failed)
  ORDER_CREATED              -> CAPTURING -> CAPTURED | CAPTURE_UNCERTAIN | FAILED | ORDER_CREATED
  CAPTURE_UNCERTAIN          -> CAPTURED | ORDER_CREATED (only after PayPal status reconciliation)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import update
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import Approval, TransactionIntent
from . import catalogue, evidence, policy
from .crypto import KeyStore, digest_of
from .manifest import verify_stored_manifest

AWAITING_APPROVAL = "AWAITING_INTERNAL_APPROVAL"
READY = "READY_FOR_PAYMENT"
ORDER_CREATING = "ORDER_CREATING"
ORDER_CREATED = "ORDER_CREATED"
CAPTURING = "CAPTURING"
CAPTURED = "CAPTURED"
UNCERTAIN = "CAPTURE_UNCERTAIN"
FAILED = "FAILED"

ALLOWED_TRANSITIONS = {
    AWAITING_APPROVAL: {READY},
    READY: {ORDER_CREATING},
    ORDER_CREATING: {ORDER_CREATED, READY, FAILED},
    ORDER_CREATED: {CAPTURING},
    CAPTURING: {CAPTURED, UNCERTAIN, FAILED, ORDER_CREATED},
    UNCERTAIN: {CAPTURED, ORDER_CREATED, FAILED},
}


class TxError(Exception):
    def __init__(self, status: int, code: str, message: str, extra: dict | None = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra or {}


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


def details_dict(*, intent_id: str, agent_id: str, manifest_digest: str, result: policy.PolicyResult, category: str) -> dict:
    """The exact data an approval/receipt is bound to. Amounts are strings (never floats)."""
    return {
        "intent_id": intent_id,
        "agent_id": agent_id,
        "manifest_digest": manifest_digest,
        "product_id": result.product_id,
        "product_name": result.product_name,
        "seller_name": result.seller_name,
        "category": category,
        "amount": f"{result.amount:.2f}",
        "currency": result.currency,
        "policy_version": result.policy_version,
        "policy_decision": result.decision.value,
    }


def transition(session: Session, intent_id: str, from_states: set[str], to_state: str, **fields) -> bool:
    """Atomic compare-and-set on state. Returns True only for the single caller that wins the race."""
    for s in from_states:
        if to_state not in ALLOWED_TRANSITIONS.get(s, set()):
            raise AssertionError(f"Illegal transition {s} -> {to_state}")
    res = session.execute(
        update(TransactionIntent)
        .where(TransactionIntent.id == intent_id, TransactionIntent.state.in_(from_states))
        .values(state=to_state, updated_at=utcnow(), **fields)
    )
    session.commit()
    return res.rowcount == 1


def create_intent(session: Session, keystore: KeyStore, agent_id: str, product_id: str,
                  claimed_seller: str | None = None, claimed_amount=None, currency: str = "USD") -> TransactionIntent:
    manifest_result, manifest = verify_stored_manifest(session, keystore, agent_id)
    if not manifest_result.valid or manifest is None:
        raise TxError(403, "MANIFEST_INVALID", f"Agent manifest rejected: {manifest_result.reason}")
    if "propose_purchase" not in manifest["capabilities"]:
        raise TxError(403, "CAPABILITY_MISSING", "Agent manifest does not declare the propose_purchase capability.")

    result = policy.evaluate_purchase(session, product_id, claimed_seller=claimed_seller,
                                      claimed_amount=claimed_amount, currency=currency)
    if result.decision == policy.Decision.DENY:
        raise TxError(403, "POLICY_DENIED", result.reasons[0], {"policy": result.to_dict()})
    product = catalogue.get_product(session, product_id)
    assert product is not None
    if product.category not in manifest["allowed_transaction_categories"]:
        raise TxError(403, "CATEGORY_NOT_ALLOWED",
                      f"Manifest does not allow category '{product.category}'.")

    intent_id = _new_id("txn")
    details = details_dict(intent_id=intent_id, agent_id=agent_id, manifest_digest=manifest_result.digest_sha256 or "",
                           result=result, category=product.category)
    now = utcnow()
    intent = TransactionIntent(
        id=intent_id, agent_id=agent_id, manifest_digest=manifest_result.digest_sha256 or "",
        product_id=product.id, product_name=product.name, seller_name=product.seller_name,
        category=product.category, amount_cents=product.price_cents, currency=product.currency,
        policy_version=result.policy_version, policy_decision=result.decision.value,
        details_digest=digest_of(details),
        state=AWAITING_APPROVAL if result.decision == policy.Decision.REQUIRE_APPROVAL else READY,
        created_at=now, updated_at=now,
    )
    session.add(intent)
    session.commit()
    evidence.append(session, keystore, intent.id, "INTENT_CREATED", evidence.SOURCE_INTERNAL,
                    refs={"details_digest": intent.details_digest}, status_to=intent.state,
                    note=f"Server-side policy decision: {intent.policy_decision} ({intent.policy_version}).")
    return intent


def get_intent(session: Session, intent_id: str) -> TransactionIntent:
    intent = session.get(TransactionIntent, intent_id)
    if intent is None:
        raise TxError(404, "NOT_FOUND", "Unknown transaction intent.")
    return intent


def current_digest(session: Session, keystore: KeyStore, intent: TransactionIntent) -> tuple[str, policy.PolicyResult]:
    """Recompute the details digest from the trusted catalogue and manifest *right now*."""
    manifest_result, _ = verify_stored_manifest(session, keystore, intent.agent_id)
    if not manifest_result.valid:
        raise TxError(403, "MANIFEST_INVALID", f"Agent manifest rejected: {manifest_result.reason}")
    result = policy.evaluate_purchase(session, intent.product_id, currency=intent.currency)
    if result.decision == policy.Decision.DENY:
        raise TxError(403, "POLICY_DENIED", result.reasons[0], {"policy": result.to_dict()})
    product = catalogue.get_product(session, intent.product_id)
    details = details_dict(intent_id=intent.id, agent_id=intent.agent_id,
                           manifest_digest=manifest_result.digest_sha256 or "", result=result,
                           category=product.category if product else "")
    return digest_of(details), result


def active_approval(session: Session, intent_id: str) -> Approval | None:
    from sqlalchemy import select
    return session.scalars(select(Approval).where(Approval.intent_id == intent_id)
                           .order_by(Approval.created_at.desc())).first()


def approve(session: Session, keystore: KeyStore, settings: Settings, intent_id: str,
            approver: str, confirmed_digest: str) -> Approval:
    """Explicit internal human approval, bound to the digest of the exact details the approver saw."""
    intent = get_intent(session, intent_id)
    if intent.policy_decision != policy.Decision.REQUIRE_APPROVAL.value:
        raise TxError(409, "APPROVAL_NOT_REQUIRED", "This transaction does not require internal approval.")
    if intent.state != AWAITING_APPROVAL:
        raise TxError(409, "ALREADY_APPROVED_OR_PROCESSED",
                      f"Approval is not possible in state {intent.state}; a duplicate approval was refused.")
    digest_now, result = current_digest(session, keystore, intent)
    if digest_now != intent.details_digest:
        raise TxError(409, "DETAILS_CHANGED", "Transaction details or policy changed since the intent was created.")
    if confirmed_digest != intent.details_digest:
        raise TxError(409, "DIGEST_MISMATCH", "The details you approved do not match this transaction.")
    now = utcnow()
    approval = Approval(
        id=_new_id("apr"), intent_id=intent.id, approver=approver, details_digest=digest_now,
        policy_version=result.policy_version, created_at=now,
        expires_at=now + timedelta(seconds=settings.approval_ttl_seconds),
    )
    session.add(approval)
    session.commit()
    if not transition(session, intent.id, {AWAITING_APPROVAL}, READY):
        raise TxError(409, "ALREADY_APPROVED_OR_PROCESSED", "Concurrent approval detected; refused.")
    evidence.append(session, keystore, intent.id, "APPROVAL_GRANTED", evidence.SOURCE_INTERNAL,
                    refs={"approval_id": approval.id, "details_digest": approval.details_digest},
                    status_from=AWAITING_APPROVAL, status_to=READY,
                    note="Internal human approval bound to the details digest; one-time use, expires.")
    return approval


def assert_payable(session: Session, keystore: KeyStore, intent: TransactionIntent, *, consuming: bool) -> Approval | None:
    """Re-validate everything before any money-moving step. Raises TxError on any problem.

    Checks: manifest signature, policy decision, digest equality with current trusted data,
    and (when required) a matching, unexpired, unused approval for this exact digest/policy.
    """
    digest_now, result = current_digest(session, keystore, intent)
    if digest_now != intent.details_digest or result.policy_version != intent.policy_version:
        raise TxError(409, "DETAILS_CHANGED",
                      "Product, seller, amount, currency or policy changed since the intent was created; "
                      "any approval is invalid.")
    if result.decision.value != intent.policy_decision:
        raise TxError(409, "DECISION_CHANGED", "Policy decision changed since the intent was created.")
    if intent.policy_decision != policy.Decision.REQUIRE_APPROVAL.value:
        return None

    approval = active_approval(session, intent.id)
    if approval is None:
        raise TxError(403, "APPROVAL_REQUIRED", "Internal human approval is required before payment.")
    if approval.details_digest != digest_now or approval.policy_version != result.policy_version:
        raise TxError(409, "APPROVAL_INVALIDATED", "Approval no longer matches the transaction details.")
    if consuming:
        if approval.used_at is not None:
            raise TxError(409, "APPROVAL_REPLAYED", "This approval was already used (one-time use).")
        if approval.expires_at <= utcnow():
            raise TxError(409, "APPROVAL_EXPIRED", "Approval has expired; request a new approval.")
    elif approval.used_at is None:
        raise TxError(409, "APPROVAL_NOT_CONSUMED", "Approval has not been consumed by an order.")
    return approval


def consume_approval(session: Session, approval: Approval) -> bool:
    """Atomically mark an approval used. Only one caller can ever succeed."""
    res = session.execute(update(Approval).where(Approval.id == approval.id, Approval.used_at.is_(None))
                          .values(used_at=utcnow()))
    session.commit()
    return res.rowcount == 1


def intent_to_dict(session: Session, intent: TransactionIntent) -> dict:
    approval = active_approval(session, intent.id)
    return {
        "id": intent.id, "agent_id": intent.agent_id, "state": intent.state,
        "product_id": intent.product_id, "product_name": intent.product_name,
        "seller_name": intent.seller_name, "category": intent.category,
        "amount": f"{intent.amount_cents / 100:.2f}", "currency": intent.currency,
        "policy_version": intent.policy_version, "policy_decision": intent.policy_decision,
        "details_digest": intent.details_digest, "manifest_digest": intent.manifest_digest,
        "internal_approval": None if approval is None else {
            "id": approval.id, "approver": approval.approver,
            "expires_at": approval.expires_at.isoformat() + "Z",
            "used": approval.used_at is not None,
        },
        "paypal": {"order_id": intent.paypal_order_id, "capture_id": intent.paypal_capture_id,
                   "status": intent.paypal_status, "approval_url": intent.paypal_approval_url},
        "recovery_status": "PENDING_RECONCILIATION" if intent.state == UNCERTAIN else None,
        "failure_reason": intent.failure_reason, "receipt_id": intent.receipt_id,
        "created_at": intent.created_at.isoformat() + "Z", "updated_at": intent.updated_at.isoformat() + "Z",
        "next_step": _next_step(intent),
    }


def _next_step(intent: TransactionIntent) -> str:
    return {
        AWAITING_APPROVAL: "Internal human approval required (separate from PayPal buyer approval).",
        READY: "Create the PayPal Sandbox order.",
        ORDER_CREATED: "Buyer approves in PayPal Sandbox, then capture.",
        CAPTURED: "Payment confirmed by PayPal. Receipt available.",
        UNCERTAIN: "Payment status uncertain. Reconcile with PayPal before doing anything else.",
        FAILED: "Transaction failed. See failure reason.",
    }.get(intent.state, "In progress.")


