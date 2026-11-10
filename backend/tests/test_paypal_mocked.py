"""MOCKED PayPal tests.

Everything here talks to an in-memory fake PayPal (httpx.MockTransport). No network, no credentials,
and NO real payment is ever made. Passing these tests shows OUR handling of PayPal's documented
HTTP behaviour; it is not evidence that live Sandbox checkout works.
"""
import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.mock_paypal import FakePayPal
from app.services.paypal import PayPalClient

AGENT = "agent-shopper-001"


@pytest.fixture()
def fake():
    return FakePayPal()


@pytest.fixture()
def paypal_app(tmp_path, fake):
    settings = Settings(data_dir=tmp_path / "data", paypal_client_id="mock-id", paypal_client_secret="mock-secret",
                        paypal_base_url="https://paypal.mock")
    app = create_app(settings)
    app.state.paypal = PayPalClient(settings, transport=httpx.MockTransport(fake.handler))
    return app


@pytest.fixture()
def pc(paypal_app):
    return TestClient(paypal_app)


def make_ready(c, product="sticker-pack"):
    i = c.post("/api/transactions", json={"agent_id": AGENT, "product_id": product}).json()
    if i["state"] == "AWAITING_INTERNAL_APPROVAL":
        c.post(f"/api/transactions/{i['id']}/approve", json={"approver": "alice", "details_digest": i["details_digest"]})
    return i["id"]


def order(c, iid):
    return c.post(f"/api/transactions/{iid}/paypal/order")


def capture(c, iid):
    return c.post(f"/api/transactions/{iid}/paypal/capture")


def test_missing_credentials_is_honest_setup_required(client):
    i = client.post("/api/transactions", json={"agent_id": AGENT, "product_id": "sticker-pack"}).json()
    r = client.post(f"/api/transactions/{i['id']}/paypal/order")
    assert r.status_code == 503 and r.json()["error"] == "PAYPAL_NOT_CONFIGURED"
    assert client.get(f"/api/transactions/{i['id']}").json()["state"] == "READY_FOR_PAYMENT"


def test_order_uses_trusted_amount_and_returns_approval_url(pc, fake):
    iid = make_ready(pc)
    r = order(pc, iid)
    body = r.json()
    assert r.status_code == 200 and body["state"] == "ORDER_CREATED"
    assert body["paypal"]["approval_url"].startswith("https://sandbox.paypal.test/approve/")
    unit = fake.orders[body["paypal"]["order_id"]]["purchase_units"][0]
    assert unit["amount"] == {"currency_code": "USD", "value": "9.99"}


def test_order_endpoint_accepts_no_client_amounts(pc):
    iid = make_ready(pc)
    r = pc.post(f"/api/transactions/{iid}/paypal/order", json={"amount": "0.01"})
    assert r.status_code == 200  # body is ignored; amount comes from the trusted intent
    assert r.json()["amount"] == "9.99"


def test_duplicate_order_request_is_idempotent(pc, fake):
    iid = make_ready(pc)
    a = order(pc, iid).json()
    b = order(pc, iid).json()
    assert a["paypal"]["order_id"] == b["paypal"]["order_id"] and len(fake.orders) == 1


def test_order_blocked_without_internal_approval(pc):
    i = pc.post("/api/transactions", json={"agent_id": AGENT, "product_id": "keyboard"}).json()
    r = order(pc, i["id"])
    assert r.status_code == 409 and r.json()["error"] == "INVALID_STATE"


def test_oauth_failure_reported(pc, fake):
    fake.fail_oauth = True
    iid = make_ready(pc)
    r = order(pc, iid)
    assert r.status_code == 502 and r.json()["error"] == "PAYPAL_AUTH_FAILED"
    assert pc.get(f"/api/transactions/{iid}").json()["state"] == "READY_FOR_PAYMENT"


def test_capture_requires_buyer_approval_at_paypal(pc, fake):
    iid = make_ready(pc)
    order(pc, iid)
    r = capture(pc, iid)
    assert r.status_code == 409 and r.json()["error"] == "BUYER_NOT_APPROVED"
    assert not any(c[1].endswith("/capture") for c in fake.calls)


def test_happy_path_capture_only_after_paypal_confirms(pc, fake):
    iid = make_ready(pc, "keyboard")  # needs internal approval first
    o = order(pc, iid).json()
    fake.buyer_approves(o["paypal"]["order_id"])
    r = capture(pc, iid)
    body = r.json()
    assert r.status_code == 200 and body["state"] == "CAPTURED"
    assert body["paypal"]["capture_id"] == f"MOCKCAP-{o['paypal']['order_id']}" and body["paypal"]["status"] == "COMPLETED"


def test_duplicate_capture_does_not_capture_twice(pc, fake):
    iid = make_ready(pc)
    o = order(pc, iid).json()
    fake.buyer_approves(o["paypal"]["order_id"])
    capture(pc, iid)
    again = capture(pc, iid)
    assert again.status_code == 200 and again.json()["state"] == "CAPTURED"
    assert sum(1 for c in fake.calls if c[1].endswith("/capture")) == 1


def test_capture_timeout_is_uncertain_and_never_blindly_retried(pc, fake):
    iid = make_ready(pc)
    o = order(pc, iid).json()
    fake.buyer_approves(o["paypal"]["order_id"])
    fake.capture_mode = "timeout"
    r = capture(pc, iid)
    assert r.status_code == 504 and r.json()["error"] == "CAPTURE_UNCERTAIN"
    assert pc.get(f"/api/transactions/{iid}").json()["state"] == "CAPTURE_UNCERTAIN"
    fake.capture_mode = "ok"
    n_before = sum(1 for c in fake.calls if c[1].endswith("/capture"))
    retry = capture(pc, iid)
    assert retry.status_code == 409 and retry.json()["error"] == "CAPTURE_UNCERTAIN"
    assert sum(1 for c in fake.calls if c[1].endswith("/capture")) == n_before  # no new capture call


def test_reconcile_after_timeout_when_paypal_actually_completed(pc, fake):
    iid = make_ready(pc)
    o = order(pc, iid).json()
    oid = o["paypal"]["order_id"]
    fake.buyer_approves(oid)
    fake.capture_mode = "timeout"
    capture(pc, iid)
    # Truth at PayPal: the capture did complete before the timeout.
    fake.orders[oid]["purchase_units"][0]["payments"] = {"captures": [{"id": "CAP-X", "status": "COMPLETED"}]}
    fake.orders[oid]["status"] = "COMPLETED"
    r = pc.post(f"/api/transactions/{iid}/paypal/reconcile")
    assert r.status_code == 200 and r.json()["state"] == "CAPTURED" and r.json()["paypal"]["capture_id"] == "CAP-X"


def test_reconcile_when_paypal_shows_no_capture_allows_safe_retry(pc, fake):
    iid = make_ready(pc)
    o = order(pc, iid).json()
    fake.buyer_approves(o["paypal"]["order_id"])
    fake.capture_mode = "timeout"
    capture(pc, iid)
    fake.capture_mode = "ok"
    assert pc.post(f"/api/transactions/{iid}/paypal/reconcile").json()["state"] == "ORDER_CREATED"
    assert capture(pc, iid).json()["state"] == "CAPTURED"


def test_reconcile_not_allowed_unless_uncertain(pc):
    iid = make_ready(pc)
    assert pc.post(f"/api/transactions/{iid}/paypal/reconcile").status_code == 409


def test_server_error_on_capture_is_uncertain(pc, fake):
    iid = make_ready(pc)
    o = order(pc, iid).json()
    fake.buyer_approves(o["paypal"]["order_id"])
    fake.capture_mode = "server_error"
    assert capture(pc, iid).status_code == 504
    assert pc.get(f"/api/transactions/{iid}").json()["state"] == "CAPTURE_UNCERTAIN"


def test_declined_capture_marks_failed_not_captured(pc, fake):
    iid = make_ready(pc)
    o = order(pc, iid).json()
    fake.buyer_approves(o["paypal"]["order_id"])
    fake.capture_mode = "declined"
    r = capture(pc, iid)
    assert r.status_code == 502 and r.json()["paypal_issue"] == "INSTRUMENT_DECLINED"
    assert pc.get(f"/api/transactions/{iid}").json()["state"] == "FAILED"


def test_pending_capture_is_not_reported_as_paid(pc, fake):
    iid = make_ready(pc)
    o = order(pc, iid).json()
    fake.buyer_approves(o["paypal"]["order_id"])
    fake.capture_mode = "pending"
    capture(pc, iid)
    assert pc.get(f"/api/transactions/{iid}").json()["state"] == "CAPTURE_UNCERTAIN"


def test_price_change_between_order_and_capture_blocks_capture(pc, paypal_app, fake):
    from app.models import Product
    iid = make_ready(pc)
    o = order(pc, iid).json()
    fake.buyer_approves(o["paypal"]["order_id"])
    with paypal_app.state.session_factory() as s:
        s.get(Product, "sticker-pack").price_cents = 1
        s.commit()
    r = capture(pc, iid)
    assert r.status_code == 409 and r.json()["error"] == "DETAILS_CHANGED"
    assert not any(c[1].endswith("/capture") for c in fake.calls)


def test_status_comes_from_paypal_api(pc, fake):
    iid = make_ready(pc)
    o = order(pc, iid).json()
    fake.buyer_approves(o["paypal"]["order_id"])
    assert pc.get(f"/api/transactions/{iid}/paypal/status").json()["paypal"]["status"] == "APPROVED"
