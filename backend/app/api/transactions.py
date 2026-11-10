"""Transaction intent + internal approval endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import TransactionIntent
from ..schemas import StrictModel
from ..services import transactions as tx
from ..services.money import InvalidAmount, parse_amount
from .deps import get_db, get_settings

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


class CreateIntentIn(StrictModel):
    agent_id: str = Field(min_length=1, max_length=64)
    product_id: str = Field(min_length=1, max_length=40)
    # Optional client claims: used only to detect tampering (mismatch => denied). Never set prices.
    claimed_seller: str | None = Field(default=None, max_length=120)
    claimed_amount: str | None = Field(default=None, max_length=20)
    currency: str = Field(default="USD", min_length=3, max_length=3)


class ApproveIn(StrictModel):
    approver: str = Field(min_length=1, max_length=120)
    details_digest: str = Field(min_length=64, max_length=64)


def tx_error_response(exc: tx.TxError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content={"error": exc.code, "message": exc.message, **exc.extra})


@router.post("", status_code=201)
def create(body: CreateIntentIn, request: Request, db: Session = Depends(get_db)):
    try:
        claimed = parse_amount(body.claimed_amount) if body.claimed_amount is not None else None
    except InvalidAmount as exc:
        return JSONResponse(status_code=422, content={"error": "INVALID_AMOUNT", "message": str(exc)})
    try:
        intent = tx.create_intent(db, request.app.state.keystore, body.agent_id, body.product_id,
                                  body.claimed_seller, claimed, body.currency.upper())
    except tx.TxError as exc:
        return tx_error_response(exc)
    return tx.intent_to_dict(db, intent)


@router.get("")
def list_intents(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(TransactionIntent).order_by(TransactionIntent.created_at.desc()).limit(50))
    return [tx.intent_to_dict(db, r) for r in rows]


@router.get("/{intent_id}")
def get(intent_id: str, db: Session = Depends(get_db)):
    try:
        return tx.intent_to_dict(db, tx.get_intent(db, intent_id))
    except tx.TxError as exc:
        return tx_error_response(exc)


@router.post("/{intent_id}/approve")
def approve(intent_id: str, body: ApproveIn, request: Request, db: Session = Depends(get_db),
            settings: Settings = Depends(get_settings)):
    """INTERNAL human approval. This is not PayPal's buyer approval."""
    try:
        tx.approve(db, request.app.state.keystore, settings, intent_id, body.approver, body.details_digest)
        return tx.intent_to_dict(db, tx.get_intent(db, intent_id))
    except tx.TxError as exc:
        return tx_error_response(exc)
