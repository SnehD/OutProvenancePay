"""Pydantic API schemas. Amounts are always strings so they never pass through floats."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProductOut(BaseModel):
    id: str
    name: str
    seller_name: str
    category: str
    price: str
    currency: str
    seller_approved: bool


class PolicyEvaluateIn(StrictModel):
    product_id: str = Field(min_length=1, max_length=40)
    # Optional claims from the client. They can only cause a DENY on mismatch; they never set a price.
    claimed_seller: str | None = Field(default=None, max_length=120)
    claimed_amount: str | None = Field(default=None, max_length=20)
    currency: str = Field(default="USD", min_length=3, max_length=3)


class PolicyDecisionOut(BaseModel):
    decision: str
    reasons: list[str]
    codes: list[str]
    policy_version: str
    product_id: str | None
    product_name: str | None
    seller_name: str | None
    amount: str | None
    currency: str | None


class HealthOut(BaseModel):
    status: str
    database: str
    paypal: str
    ai: str
    paypal_configured: bool
    ai_configured: bool
    mode_notes: list[str]
