from decimal import Decimal

import pytest

from app.services.money import InvalidAmount, parse_amount
from app.services.policy import Decision, evaluate_purchase


def test_allow_at_threshold_boundary(db):
    r = evaluate_purchase(db, "desk-lamp")  # exactly 75.00
    assert r.decision == Decision.ALLOW


def test_small_purchase_allowed(db):
    assert evaluate_purchase(db, "sticker-pack").decision == Decision.ALLOW


def test_above_75_requires_approval(db):
    r = evaluate_purchase(db, "keyboard")  # 89.00
    assert r.decision == Decision.REQUIRE_APPROVAL


def test_exactly_100_requires_approval_not_deny(db):
    r = evaluate_purchase(db, "monitor-stand")
    assert r.decision == Decision.REQUIRE_APPROVAL and r.amount == Decimal("100.00")


def test_over_100_denied(db):
    r = evaluate_purchase(db, "headphones")  # 129.00
    assert r.decision == Decision.DENY and "OVER_LIMIT" in r.codes


def test_unapproved_seller_denied(db):
    r = evaluate_purchase(db, "gadget-gray")
    assert r.decision == Decision.DENY and "UNAPPROVED_SELLER" in r.codes


def test_unknown_product_denied(db):
    r = evaluate_purchase(db, "does-not-exist")
    assert r.decision == Decision.DENY and "UNKNOWN_PRODUCT" in r.codes


def test_unsupported_currency_denied(db):
    assert evaluate_purchase(db, "sticker-pack", currency="EUR").decision == Decision.DENY


def test_client_cannot_lower_price(db):
    r = evaluate_purchase(db, "headphones", claimed_amount=Decimal("1.00"))
    assert r.decision == Decision.DENY and r.amount == Decimal("129.00")


def test_client_cannot_swap_seller(db):
    r = evaluate_purchase(db, "gadget-gray", claimed_seller="Acme Office Supply")
    assert r.decision == Decision.DENY


@pytest.mark.parametrize("bad", ["0", "-5", "NaN", "Infinity", "abc", "1.005", "99999999", 12.5, True, ""])
def test_invalid_amounts_rejected(bad):
    with pytest.raises(InvalidAmount):
        parse_amount(bad)


def test_valid_amount_parsed():
    assert parse_amount("75.00") == Decimal("75.00")
    assert parse_amount(10) == Decimal("10.00")
