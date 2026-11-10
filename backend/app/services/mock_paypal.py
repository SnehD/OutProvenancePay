"""MOCK PayPal server (httpx.MockTransport handler). In-memory only: no network, no credentials.

Used by automated tests and the Attack Lab sandbox. Nothing produced here is a real payment;
anything derived from it must be labelled as mocked.

Failure injection (all controlled, in-memory):
  capture_mode   ok | timeout | declined | server_error | already_captured | pending
                 | lost_response   the capture IS executed at the "processor", but the response is lost
  order_mode     ok | lost_response  same idea for order creation
  order_lookup_fails  True => GET /v2/checkout/orders/{id} times out (reconciliation cannot be completed)
"""
from __future__ import annotations

import json
import threading

import httpx


class FakePayPal:
    def __init__(self) -> None:
        self.orders: dict[str, dict] = {}
        self.capture_mode = "ok"
        self.order_mode = "ok"
        self.order_status_override: str | None = None
        self.order_lookup_fails = False
        self.fail_oauth = False
        self.calls: list[tuple[str, str]] = []
        self.seq = 0
        self.request_ids: dict[str, str] = {}
        self.capture_request_ids: dict[str, str] = {}
        self._lock = threading.Lock()

    def capture_calls(self) -> int:
        return sum(1 for c in self.calls if c[1].endswith("/capture"))

    def captures_executed(self) -> int:
        """How many captures actually happened at the fake processor (not how many requests arrived)."""
        return sum(1 for o in self.orders.values() if o["purchase_units"][0].get("payments"))

    def buyer_approves(self, order_id: str) -> None:
        self.orders[order_id]["status"] = "APPROVED"

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def handler(self, request: httpx.Request) -> httpx.Response:
        with self._lock:
            return self._handle(request)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        self.calls.append((method, path))
        if path == "/v1/oauth2/token":
            if self.fail_oauth:
                return httpx.Response(401, json={"error": "invalid_client"})
            return httpx.Response(200, json={"access_token": "mock-token", "expires_in": 3000})
        if path == "/v2/checkout/orders" and method == "POST":
            rid = request.headers.get("PayPal-Request-Id")
            if rid in self.request_ids:  # PayPal idempotency: same key => same order
                return httpx.Response(200, json=self.orders[self.request_ids[rid]])
            unit = json.loads(request.content)["purchase_units"][0]
            self.seq += 1
            oid = f"MOCKORDER{self.seq}"
            self.orders[oid] = {
                "id": oid, "status": "PAYER_ACTION_REQUIRED",
                "purchase_units": [{"reference_id": unit["reference_id"], "amount": unit["amount"]}],
                "links": [{"rel": "payer-action", "href": f"https://sandbox.paypal.test/approve/{oid}"}],
            }
            self.request_ids[rid] = oid
            if self.order_mode == "lost_response":  # order exists, but the caller never hears about it
                raise httpx.ReadTimeout("simulated lost response", request=request)
            return httpx.Response(201, json=self.orders[oid])
        parts = path.split("/")
        oid = parts[4] if len(parts) > 4 else None
        if method == "GET" and oid in self.orders:
            if self.order_lookup_fails:
                raise httpx.ReadTimeout("simulated lookup timeout", request=request)
            order = dict(self.orders[oid])
            if self.order_status_override:
                order["status"] = self.order_status_override
            return httpx.Response(200, json=order)
        if method == "POST" and path.endswith("/capture") and oid in self.orders:
            order = self.orders[oid]
            if self.capture_mode == "timeout":
                raise httpx.ReadTimeout("simulated timeout", request=request)
            if self.capture_mode == "server_error":
                return httpx.Response(503, json={})
            if self.capture_mode == "declined":
                return httpx.Response(422, json={"message": "declined", "details": [{"issue": "INSTRUMENT_DECLINED"}]})
            if self.capture_mode == "already_captured":
                return httpx.Response(422, json={"message": "x", "details": [{"issue": "ORDER_ALREADY_CAPTURED"}]})
            rid = request.headers.get("PayPal-Request-Id")
            if order["purchase_units"][0].get("payments") and rid in self.capture_request_ids:
                return httpx.Response(201, json=order)  # PayPal idempotency: same key => same capture, not a second one
            status = "PENDING" if self.capture_mode == "pending" else "COMPLETED"
            order["purchase_units"][0]["payments"] = {"captures": [{"id": f"MOCKCAP-{oid}", "status": status}]}
            order["status"] = "COMPLETED"
            self.capture_request_ids[rid or ""] = oid
            if self.capture_mode == "lost_response":  # money moved, but the caller never hears about it
                raise httpx.ReadTimeout("simulated lost response", request=request)
            return httpx.Response(201, json=order)
        return httpx.Response(404, json={})
