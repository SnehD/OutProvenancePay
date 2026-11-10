"""Advisory AI: proposes a catalogue product from REDACTED text. Output is untrusted.

The AI can only suggest a product id. It cannot set prices, pick sellers, decide policy,
approve, sign or capture. Whatever it returns is validated against a strict schema and the
trusted catalogue; the deterministic policy engine then decides independently.
"""
from __future__ import annotations

import json
import logging
import re

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from ..config import Settings
from . import catalogue

log = logging.getLogger("outprovenance.ai")

SOURCE_FALLBACK = "local-fallback"
SOURCE_EXTERNAL = "external-llm"


class AiProposal(BaseModel):
    """Strict schema: unknown fields (e.g. price, seller, decision) make the output invalid."""

    model_config = ConfigDict(extra="forbid")

    product_id: str = Field(min_length=1, max_length=40)
    rationale: str = Field(default="", max_length=300)


def _fallback(session: Session, text: str) -> AiProposal | None:
    """Deterministic keyword matcher. This is NOT an LLM."""
    tokens = set(re.findall(r"[a-z0-9]+", text.lower()))
    best, best_score = None, 0
    for p in catalogue.list_products(session):
        words = set(re.findall(r"[a-z0-9]+", f"{p.id} {p.name}".lower())) - {"a", "the", "pack"}
        score = len(words & tokens)
        if score > best_score:
            best, best_score = p, score
    if best is None:
        return None
    return AiProposal(product_id=best.id, rationale=f"Keyword match on '{best.name}'.")


def _call_external(settings: Settings, redacted_text: str, product_ids: list[str],
                   transport: httpx.BaseTransport | None) -> object:
    prompt = (
        "Pick the single catalogue product the user wants. Respond with JSON only: "
        '{"product_id": "<id>", "rationale": "<short>"}. Valid ids: ' + ", ".join(product_ids)
    )
    with httpx.Client(timeout=15.0, transport=transport) as client:
        resp = client.post(
            f"{settings.ai_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.ai_api_key}"},
            json={"model": settings.ai_model, "messages": [
                {"role": "system", "content": prompt}, {"role": "user", "content": redacted_text}]},
        )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return json.loads(content)


def propose_product(session: Session, settings: Settings, redacted_text: str,
                    transport: httpx.BaseTransport | None = None) -> dict:
    """Returns {source, proposal, accepted, notes}. Only `redacted_text` is ever used here."""
    ids = [p.id for p in catalogue.list_products(session)]
    if not settings.ai_configured:
        proposal = _fallback(session, redacted_text)
        return {
            "source": SOURCE_FALLBACK,
            "label": "Local deterministic keyword matcher (not an LLM).",
            "proposal": proposal.model_dump() if proposal else None,
            "accepted": proposal is not None,
            "notes": [] if proposal else ["No catalogue product matched the request."],
        }
    try:
        raw = _call_external(settings, redacted_text, ids, transport)
        proposal = AiProposal.model_validate(raw)
    except (httpx.HTTPError, KeyError, IndexError, ValueError, ValidationError, TypeError) as exc:
        log.warning("ai output rejected or call failed: %s", type(exc).__name__)
        return {"source": SOURCE_EXTERNAL, "label": "External AI provider (advisory)", "proposal": None,
                "accepted": False, "notes": ["AI response was invalid or unavailable and was discarded."]}
    if proposal.product_id not in ids:
        return {"source": SOURCE_EXTERNAL, "label": "External AI provider (advisory)", "proposal": None,
                "accepted": False, "notes": ["AI proposed a product id that is not in the trusted catalogue."]}
    return {"source": SOURCE_EXTERNAL, "label": "External AI provider (advisory)",
            "proposal": proposal.model_dump(), "accepted": True, "notes": []}
