"""Payment orchestration: PayPal order creation, buyer-status check, capture and reconciliation.

PayPal buyer approval (happens on paypal.com) is separate from our internal human approval.
A browser redirect is never proof of payment: only PayPal's server API status counts.

Every money-moving step records a persisted attempt (with the idempotency key used) and signed evidence
events, marked either PAYPAL_OBSERVED (read from PayPal's API) or INTERNAL (our own decision).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..config import Settings
from ..models import PaymentAttempt, TransactionIntent
from . import attempts
from . import evidence as ev
from . import paypal as pp
from . import transactions as tx
from .crypto import KeyStore


def _amount(intent: TransactionIntent) -> str:
    return f"{intent.amount_cents / 100:.2f}"


def _require_configured(settings: Settings) -> None:
    if not settings.paypal_configured:
        raise tx.TxError(503, "PAYPAL_NOT_CONFIGURED",
                         "PayPal Sandbox credentials are not configured. Set PAYPAL_CLIENT_ID and "
                         "PAYPAL_CLIENT_SECRET in backend/.env. No payment was attempted.")


def _paypal_http_error(exc: pp.PayPalError) -> tx.TxError:
    if isinstance(exc, pp.PayPalNotConfigured):
        return tx.TxError(503, "PAYPAL_NOT_CONFIGURED", exc.message)
    if isinstance(exc, pp.PayPalAuthError):
        return tx.TxError(502, "PAYPAL_AUTH_FAILED", exc.message)
    if isinstance(exc, pp.PayPalTimeout):
        return tx.TxError(504, "PAYPAL_UNAVAILABLE", exc.message)
    return tx.TxError(502, "PAYPAL_REJECTED", exc.message, {"paypal_issue": exc.issue, "debug_id": exc.debug_id})


def _observation(order: dict) -> dict:
    cap = pp.first_capture(order)
    return {"order_status": order.get("status"), "capture_status": cap.get("status") if cap else None}


def _refs(intent: TransactionIntent, att: PaymentAttempt | None = None, **extra) -> dict:
    refs = {"details_digest": intent.details_digest, "paypal_order_id": intent.paypal_order_id,
            "paypal_capture_id": intent.paypal_capture_id}
    if att is not None:
        refs.update(attempt_id=att.id, idempotency_key=att.idempotency_key)
    refs.update(extra)
    return refs


def create_order(session: Session, keystore: KeyStore, settings: Settings, client: pp.PayPalClient,
                 intent_id: str) -> TransactionIntent:
    _require_configured(settings)
    intent = tx.get_intent(session, intent_id)
    if intent.state == tx.ORDER_CREATED:
        return intent  # idempotent: duplicate request returns the existing order, creates nothing new
    if intent.state != tx.READY:
        raise tx.TxError(409, "INVALID_STATE", f"Cannot create an order in state {intent.state}.")

    approval = tx.assert_payable(session, keystore, intent, consuming=True)
    if not tx.transition(session, intent.id, {tx.READY}, tx.ORDER_CREATING):
        raise tx.TxError(409, "DUPLICATE_REQUEST", "Another request is already creating this order.")

    amount = _amount(intent)
    request_id = f"opp-order-{intent.id}"  # same key on every retry => PayPal returns the same order
    att = attempts.begin(session, intent.id, "create_order", request_id)
    refs = _refs(intent, att, approval_id=approval.id if approval else None)
    ev.append(session, keystore, intent.id, "ORDER_CREATE_STARTED", ev.SOURCE_INTERNAL, refs=refs,
              status_from=tx.READY, status_to=tx.ORDER_CREATING, note="Order creation attempt started.")
    try:
        order = client.create_order(
            intent_id=intent.id, description=f"{intent.product_name} ({intent.seller_name})",
            amount=amount, currency=intent.currency,
            return_url=f"{settings.frontend_url}/?paypal=return&intent={intent.id}",
            cancel_url=f"{settings.frontend_url}/?paypal=cancel&intent={intent.id}",
            request_id=request_id,
        )
    except pp.PayPalError as exc:
        unknown = exc.ambiguous
        attempts.finish(session, att, "OUTCOME_UNKNOWN" if unknown else "REJECTED", detail=exc.message)
        tx.transition(session, intent.id, {tx.ORDER_CREATING}, tx.READY, failure_reason=exc.message[:390])
        ev.append(session, keystore, intent.id, "ORDER_CREATE_OUTCOME_UNKNOWN" if unknown else "ORDER_CREATE_REJECTED",
                  ev.SOURCE_INTERNAL, refs=refs, status_from=tx.ORDER_CREATING, status_to=tx.READY,
                  note=("No confirmed response, so PayPal may have created the order. Retrying re-sends the same "
                        "PayPal-Request-Id, which makes PayPal return the original order instead of a new one.")
                  if unknown else f"PayPal rejected the request: {exc.message[:200]}")
        raise _paypal_http_error(exc) from exc

    if not pp.order_matches(order, intent_id=intent.id, amount=amount, currency=intent.currency) or not order.get("id"):
        attempts.finish(session, att, "REJECTED", detail="Order did not match trusted details.")
        tx.transition(session, intent.id, {tx.ORDER_CREATING}, tx.FAILED,
                      failure_reason="PayPal order did not match the trusted transaction details.")
        ev.append(session, keystore, intent.id, "ORDER_MISMATCH", ev.SOURCE_INTERNAL, refs=refs,
                  status_from=tx.ORDER_CREATING, status_to=tx.FAILED, note="PayPal's order did not match trusted details.")
        raise tx.TxError(502, "ORDER_MISMATCH", "PayPal's order did not match the trusted transaction details.")

    if approval is not None and not tx.consume_approval(session, approval):
        attempts.finish(session, att, "REJECTED", detail="Approval replay detected.")
        tx.transition(session, intent.id, {tx.ORDER_CREATING}, tx.FAILED, failure_reason="Approval replay detected.")
        ev.append(session, keystore, intent.id, "APPROVAL_REPLAY_BLOCKED", ev.SOURCE_INTERNAL, refs=refs,
                  status_from=tx.ORDER_CREATING, status_to=tx.FAILED, note="Approval was already used.")
        raise tx.TxError(409, "APPROVAL_REPLAYED", "Approval was already used.")
    tx.transition(session, intent.id, {tx.ORDER_CREATING}, tx.ORDER_CREATED, paypal_order_id=order["id"],
                  paypal_approval_url=pp.approval_url(order), paypal_status=order.get("status"), failure_reason=None)
    session.refresh(intent)
    attempts.finish(session, att, "SUCCEEDED", observed_status=order.get("status"), order_id=order["id"])
    if approval is not None:
        ev.append(session, keystore, intent.id, "APPROVAL_CONSUMED", ev.SOURCE_INTERNAL, refs=_refs(intent, att, approval_id=approval.id),
                  note="One-time approval consumed by this order.")
    ev.append(session, keystore, intent.id, "ORDER_CREATED", ev.SOURCE_PAYPAL, refs=_refs(intent, att),
              status_from=tx.ORDER_CREATING, status_to=tx.ORDER_CREATED, observation=_observation(order))
    return intent


def _verified_order(session: Session, client: pp.PayPalClient, intent: TransactionIntent) -> dict:
    order = client.get_order(intent.paypal_order_id)
    if not pp.order_matches(order, intent_id=intent.id, amount=_amount(intent), currency=intent.currency):
        raise tx.TxError(502, "ORDER_MISMATCH", "PayPal's order does not match the trusted transaction details.")
    return order


def refresh_status(session: Session, keystore: KeyStore, settings: Settings, client: pp.PayPalClient,
                   intent_id: str) -> TransactionIntent:
    """Fetch the order from PayPal's server API (not from the browser) and store its status."""
    _require_configured(settings)
    intent = tx.get_intent(session, intent_id)
    if not intent.paypal_order_id:
        raise tx.TxError(409, "NO_ORDER", "No PayPal order exists for this transaction yet.")
    try:
        order = _verified_order(session, client, intent)
    except pp.PayPalError as exc:
        raise _paypal_http_error(exc) from exc
    intent.paypal_status = order.get("status")
    session.commit()
    ev.append(session, keystore, intent.id, "ORDER_STATUS_OBSERVED", ev.SOURCE_PAYPAL, refs=_refs(intent),
              observation=_observation(order))
    return intent


def _record_capture(session: Session, intent: TransactionIntent, order: dict, from_states: set[str]) -> bool:
    """Mark CAPTURED only if PayPal's own data shows a COMPLETED capture."""
    capture = pp.first_capture(order)
    if order.get("status") == "COMPLETED" and capture and capture.get("status") == "COMPLETED":
        return tx.transition(session, intent.id, from_states, tx.CAPTURED, paypal_order_id=intent.paypal_order_id,
                             paypal_capture_id=capture.get("id"), paypal_status="COMPLETED", failure_reason=None)
    return False


def _confirmed(session: Session, keystore: KeyStore, intent: TransactionIntent, att: PaymentAttempt | None,
               order: dict, status_from: str, outcome: str) -> None:
    session.refresh(intent)
    if att is not None:
        attempts.finish(session, att, outcome, observed_status="COMPLETED", capture_id=intent.paypal_capture_id)
    ev.append(session, keystore, intent.id, "CAPTURE_CONFIRMED", ev.SOURCE_PAYPAL, refs=_refs(intent, att),
              status_from=status_from, status_to=tx.CAPTURED, observation=_observation(order),
              note="PayPal's server API reports a COMPLETED capture.")


def _unknown(session: Session, keystore: KeyStore, intent: TransactionIntent, att: PaymentAttempt, reason: str,
             *, paypal_status: str | None = None) -> None:
    fields = {"paypal_status": paypal_status} if paypal_status else {}
    tx.transition(session, intent.id, {tx.CAPTURING}, tx.UNCERTAIN, failure_reason=reason, **fields)
    attempts.finish(session, att, "OUTCOME_UNKNOWN", observed_status=paypal_status, detail=reason)
    ev.append(session, keystore, intent.id, "CAPTURE_OUTCOME_UNKNOWN", ev.SOURCE_INTERNAL, refs=_refs(intent, att),
              status_from=tx.CAPTURING, status_to=tx.UNCERTAIN,
              note="PENDING_RECONCILIATION: success cannot be assumed and failure cannot be assumed. " + reason)


def capture(session: Session, keystore: KeyStore, settings: Settings, client: pp.PayPalClient,
            intent_id: str) -> TransactionIntent:
    _require_configured(settings)
    intent = tx.get_intent(session, intent_id)
    if intent.state == tx.CAPTURED:
        return intent  # idempotent duplicate: nothing is captured twice
    if intent.state == tx.UNCERTAIN:
        raise tx.TxError(409, "CAPTURE_UNCERTAIN",
                         "A previous capture attempt has an unknown outcome. Reconcile with PayPal first; "
                         "capture will not be retried blindly.")
    if intent.state != tx.ORDER_CREATED or not intent.paypal_order_id:
        raise tx.TxError(409, "INVALID_STATE", f"Cannot capture in state {intent.state}.")

    tx.assert_payable(session, keystore, intent, consuming=False)  # re-validate everything first
    if not tx.transition(session, intent.id, {tx.ORDER_CREATED}, tx.CAPTURING):
        raise tx.TxError(409, "DUPLICATE_REQUEST", "Another capture request is already in progress.")

    request_id = f"opp-capture-{intent.id}"  # one key per intent: PayPal treats a repeat as the same capture
    att = attempts.begin(session, intent.id, "capture", request_id, order_id=intent.paypal_order_id)
    ev.append(session, keystore, intent.id, "CAPTURE_STARTED", ev.SOURCE_INTERNAL, refs=_refs(intent, att),
              status_from=tx.ORDER_CREATED, status_to=tx.CAPTURING, note="Capture attempt started after re-validation.")

    try:
        order = _verified_order(session, client, intent)
    except pp.PayPalError as exc:  # nothing was captured yet, so reverting is safe
        attempts.finish(session, att, "REJECTED" if not exc.ambiguous else "OUTCOME_UNKNOWN", detail=exc.message)
        tx.transition(session, intent.id, {tx.CAPTURING}, tx.ORDER_CREATED, failure_reason=exc.message[:390])
        ev.append(session, keystore, intent.id, "PRE_CAPTURE_CHECK_FAILED", ev.SOURCE_INTERNAL, refs=_refs(intent, att),
                  status_from=tx.CAPTURING, status_to=tx.ORDER_CREATED,
                  note="Could not read the order before capturing; no capture request was sent.")
        raise _paypal_http_error(exc) from exc
    except tx.TxError:
        attempts.finish(session, att, "REJECTED", detail="Order mismatch.")
        tx.transition(session, intent.id, {tx.CAPTURING}, tx.FAILED, failure_reason="Order mismatch.")
        ev.append(session, keystore, intent.id, "ORDER_MISMATCH", ev.SOURCE_INTERNAL, refs=_refs(intent, att),
                  status_from=tx.CAPTURING, status_to=tx.FAILED)
        raise
    ev.append(session, keystore, intent.id, "ORDER_STATUS_OBSERVED", ev.SOURCE_PAYPAL, refs=_refs(intent, att),
              observation=_observation(order))

    if order.get("status") == "COMPLETED":  # already captured elsewhere/earlier: record, don't capture again
        if _record_capture(session, intent, order, {tx.CAPTURING}):
            _confirmed(session, keystore, intent, att, order, tx.CAPTURING, "RECONCILED")
            return intent
    elif order.get("status") != "APPROVED":
        attempts.finish(session, att, "REJECTED", observed_status=order.get("status"), detail="Buyer has not approved.")
        tx.transition(session, intent.id, {tx.CAPTURING}, tx.ORDER_CREATED, paypal_status=order.get("status"))
        ev.append(session, keystore, intent.id, "CAPTURE_NOT_SENT", ev.SOURCE_INTERNAL, refs=_refs(intent, att),
                  status_from=tx.CAPTURING, status_to=tx.ORDER_CREATED, note="Buyer has not approved at PayPal yet.")
        raise tx.TxError(409, "BUYER_NOT_APPROVED",
                         f"The buyer has not approved this order in PayPal yet (PayPal status: {order.get('status')}).")

    try:
        result = client.capture_order(intent.paypal_order_id, request_id=request_id)
    except pp.PayPalRejected as exc:
        if exc.issue == "ORDER_ALREADY_CAPTURED":
            _unknown(session, keystore, intent, att, "PayPal reports the order was already captured; reconcile.")
            raise tx.TxError(409, "CAPTURE_UNCERTAIN", "PayPal reports the order was already captured. Reconcile.") from exc
        attempts.finish(session, att, "REJECTED", detail=exc.message)
        tx.transition(session, intent.id, {tx.CAPTURING}, tx.FAILED, failure_reason=exc.message[:390])
        ev.append(session, keystore, intent.id, "CAPTURE_REJECTED", ev.SOURCE_INTERNAL, refs=_refs(intent, att),
                  status_from=tx.CAPTURING, status_to=tx.FAILED, note=f"PayPal rejected the capture: {exc.message[:200]}")
        raise _paypal_http_error(exc) from exc
    except pp.PayPalError as exc:  # timeout / 5xx / auth glitch mid-capture: outcome unknown
        _unknown(session, keystore, intent, att, "Capture outcome unknown (no confirmed response). Reconcile with PayPal.")
        raise tx.TxError(504, "CAPTURE_UNCERTAIN",
                         "No confirmed response from PayPal; payment status is UNCERTAIN. Reconcile before retrying.") from exc

    if _record_capture(session, intent, result, {tx.CAPTURING}):
        _confirmed(session, keystore, intent, att, result, tx.CAPTURING, "SUCCEEDED")
        return intent
    _unknown(session, keystore, intent, att, "PayPal did not confirm a COMPLETED capture (e.g. pending). Reconcile.",
             paypal_status=result.get("status"))
    raise tx.TxError(409, "CAPTURE_UNCERTAIN", "PayPal did not confirm a completed capture. Reconcile.")


def reconcile(session: Session, keystore: KeyStore, settings: Settings, client: pp.PayPalClient,
              intent_id: str) -> TransactionIntent:
    """Resolve UNCERTAIN by asking PayPal. Only retries are allowed if PayPal shows no capture occurred."""
    _require_configured(settings)
    intent = tx.get_intent(session, intent_id)
    if intent.state != tx.UNCERTAIN:
        raise tx.TxError(409, "INVALID_STATE", f"Reconciliation applies only to CAPTURE_UNCERTAIN (state: {intent.state}).")
    att = attempts.begin(session, intent.id, "reconcile", "n/a (read-only GET)", order_id=intent.paypal_order_id)
    try:
        order = _verified_order(session, client, intent)
    except pp.PayPalError as exc:
        attempts.finish(session, att, "OUTCOME_UNKNOWN", detail=exc.message)
        ev.append(session, keystore, intent.id, "RECONCILIATION_UNRESOLVED", ev.SOURCE_INTERNAL, refs=_refs(intent, att),
                  status_from=tx.UNCERTAIN, status_to=tx.UNCERTAIN,
                  note="Could not read PayPal's order. State stays CAPTURE_UNCERTAIN (PENDING_RECONCILIATION).")
        raise _paypal_http_error(exc) from exc  # still uncertain
    status = order.get("status")
    if _record_capture(session, intent, order, {tx.UNCERTAIN}):
        _confirmed(session, keystore, intent, att, order, tx.UNCERTAIN, "RECONCILED")
    elif status == "APPROVED" and pp.first_capture(order) is None:
        tx.transition(session, intent.id, {tx.UNCERTAIN}, tx.ORDER_CREATED, paypal_status=status,
                      failure_reason="Reconciled: PayPal shows no capture. Capture may be retried.")
        session.refresh(intent)
        attempts.finish(session, att, "RECONCILED", observed_status=status, detail="PayPal shows no capture.")
        ev.append(session, keystore, intent.id, "RECONCILIATION_OBSERVED", ev.SOURCE_PAYPAL, refs=_refs(intent, att),
                  status_from=tx.UNCERTAIN, status_to=tx.ORDER_CREATED, observation=_observation(order),
                  note="PayPal shows the order approved with no capture, so no money moved.")
    elif status in ("VOIDED",):
        tx.transition(session, intent.id, {tx.UNCERTAIN}, tx.FAILED, paypal_status=status,
                      failure_reason="Reconciled: order voided at PayPal.")
        session.refresh(intent)
        attempts.finish(session, att, "RECONCILED", observed_status=status, detail="Order voided.")
        ev.append(session, keystore, intent.id, "RECONCILIATION_OBSERVED", ev.SOURCE_PAYPAL, refs=_refs(intent, att),
                  status_from=tx.UNCERTAIN, status_to=tx.FAILED, observation=_observation(order))
    else:
        intent.paypal_status = status
        session.commit()
        attempts.finish(session, att, "OUTCOME_UNKNOWN", observed_status=status, detail="PayPal status is inconclusive.")
        ev.append(session, keystore, intent.id, "RECONCILIATION_OBSERVED", ev.SOURCE_PAYPAL, refs=_refs(intent, att),
                  status_from=tx.UNCERTAIN, status_to=tx.UNCERTAIN, observation=_observation(order),
                  note="PayPal's status does not settle the outcome; staying PENDING_RECONCILIATION.")
    session.refresh(intent)
    return intent
