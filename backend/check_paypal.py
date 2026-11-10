"""Check that PayPal Sandbox credentials work, without moving any money.

    python check_paypal.py            # asks PayPal for an OAuth token (proves the client id/secret are accepted)
    python check_paypal.py --order    # also creates ONE 1.00 USD Sandbox order and prints the buyer-approval link

Neither mode captures a payment. Secrets and tokens are never printed. Exit codes: 0 ok, 1 PayPal rejected or
unreachable, 2 not configured, 3 refused (live host).
"""
from __future__ import annotations

import argparse
import sys

from app.config import Settings, load_settings
from app.main import LIVE_PAYPAL_HOSTS
from app.services import paypal as pp
from urllib.parse import urlparse


def run(settings: Settings, client: pp.PayPalClient, make_order: bool, out=print) -> int:
    host = (urlparse(settings.paypal_base_url).hostname or "").lower()
    if host in LIVE_PAYPAL_HOSTS:
        out(f"REFUSED: PAYPAL_BASE_URL host is {host}, PayPal's LIVE API. This project is Sandbox-only.")
        return 3
    if not settings.paypal_configured:
        out("NOT CONFIGURED: set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET in backend/.env, then run this again.")
        out("Get them at https://developer.paypal.com -> Apps & Credentials -> Sandbox -> Create App.")
        return 2
    out(f"PayPal host: {host or settings.paypal_base_url}")
    try:
        client._access_token()  # raises on bad credentials; the token itself is never shown
    except pp.PayPalError as exc:
        out(f"FAILED: {exc.message}")
        out("Check that the keys are from the SANDBOX tab (not Live) and have no spaces or quotes around them.")
        return 1
    out("OK: PayPal Sandbox accepted the credentials (OAuth token obtained).")
    if not make_order:
        out("Next: run with --order to create one test order, or use the app (PayPal Checkout page).")
        return 0
    try:
        order = client.create_order(
            intent_id="check-paypal-script", description="OutProvenance Pay credential check", amount="1.00",
            currency="USD", return_url=f"{settings.frontend_url}/?paypal=return", cancel_url=f"{settings.frontend_url}/?paypal=cancel",
            request_id="opp-check-script-1")
    except pp.PayPalError as exc:
        out(f"ORDER FAILED: {exc.message} (issue: {exc.issue}, debug id: {exc.debug_id})")
        return 1
    out(f"OK: created Sandbox order {order.get('id')} with status {order.get('status')}. No money has moved and nothing was captured.")
    link = pp.approval_url(order)
    out(f"Buyer approval link (log in with your Sandbox PERSONAL account): {link}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--order", action="store_true", help="also create one 1.00 USD Sandbox order (no capture)")
    args = parser.parse_args(argv)
    settings = load_settings()
    return run(settings, pp.PayPalClient(settings), args.order)


if __name__ == "__main__":
    sys.exit(main())
