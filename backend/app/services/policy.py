"""Deterministic policy engine. No AI, no client-supplied prices: it reads the trusted catalogue."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from sqlalchemy.orm import Session

from ..config import APPROVAL_THRESHOLD_USD, MAX_PURCHASE_USD, POLICY_VERSION, SUPPORTED_CURRENCIES
from . import catalogue


class Decision(str, Enum):
    ALLOW = "ALLOW"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    DENY = "DENY"


@dataclass(frozen=True)
class PolicyResult:
    decision: Decision
    reasons: list[str]
    policy_version: str = POLICY_VERSION
    product_id: str | None = None
    product_name: str | None = None
    seller_name: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    codes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "decision": self.decision.value,
            "reasons": self.reasons,
            "codes": self.codes,
            "policy_version": self.policy_version,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "seller_name": self.seller_name,
            "amount": None if self.amount is None else f"{self.amount:.2f}",
            "currency": self.currency,
        }


def _deny(reason: str, code: str, **kw) -> PolicyResult:
    return PolicyResult(Decision.DENY, [reason], codes=[code], **kw)


def evaluate_purchase(
    session: Session,
    product_id: str,
    *,
    claimed_seller: str | None = None,
    claimed_amount: Decimal | None = None,
    currency: str = "USD",
) -> PolicyResult:
    """Evaluate a purchase against the trusted catalogue.

    `claimed_seller` / `claimed_amount` are optional client claims. They never override
    the catalogue; any mismatch is a DENY (a changed price/seller is treated as tampering).
    """
    if currency not in SUPPORTED_CURRENCIES:
        return _deny(f"Currency '{currency}' is not supported.", "UNSUPPORTED_CURRENCY", currency=currency)

    product = catalogue.get_product(session, product_id)
    if product is None:
        return _deny("Unknown product.", "UNKNOWN_PRODUCT")

    base = dict(
        product_id=product.id, product_name=product.name,
        seller_name=product.seller_name, amount=product.price, currency=product.currency,
    )

    if product.currency != currency:
        return _deny("Requested currency does not match the catalogue currency.", "CURRENCY_MISMATCH", **base)
    if not catalogue.is_seller_approved(session, product.seller_name):
        return _deny(f"Seller '{product.seller_name}' is not on the approved seller list.",
                     "UNAPPROVED_SELLER", **base)
    if claimed_seller is not None and claimed_seller != product.seller_name:
        return _deny("Claimed seller does not match the trusted catalogue.", "SELLER_MISMATCH", **base)
    if claimed_amount is not None and claimed_amount != product.price:
        return _deny("Claimed amount does not match the trusted catalogue price.", "AMOUNT_MISMATCH", **base)

    limit = Decimal(MAX_PURCHASE_USD)
    threshold = Decimal(APPROVAL_THRESHOLD_USD)
    if product.price > limit:
        return PolicyResult(Decision.DENY,
                            [f"Amount {product.price:.2f} exceeds the {limit:.2f} maximum purchase limit."],
                            codes=["OVER_LIMIT"], **base)
    if product.price > threshold:
        return PolicyResult(Decision.REQUIRE_APPROVAL,
                            [f"Amount {product.price:.2f} is above {threshold:.2f}; explicit human approval required."],
                            codes=["APPROVAL_REQUIRED"], **base)
    return PolicyResult(Decision.ALLOW,
                        [f"Amount {product.price:.2f} is within the auto-allow limit of {threshold:.2f}."],
                        codes=["WITHIN_LIMIT"], **base)


def describe_policy() -> dict:
    return {
        "policy_version": POLICY_VERSION,
        "currency": list(SUPPORTED_CURRENCIES),
        "rules": [
            f"amount <= {APPROVAL_THRESHOLD_USD}: ALLOW",
            f"{APPROVAL_THRESHOLD_USD} < amount <= {MAX_PURCHASE_USD}: REQUIRE_APPROVAL",
            f"amount > {MAX_PURCHASE_USD}: DENY",
            "Unknown product, unapproved seller, unsupported currency: DENY",
            "Prices and sellers always come from the trusted backend catalogue.",
        ],
        "approval_threshold": APPROVAL_THRESHOLD_USD,
        "max_purchase": MAX_PURCHASE_USD,
    }
