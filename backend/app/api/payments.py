"""PayPal Sandbox checkout endpoints. All logic is server-side and re-validates the trusted intent."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..config import Settings
from ..services import payments, receipts
from ..services import transactions as tx
from .deps import get_db, get_settings
from .transactions import tx_error_response

router = APIRouter(prefix="/api/transactions/{intent_id}/paypal", tags=["paypal"])


def _respond(db: Session, request: Request, fn):
    try:
        intent = fn()
        if intent.state == tx.CAPTURED:  # receipt only after PayPal confirmed the capture
            receipts.issue_payment_receipt(db, request.app.state.keystore, intent)
        return tx.intent_to_dict(db, intent)
    except tx.TxError as exc:
        return tx_error_response(exc)


@router.post("/order")
def create_order(intent_id: str, request: Request, db: Session = Depends(get_db),
                 settings: Settings = Depends(get_settings)):
    """Create the PayPal Sandbox order from the trusted intent (client sends no amounts)."""
    return _respond(db, request, lambda: payments.create_order(db, request.app.state.keystore, settings,
                                                      request.app.state.paypal, intent_id))


@router.get("/status")
def status(intent_id: str, request: Request, db: Session = Depends(get_db),
           settings: Settings = Depends(get_settings)):
    return _respond(db, request, lambda: payments.refresh_status(db, request.app.state.keystore, settings,
                                                                 request.app.state.paypal, intent_id))


@router.post("/capture")
def capture(intent_id: str, request: Request, db: Session = Depends(get_db),
            settings: Settings = Depends(get_settings)):
    return _respond(db, request, lambda: payments.capture(db, request.app.state.keystore, settings,
                                                 request.app.state.paypal, intent_id))


@router.post("/reconcile")
def reconcile(intent_id: str, request: Request, db: Session = Depends(get_db),
              settings: Settings = Depends(get_settings)):
    return _respond(db, request, lambda: payments.reconcile(db, request.app.state.keystore, settings,
                                                            request.app.state.paypal, intent_id))
