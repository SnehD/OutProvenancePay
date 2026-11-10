"""Trusted product catalogue. This is the ONLY source of prices and seller names."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ApprovedSeller, Product

APPROVED_SELLERS = ["Acme Office Supply", "Northwind Electronics", "Contoso Home"]

# (id, name, seller, category, price in cents)
SEED_PRODUCTS = [
    ("sticker-pack", "Developer Sticker Pack", "Acme Office Supply", "office", 999),
    ("usbc-cable", "USB-C Cable 2m", "Northwind Electronics", "electronics", 2450),
    ("desk-lamp", "LED Desk Lamp", "Contoso Home", "home", 7500),  # exactly 75.00: ALLOW
    ("keyboard", "Mechanical Keyboard", "Northwind Electronics", "electronics", 8900),  # approval
    ("monitor-stand", "Monitor Stand", "Contoso Home", "home", 10000),  # exactly 100.00: approval
    ("headphones", "Noise-Cancelling Headphones", "Northwind Electronics", "electronics", 12900),  # deny
    ("gadget-gray", "Bargain Gadget", "Gray Market Gadgets", "electronics", 1999),  # unapproved seller
]


def seed_catalogue(session: Session) -> None:
    """Insert the fixed catalogue if missing. Existing rows are left untouched."""
    for name in APPROVED_SELLERS:
        if session.get(ApprovedSeller, name) is None:
            session.add(ApprovedSeller(name=name))
    for pid, name, seller, category, cents in SEED_PRODUCTS:
        if session.get(Product, pid) is None:
            session.add(
                Product(id=pid, name=name, seller_name=seller, category=category,
                        price_cents=cents, currency="USD", active=True)
            )
    session.commit()


def list_products(session: Session) -> list[Product]:
    return list(session.scalars(select(Product).where(Product.active.is_(True)).order_by(Product.id)))


def get_product(session: Session, product_id: str) -> Product | None:
    product = session.get(Product, product_id)
    return product if product is not None and product.active else None


def is_seller_approved(session: Session, seller_name: str) -> bool:
    return session.get(ApprovedSeller, seller_name) is not None


def approved_seller_names(session: Session) -> list[str]:
    return sorted(s.name for s in session.scalars(select(ApprovedSeller)))
