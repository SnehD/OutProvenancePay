"""Agent retry handling: a lost or timed-out response must never turn into a second payment.

`retry_payment` is what an agent calls when it did not hear back. It always works from the ORIGINAL
purchase intent and the state we persisted, never from what the retry request claims:

  * details in the retry that differ from the intent => rejected, unconsumed approval revoked, fresh
    authorization (a new intent) required;
  * CAPTURED                    => the original result is reused (nothing is sent to PayPal);
  * CAPTURE_UNCERTAIN           => reconcile with PayPal first; capture is only re-sent if PayPal proves
                                    no capture exists, and then with the SAME PayPal-Request-Id;
  * PayPal cannot be reached    => stays CAPTURE_UNCERTAIN, reported as PENDING_RECONCILIATION;
  * in-flight work              => refused as a duplicate; the atomic state claims in payments.py decide
                                    the single winner under concurrency.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import update
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import Approval, TransactionIntent
from . import attempts, payments
from . import evidence as ev
from . import paypal as pp
from . import transactions as tx
from .crypto import KeyStore
from .money import InvalidAmount, parse_amount

PENDING = "PENDING_RECONCILIATION"


@dataclass
class RetryResult:
    intent: TransactionIntent
    outcome: str  # REUSED | RECONCILED | COMPLETED | ORDER_CREATED | PENDING_RECONCILIATION | IN_PROGRESS
    message: str
    attempt_id: str
    replay: bool


def altered_fields(intent: TransactionIntent, claimed: dict) -> list[str]:
    """Names of fields in the retry that differ from the approved intent. Values are never echoed."""
    bad: list[str] = []
    if claimed.get("product_id") not in (None, intent.product_id):
        bad.append("product_id")
    if claimed.get("seller_name") not in (None, intent.seller_name):
        bad.append("seller_name")
    if claimed.get("currency") not in (None, intent.currency):
        bad.append("currency")
    if claimed.get("amount") is not None:
        try:
            if parse_amount(claimed["amount"]) != (Decimal(intent.amount_cents) / 100).quantize(Decimal("0.01")):
                bad.append("amount")
        except InvalidAmount:
            bad.append("amount")
    return bad


def _revoke_unused_approvals(session: Session, intent_id: str) -> int:
    now = tx.utcnow()
    res = session.execute(update(Approval).where(Approval.intent_id == intent_id, Approval.used_at.is_(None))
                          .values(used_at=now, expires_at=now))
    session.commit()
    return res.rowcount


def retry_payment(session: Session, keystore: KeyStore, settings: Settings, client: pp.PayPalClient,
                  intent_id: str, client_key: str, claimed: dict | None = None) -> RetryResult:
    intent = tx.get_intent(session, intent_id)

    bad = altered_fields(intent, claimed or {})
    if bad:
        revoked = _revoke_unused_approvals(session, intent.id)
        ev.append(session, keystore, intent.id, "RETRY_REJECTED_ALTERED_DETAILS", ev.SOURCE_INTERNAL,
                  refs={"details_digest": intent.details_digest, "idempotency_key": client_key},
                  status_from=intent.state, status_to=intent.state,
                  note=f"Retry changed {', '.join(bad)}. Rejected; unused approval revoked: {revoked > 0}. "
                       "A new intent and fresh approval are required for different details.")
        raise tx.TxError(409, "RETRY_DETAILS_MISMATCH",
                         "The retry does not match the approved transaction. It was rejected and any unused "
                         "approval was revoked; start a new transaction for different details.",
                         {"altered_fields": bad, "approval_revoked": revoked > 0})

    att, created = attempts.begin_or_get(session, intent.id, "agent_retry", f"agent:{client_key}", client_key)
    ev.append(session, keystore, intent.id, "RETRY_RECEIVED", ev.SOURCE_INTERNAL,
              refs={"attempt_id": att.id, "idempotency_key": client_key, "details_digest": intent.details_digest},
              status_from=intent.state, status_to=intent.state,
              note="Agent retry received." + ("" if created else " Same Idempotency-Key as an earlier retry: replayed, not re-run."))

    def done(outcome: str, message: str, attempt_outcome: str) -> RetryResult:
        if created:  # a replay must not overwrite what the original attempt recorded
            attempts.finish(session, att, attempt_outcome, detail=message)
        session.refresh(intent)
        ev.append(session, keystore, intent.id, "RETRY_RESOLVED", ev.SOURCE_INTERNAL,
                  refs={"attempt_id": att.id, "idempotency_key": client_key, "paypal_order_id": intent.paypal_order_id,
                        "paypal_capture_id": intent.paypal_capture_id},
                  status_to=intent.state, note=f"{outcome}: {message}")
        return RetryResult(intent, outcome, message, att.id, not created)

    if intent.state == tx.CAPTURED:
        return done("REUSED", "Already captured. The original result is returned; nothing was sent to PayPal.", "REUSED")

    if intent.state in (tx.CAPTURING, tx.ORDER_CREATING):
        return done("IN_PROGRESS", "The original operation is still in progress; no second one was started.", "REUSED")

    if intent.state == tx.UNCERTAIN:
        try:
            payments.reconcile(session, keystore, settings, client, intent.id)
        except tx.TxError:
            return done(PENDING, "PayPal could not be asked for the outcome, so it remains unresolved.", "OUTCOME_UNKNOWN")
        session.refresh(intent)
        if intent.state == tx.CAPTURED:
            return done("RECONCILED", "PayPal shows the original capture completed. No second capture was made.", "RECONCILED")
        if intent.state == tx.UNCERTAIN:
            return done(PENDING, "PayPal's status does not settle the outcome yet.", "OUTCOME_UNKNOWN")
        if intent.state != tx.ORDER_CREATED:
            raise tx.TxError(409, "INVALID_STATE", f"After reconciliation the transaction is {intent.state}.")
        # PayPal proved that no capture exists, so one (idempotent) capture may now be sent.

    if intent.state == tx.READY:
        payments.create_order(session, keystore, settings, client, intent.id)  # same PayPal-Request-Id as before
        session.refresh(intent)
        return done("ORDER_CREATED", "Order created (or the original order was returned by PayPal's idempotency).", "SUCCEEDED")

    if intent.state == tx.ORDER_CREATED:
        try:
            payments.capture(session, keystore, settings, client, intent.id)
        except tx.TxError as exc:
            session.refresh(intent)
            if exc.code == "CAPTURE_UNCERTAIN":
                return done(PENDING, "The capture response was not confirmed; reconciliation is required.", "OUTCOME_UNKNOWN")
            if created:
                attempts.finish(session, att, "REJECTED", detail=exc.message)
            raise
        session.refresh(intent)
        return done("COMPLETED", "PayPal confirmed the capture.", "SUCCEEDED")

    raise tx.TxError(409, "INVALID_STATE", f"A payment retry is not possible in state {intent.state}.")
