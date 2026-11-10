"""Persisted execution attempts: which idempotency key was used, when, and what is known about the outcome."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import PaymentAttempt


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def begin(session: Session, intent_id: str, operation: str, idempotency_key: str, *,
          client_key: str | None = None, order_id: str | None = None) -> PaymentAttempt:
    att = PaymentAttempt(id=f"att_{uuid.uuid4().hex[:20]}", intent_id=intent_id, operation=operation,
                         idempotency_key=idempotency_key, client_key=client_key, paypal_order_id=order_id,
                         outcome="STARTED", started_at=_now())
    session.add(att)
    session.commit()
    return att


def begin_or_get(session: Session, intent_id: str, operation: str, idempotency_key: str,
                 client_key: str) -> tuple[PaymentAttempt, bool]:
    """Returns (attempt, created). A repeated agent Idempotency-Key finds the original attempt, not a new one."""
    try:
        return begin(session, intent_id, operation, idempotency_key, client_key=client_key), True
    except IntegrityError:
        session.rollback()
        existing = session.scalars(select(PaymentAttempt).where(
            PaymentAttempt.intent_id == intent_id, PaymentAttempt.client_key == client_key)).one()
        return existing, False


def finish(session: Session, attempt: PaymentAttempt, outcome: str, *, observed_status: str | None = None,
           order_id: str | None = None, capture_id: str | None = None, detail: str | None = None) -> None:
    attempt.outcome = outcome
    attempt.finished_at = _now()
    if observed_status is not None:
        attempt.observed_status = observed_status
    if order_id is not None:
        attempt.paypal_order_id = order_id
    if capture_id is not None:
        attempt.paypal_capture_id = capture_id
    if detail is not None:
        attempt.detail = detail[:390]
    session.merge(attempt)
    session.commit()


def list_for(session: Session, intent_id: str) -> list[PaymentAttempt]:
    return list(session.scalars(select(PaymentAttempt).where(PaymentAttempt.intent_id == intent_id)
                                .order_by(PaymentAttempt.started_at)))


def to_dict(a: PaymentAttempt) -> dict:
    return {"id": a.id, "operation": a.operation, "idempotency_key": a.idempotency_key, "client_key": a.client_key,
            "paypal_order_id": a.paypal_order_id, "paypal_capture_id": a.paypal_capture_id, "outcome": a.outcome,
            "observed_status": a.observed_status, "detail": a.detail,
            "started_at": a.started_at.isoformat() + "Z",
            "finished_at": a.finished_at.isoformat() + "Z" if a.finished_at else None}
