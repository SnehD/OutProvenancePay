"""Payment recovery and evidence endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy.orm import Session

from ..config import Settings
from ..schemas import StrictModel
from ..services import attempts, evidence, receipts, recovery
from ..services import transactions as tx
from .deps import get_db, get_settings
from .transactions import tx_error_response

router = APIRouter(prefix="/api", tags=["recovery"])


class RetryIn(StrictModel):
    """Optional claims the agent believes it is retrying. They are only compared, never trusted."""
    product_id: str | None = Field(default=None, max_length=40)
    seller_name: str | None = Field(default=None, max_length=120)
    amount: str | None = Field(default=None, max_length=20)
    currency: str | None = Field(default=None, min_length=3, max_length=3)


class EventIn(StrictModel):
    payload: dict
    signature_b64: str
    key_id: str
    digest_sha256: str | None = None  # accepted but ignored: digests are always recomputed


class VerifyEvidenceIn(StrictModel):
    events: list[EventIn] = Field(max_length=500)
    expected_head_digest: str | None = Field(default=None, min_length=64, max_length=64)


@router.post("/transactions/{intent_id}/paypal/retry")
def retry(intent_id: str, request: Request, body: RetryIn | None = Body(default=None),
          idempotency_key: str | None = Header(default=None, min_length=8, max_length=100),
          db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    """What an agent calls when it did not hear back. Resolves against the ORIGINAL intent; see services/recovery.py."""
    if idempotency_key is None:
        return JSONResponse(status_code=428, content={
            "error": "IDEMPOTENCY_KEY_REQUIRED",
            "message": "Send an Idempotency-Key header (8-100 chars) so a repeated retry is recognised as the same request."})
    claimed = body.model_dump(exclude_none=True) if body else {}
    try:
        res = recovery.retry_payment(db, request.app.state.keystore, settings, request.app.state.paypal,
                                     intent_id, idempotency_key, claimed)
        if res.intent.state == tx.CAPTURED:  # receipt only after PayPal confirmed the capture
            receipts.issue_payment_receipt(db, request.app.state.keystore, res.intent)
        payload = {**tx.intent_to_dict(db, res.intent), "retry": {
            "outcome": res.outcome, "message": res.message, "attempt_id": res.attempt_id, "replay": res.replay}}
    except tx.TxError as exc:
        return tx_error_response(exc)
    if res.outcome == recovery.PENDING:  # neither success nor failure may be claimed
        return JSONResponse(status_code=202, content=payload)
    if res.outcome == "IN_PROGRESS":
        return JSONResponse(status_code=409, content={"error": "DUPLICATE_REQUEST", **payload})
    return payload


@router.get("/transactions/{intent_id}/attempts")
def list_attempts(intent_id: str, db: Session = Depends(get_db)):
    try:
        tx.get_intent(db, intent_id)
    except tx.TxError as exc:
        return tx_error_response(exc)
    return [attempts.to_dict(a) for a in attempts.list_for(db, intent_id)]


@router.get("/transactions/{intent_id}/evidence")
def get_evidence(intent_id: str, request: Request, db: Session = Depends(get_db)):
    try:
        tx.get_intent(db, intent_id)
    except tx.TxError as exc:
        return tx_error_response(exc)
    return evidence.document(request.app.state.keystore, db, intent_id)


@router.post("/evidence/verify")
def verify_evidence(body: VerifyEvidenceIn, request: Request) -> dict:
    """Verifies the SUBMITTED events only. Nothing here reads a stored 'valid' flag."""
    return evidence.verify_chain(request.app.state.keystore, [e.model_dump() for e in body.events],
                                 body.expected_head_digest)
