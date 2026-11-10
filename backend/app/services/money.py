"""Strict money parsing. Rejects non-finite, non-positive, over-precise and excessive values."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from ..config import MAX_SANE_AMOUNT


class InvalidAmount(ValueError):
    pass


def parse_amount(value: object) -> Decimal:
    """Parse a user/API amount into a 2-decimal Decimal or raise InvalidAmount.

    Floats are refused outright: they cannot represent most decimal amounts exactly.
    """
    if isinstance(value, bool) or isinstance(value, float):
        raise InvalidAmount("Amount must be a decimal string or integer, not a float/bool.")
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise InvalidAmount("Amount is not a valid number.") from exc
    if not amount.is_finite():
        raise InvalidAmount("Amount must be finite.")
    if amount <= 0:
        raise InvalidAmount("Amount must be greater than zero.")
    if amount != amount.quantize(Decimal("0.01")):
        raise InvalidAmount("Amount may have at most 2 decimal places.")
    if amount > Decimal(MAX_SANE_AMOUNT):
        raise InvalidAmount("Amount exceeds the maximum accepted value.")
    return amount.quantize(Decimal("0.01"))


def format_amount(amount: Decimal) -> str:
    return f"{amount.quantize(Decimal('0.01')):.2f}"
