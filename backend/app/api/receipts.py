"""Receipt endpoints: fetch/download, development receipt, and independent verification."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ReceiptRecord
from ..schemas import StrictModel
from ..services import receipts as rc
from ..services import transactions as tx
from .deps import get_db
from .transactions import tx_error_response

router = APIRouter(prefix="/api", tags=["receipts"])


class VerifyIn(StrictModel):
    payload: dict
    signature_b64: str
    key_id: str


@router.post("/receipts/verify")
def verify(body: VerifyIn, request: Request) -> dict:
    """Verifies the SUBMITTED content. Nothing here reads a stored 'valid' flag."""
    return rc.verify_receipt(request.app.state.keystore, body.payload, body.signature_b64, body.key_id)


@router.get("/receipts")
def list_receipts(intent_id: str | None = None, request: Request = None, db: Session = Depends(get_db)):
    q = select(ReceiptRecord).order_by(ReceiptRecord.created_at.desc()).limit(50)
    if intent_id:
        q = q.where(ReceiptRecord.intent_id == intent_id)
    return [{"id": r.id, "intent_id": r.intent_id, "receipt_type": r.receipt_type,
             "created_at": r.created_at.isoformat() + "Z"} for r in db.scalars(q)]


@router.get("/receipts/{receipt_id}")
def get_receipt(receipt_id: str, request: Request, download: bool = False, db: Session = Depends(get_db)):
    rec = db.get(ReceiptRecord, receipt_id)
    if rec is None:
        return JSONResponse(status_code=404, content={"error": "NOT_FOUND", "message": "Unknown receipt."})
    doc = rc.receipt_document(request.app.state.keystore, rec)
    headers = {"Content-Disposition": f'attachment; filename="{rec.id}.json"'} if download else None
    return JSONResponse(content=doc, headers=headers)


@router.post("/transactions/{intent_id}/dev-receipt")
def dev_receipt(intent_id: str, request: Request, db: Session = Depends(get_db)):
    """Development/test receipt. Claims NO payment and can neither authorise nor capture anything."""
    try:
        rec = rc.issue_dev_receipt(db, request.app.state.keystore, tx.get_intent(db, intent_id))
    except tx.TxError as exc:
        return tx_error_response(exc)
    return rc.receipt_document(request.app.state.keystore, rec)
