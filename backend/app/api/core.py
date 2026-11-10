"""Health, catalogue and policy endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import Settings
from ..schemas import HealthOut, PolicyDecisionOut, PolicyEvaluateIn, ProductOut
from ..services import catalogue, policy
from ..services.money import InvalidAmount, parse_amount
from .deps import get_db, get_settings

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthOut, tags=["system"])
def health(db: Session = Depends(get_db), settings: Settings = Depends(get_settings)) -> HealthOut:
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:  # pragma: no cover - only on a broken DB
        database = "error"
    return HealthOut(
        status="ok" if database == "ok" else "degraded",
        database=database,
        paypal="configured (sandbox)" if settings.paypal_configured else "not configured - setup required",
        ai="external provider configured" if settings.ai_configured else "not configured - local deterministic fallback",
        paypal_configured=settings.paypal_configured,
        ai_configured=settings.ai_configured,
        mode_notes=[
            "PayPal payments only count when PayPal Sandbox confirms capture.",
            "Automated tests that mock PayPal are labelled as mocked.",
        ],
    )


@router.get("/products", response_model=list[ProductOut], tags=["catalogue"])
def products(db: Session = Depends(get_db)) -> list[ProductOut]:
    return [
        ProductOut(
            id=p.id, name=p.name, seller_name=p.seller_name, category=p.category,
            price=f"{p.price:.2f}", currency=p.currency,
            seller_approved=catalogue.is_seller_approved(db, p.seller_name),
        )
        for p in catalogue.list_products(db)
    ]


@router.get("/policies", tags=["policy"])
def policies(db: Session = Depends(get_db)) -> dict:
    return {**policy.describe_policy(), "approved_sellers": catalogue.approved_seller_names(db)}


@router.post("/policies/evaluate", response_model=PolicyDecisionOut, tags=["policy"])
def evaluate(body: PolicyEvaluateIn, db: Session = Depends(get_db)) -> PolicyDecisionOut:
    claimed = None
    if body.claimed_amount is not None:
        try:
            claimed = parse_amount(body.claimed_amount)
        except InvalidAmount as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = policy.evaluate_purchase(
        db, body.product_id, claimed_seller=body.claimed_seller,
        claimed_amount=claimed, currency=body.currency.upper(),
    )
    return PolicyDecisionOut(**result.to_dict())
