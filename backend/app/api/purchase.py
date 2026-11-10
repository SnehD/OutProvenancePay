"""Privacy preview and AI-assisted purchase proposal."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy.orm import Session

from ..config import Settings
from ..schemas import StrictModel
from ..services import ai, policy, privacy
from .deps import get_db, get_settings

router = APIRouter(prefix="/api", tags=["purchase"])
log = logging.getLogger("outprovenance.purchase")


class TextIn(StrictModel):
    text: str = Field(min_length=1, max_length=2000)


def _preview(text: str, settings: Settings) -> dict:
    result = privacy.redact(text)
    return {
        "redacted_text": result.redacted_text,
        "redaction_counts": result.counts,
        "total_redactions": result.total,
        "external_ai_configured": settings.ai_configured,
        "will_be_sent_externally": settings.ai_configured,
        "destination": "external AI provider (redacted text only)" if settings.ai_configured
        else "nowhere - local fallback, nothing leaves this server",
        "limitation": privacy.LIMITATION_NOTE,
    }


@router.post("/privacy/preview")
def privacy_preview(body: TextIn, settings: Settings = Depends(get_settings)) -> dict:
    log.info("privacy preview chars=%d", len(body.text))  # never log the text itself
    return _preview(body.text, settings)


@router.post("/purchase/propose")
def propose(body: TextIn, db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> dict:
    """AI (or fallback) suggests a product; the deterministic policy engine decides independently."""
    preview = _preview(body.text, settings)
    suggestion = ai.propose_product(db, settings, preview["redacted_text"])
    decision = None
    if suggestion["accepted"]:
        decision = policy.evaluate_purchase(db, suggestion["proposal"]["product_id"]).to_dict()
    return {"privacy": preview, "ai": suggestion, "policy": decision,
            "note": "AI output is advisory. Price, seller and decision come from the backend."}
