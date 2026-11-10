"""Signed transaction receipts (Ed25519 over canonical JSON) and independent verification.

A valid signature proves the content is unchanged since the backend key signed it. It does NOT
prove every claim is true, nor that goods were delivered.
A PAYMENT_CONFIRMED receipt is only ever issued when PayPal's API confirmed a COMPLETED capture.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import ReceiptRecord, TransactionIntent
from . import evidence
from . import transactions as tx
from .crypto import KeyStore, VerifyResult

RECEIPT_KEY_NAME = "receipt-signer"
RECEIPT_VERSION = "1.0"
TYPE_PAYMENT = "PAYMENT_CONFIRMED"
TYPE_DEV = "DEV_TEST_NO_PAYMENT"

SIGNATURE_NOTE = (
    "A valid signature proves this content matches the signing key and has not changed. It does not "
    "prove that every claim is true or that goods were delivered."
)

REQUIRED_FIELDS = {
    "receipt_version", "receipt_id", "issued_at", "receipt_type", "agent_id", "manifest_digest",
    "policy_version", "policy_decision", "transaction_intent_id", "product_id", "product_name",
    "seller_name", "amount", "currency", "internal_approval_reference", "paypal_order_id",
    "paypal_capture_id", "payment_status", "environment", "notice",
}


def _base_payload(intent: TransactionIntent, session: Session, receipt_id: str) -> dict:
    approval = tx.active_approval(session, intent.id)
    return {
        "receipt_version": RECEIPT_VERSION,
        "receipt_id": receipt_id,
        "issued_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "agent_id": intent.agent_id,
        "manifest_digest": intent.manifest_digest,
        "policy_version": intent.policy_version,
        "policy_decision": intent.policy_decision,
        "transaction_intent_id": intent.id,
        "product_id": intent.product_id,
        "product_name": intent.product_name,
        "seller_name": intent.seller_name,
        "amount": f"{intent.amount_cents / 100:.2f}",
        "currency": intent.currency,
        "internal_approval_reference": approval.id if approval is not None else None,
        # Pins the evidence chain as it stood when this receipt was issued (None if there is none yet).
        "evidence_reference": evidence.head(session, intent.id),
    }


def _store(session: Session, keystore: KeyStore, intent_id: str, payload: dict) -> ReceiptRecord:
    signed = keystore.sign(RECEIPT_KEY_NAME, payload)
    rec = ReceiptRecord(
        id=payload["receipt_id"], intent_id=intent_id, receipt_type=payload["receipt_type"],
        payload_json=json.dumps(payload, sort_keys=True), signature_b64=signed.signature_b64,
        key_id=signed.key_id, digest_sha256=signed.digest_sha256, created_at=tx.utcnow(),
    )
    session.add(rec)
    try:
        session.commit()
    except IntegrityError:  # concurrent request already issued this receipt type for the intent
        session.rollback()
        existing = session.scalars(select(ReceiptRecord).where(
            ReceiptRecord.intent_id == intent_id, ReceiptRecord.receipt_type == payload["receipt_type"])).first()
        if existing is None:
            raise
        return existing
    evidence.append(session, keystore, intent_id, "RECEIPT_ISSUED", evidence.SOURCE_INTERNAL,
                    refs={"receipt_id": rec.id, "paypal_order_id": payload.get("paypal_order_id"),
                          "paypal_capture_id": payload.get("paypal_capture_id")},
                    note=f"{payload['receipt_type']} receipt signed. Payment status: {payload['payment_status']}.")
    return rec


def issue_payment_receipt(session: Session, keystore: KeyStore, intent: TransactionIntent) -> ReceiptRecord:
    """Only for intents PayPal has confirmed as captured. Idempotent."""
    if intent.receipt_id:
        existing = session.get(ReceiptRecord, intent.receipt_id)
        if existing is not None:
            return existing
    if intent.state != tx.CAPTURED or not intent.paypal_capture_id or intent.paypal_status != "COMPLETED":
        raise tx.TxError(409, "NOT_CAPTURED", "A payment receipt requires a capture confirmed by PayPal.")
    payload = _base_payload(intent, session, tx._new_id("rcpt"))
    payload.update({
        "receipt_type": TYPE_PAYMENT, "paypal_order_id": intent.paypal_order_id,
        "paypal_capture_id": intent.paypal_capture_id, "payment_status": "COMPLETED",
        "environment": "paypal-sandbox",
        "notice": "Payment status verified from PayPal's server API at capture time.",
    })
    rec = _store(session, keystore, intent.id, payload)
    intent.receipt_id = rec.id
    session.commit()
    return rec


def issue_dev_receipt(session: Session, keystore: KeyStore, intent: TransactionIntent) -> ReceiptRecord:
    """Clearly labelled receipt for demos/tests. Claims NO payment. Authorises nothing."""
    if intent.state == tx.CAPTURED:
        raise tx.TxError(409, "ALREADY_CAPTURED", "This transaction has a real payment receipt instead.")
    if intent.state in (tx.AWAITING_APPROVAL, tx.FAILED, tx.UNCERTAIN):
        raise tx.TxError(409, "INVALID_STATE", f"No development receipt in state {intent.state}.")
    tx.assert_payable(session, keystore, intent, consuming=True)  # same validation; does not consume
    existing = session.scalars(select(ReceiptRecord).where(
        ReceiptRecord.intent_id == intent.id, ReceiptRecord.receipt_type == TYPE_DEV)).first()
    if existing is not None:
        return existing
    payload = _base_payload(intent, session, tx._new_id("rcpt"))
    payload.update({
        "receipt_type": TYPE_DEV, "paypal_order_id": None, "paypal_capture_id": None,
        "payment_status": "NOT_PAID", "environment": "development-test",
        "notice": "DEVELOPMENT/TEST RECEIPT. No payment occurred. Not proof of purchase.",
    })
    return _store(session, keystore, intent.id, payload)


def check_consistency(payload: dict) -> list[str]:
    """Semantic checks that are independent of the signature."""
    issues = []
    missing = REQUIRED_FIELDS - set(payload)
    if missing:
        issues.append(f"Missing fields: {', '.join(sorted(missing))}")
    if payload.get("receipt_version") != RECEIPT_VERSION:
        issues.append("Unknown receipt_version.")
    kind = payload.get("receipt_type")
    if kind == TYPE_PAYMENT:
        if payload.get("payment_status") != "COMPLETED" or not payload.get("paypal_capture_id"):
            issues.append("PAYMENT_CONFIRMED receipt lacks a COMPLETED status and PayPal capture reference.")
    elif kind == TYPE_DEV:
        if payload.get("payment_status") != "NOT_PAID" or payload.get("paypal_capture_id"):
            issues.append("Development receipt must not claim a payment.")
    else:
        issues.append("Unknown receipt_type.")
    return issues


def verify_receipt(keystore: KeyStore, payload: dict, signature_b64: str, key_id: str) -> dict:
    """Recompute digest and verify the signature from the supplied content only."""
    sig: VerifyResult = keystore.verify(payload, signature_b64, key_id)
    issues = check_consistency(payload) if isinstance(payload, dict) else ["Payload must be a JSON object."]
    return {
        "valid": sig.valid and not issues,
        "signature_valid": sig.valid,
        "signature_reason": sig.reason,
        "consistency_issues": issues,
        "recomputed_digest_sha256": sig.digest_sha256,
        "key_id": key_id,
        "receipt_type": payload.get("receipt_type") if isinstance(payload, dict) else None,
        "note": SIGNATURE_NOTE,
    }


def receipt_document(keystore: KeyStore, rec: ReceiptRecord) -> dict:
    return {
        "payload": json.loads(rec.payload_json),
        "signature_b64": rec.signature_b64,
        "key_id": rec.key_id,
        "algorithm": "Ed25519",
        "digest_sha256": rec.digest_sha256,
        "signer_public_key_b64": keystore.public_key_b64(RECEIPT_KEY_NAME),
        "canonicalization": "JSON, UTF-8, sorted keys, separators (',', ':'), no floats",
    }
