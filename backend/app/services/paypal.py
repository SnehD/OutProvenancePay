"""Minimal PayPal Orders v2 REST client (Sandbox by default). Server-side only.

Secrets are used only to obtain an OAuth token and are never logged or returned.
"""
from __future__ import annotations

import logging
import time

import httpx

from ..config import Settings

log = logging.getLogger("outprovenance.paypal")


class PayPalError(Exception):
    """Base class. `ambiguous` is True when the outcome at PayPal is unknown (e.g. timeout)."""

    ambiguous = False

    def __init__(self, message: str, *, status: int | None = None, debug_id: str | None = None,
                 issue: str | None = None) -> None:
        super().__init__(message)
        self.message, self.status, self.debug_id, self.issue = message, status, debug_id, issue


class PayPalNotConfigured(PayPalError):
    pass


class PayPalAuthError(PayPalError):
    pass


class PayPalRejected(PayPalError):
    """PayPal answered with a 4xx: the request definitively did not succeed."""


class PayPalTimeout(PayPalError):
    """No usable answer (timeout/network/5xx): the operation may or may not have happened."""

    ambiguous = True


class PayPalClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None) -> None:
        self._s = settings
        self._transport = transport
        self._token: str | None = None
        self._token_expiry = 0.0

    # -- plumbing -----------------------------------------------------------------
    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self._s.paypal_base_url, timeout=self._s.paypal_timeout_seconds,
                            transport=self._transport)

    def _access_token(self) -> str:
        if not self._s.paypal_configured:
            raise PayPalNotConfigured("PayPal Sandbox credentials are not configured on the server.")
        if self._token and time.monotonic() < self._token_expiry:
            return self._token
        try:
            with self._client() as c:
                resp = c.post("/v1/oauth2/token", data={"grant_type": "client_credentials"},
                              auth=(self._s.paypal_client_id, self._s.paypal_client_secret),
                              headers={"Accept": "application/json"})
        except httpx.HTTPError as exc:
            raise PayPalTimeout(f"Could not reach PayPal for authentication ({type(exc).__name__}).") from exc
        if resp.status_code in (401, 403):
            raise PayPalAuthError("PayPal rejected the configured client credentials.", status=resp.status_code)
        if resp.status_code != 200:
            raise PayPalAuthError(f"PayPal OAuth failed with HTTP {resp.status_code}.", status=resp.status_code)
        body = resp.json()
        self._token = body["access_token"]
        self._token_expiry = time.monotonic() + max(int(body.get("expires_in", 300)) - 30, 30)
        return self._token

    def _request(self, method: str, path: str, *, request_id: str | None = None, json: dict | None = None) -> dict:
        token = self._access_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                   "Accept": "application/json"}
        if request_id:
            headers["PayPal-Request-Id"] = request_id  # idempotency key
        try:
            with self._client() as c:
                resp = c.request(method, path, headers=headers, json=json)
        except httpx.HTTPError as exc:
            log.warning("paypal %s %s network error: %s", method, path, type(exc).__name__)
            raise PayPalTimeout(f"No response from PayPal ({type(exc).__name__}); outcome unknown.") from exc
        debug_id = resp.headers.get("paypal-debug-id")
        if resp.status_code >= 500:
            raise PayPalTimeout(f"PayPal server error HTTP {resp.status_code}; outcome unknown.",
                                status=resp.status_code, debug_id=debug_id)
        if resp.status_code >= 400:
            try:
                data = resp.json()
            except ValueError:
                data = {}
            issue = (data.get("details") or [{}])[0].get("issue") if isinstance(data, dict) else None
            msg = data.get("message", "PayPal rejected the request.") if isinstance(data, dict) else "Rejected."
            log.warning("paypal %s %s -> %s issue=%s debug_id=%s", method, path, resp.status_code, issue, debug_id)
            raise PayPalRejected(msg, status=resp.status_code, debug_id=debug_id, issue=issue)
        try:
            return resp.json()
        except ValueError as exc:
            raise PayPalTimeout("PayPal returned an unreadable response; outcome unknown.") from exc

    # -- Orders v2 ----------------------------------------------------------------
    def create_order(self, *, intent_id: str, description: str, amount: str, currency: str,
                     return_url: str, cancel_url: str, request_id: str) -> dict:
        body = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "reference_id": intent_id,
                "description": description[:127],
                "amount": {"currency_code": currency, "value": amount},
            }],
            "payment_source": {"paypal": {"experience_context": {
                "return_url": return_url, "cancel_url": cancel_url,
                "user_action": "PAY_NOW", "shipping_preference": "NO_SHIPPING"}}},
        }
        return self._request("POST", "/v2/checkout/orders", request_id=request_id, json=body)

    def get_order(self, order_id: str) -> dict:
        return self._request("GET", f"/v2/checkout/orders/{order_id}")

    def capture_order(self, order_id: str, request_id: str) -> dict:
        return self._request("POST", f"/v2/checkout/orders/{order_id}/capture", request_id=request_id, json={})


def approval_url(order: dict) -> str | None:
    for link in order.get("links", []):
        if link.get("rel") in ("payer-action", "approve"):
            return link.get("href")
    return None


def first_capture(order: dict) -> dict | None:
    try:
        return order["purchase_units"][0]["payments"]["captures"][0]
    except (KeyError, IndexError, TypeError):
        return None


def order_matches(order: dict, *, intent_id: str, amount: str, currency: str) -> bool:
    """Confirm PayPal's record matches the trusted intent (never trust amounts echoed by browsers)."""
    try:
        unit = order["purchase_units"][0]
        return (unit.get("reference_id") == intent_id and unit["amount"]["value"] == amount
                and unit["amount"]["currency_code"] == currency)
    except (KeyError, IndexError, TypeError):
        return False
