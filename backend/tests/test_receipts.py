import copy
import subprocess
import sys
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.crypto import KeyStore
from app.services.mock_paypal import FakePayPal
from app.services.paypal import PayPalClient

AGENT = "agent-shopper-001"


def dev_receipt(client, product="sticker-pack"):
    i = client.post("/api/transactions", json={"agent_id": AGENT, "product_id": product}).json()
    if i["state"] == "AWAITING_INTERNAL_APPROVAL":
        client.post(f"/api/transactions/{i['id']}/approve", json={"approver": "a", "details_digest": i["details_digest"]})
    return i, client.post(f"/api/transactions/{i['id']}/dev-receipt")


def verify(client, doc, **override):
    body = {"payload": doc["payload"], "signature_b64": doc["signature_b64"], "key_id": doc["key_id"], **override}
    return client.post("/api/receipts/verify", json=body)


def test_dev_receipt_is_labelled_and_claims_no_payment(client):
    _, r = dev_receipt(client)
    p = r.json()["payload"]
    assert r.status_code == 200
    assert p["receipt_type"] == "DEV_TEST_NO_PAYMENT" and p["payment_status"] == "NOT_PAID"
    assert p["paypal_capture_id"] is None and "No payment occurred" in p["notice"]


def test_valid_receipt_verifies(client):
    _, r = dev_receipt(client)
    v = verify(client, r.json()).json()
    assert v["valid"] is True and v["signature_valid"] is True and v["consistency_issues"] == []


@pytest.mark.parametrize("field,value", [
    ("amount", "0.01"), ("product_id", "headphones"), ("transaction_intent_id", "txn_forged"),
    ("seller_name", "Evil Corp"), ("payment_status", "COMPLETED"),
])
def test_any_tampered_signed_field_fails(client, field, value):
    _, r = dev_receipt(client)
    doc = r.json()
    doc["payload"][field] = value
    v = verify(client, doc).json()
    assert v["valid"] is False and v["signature_valid"] is False


def test_extra_field_added_fails(client):
    _, r = dev_receipt(client)
    doc = r.json()
    doc["payload"]["bonus"] = "x"
    assert verify(client, doc).json()["valid"] is False


def test_invalid_and_malformed_signature_fail(client):
    _, r = dev_receipt(client)
    doc = r.json()
    assert verify(client, doc, signature_b64="AAAA" * 22).json()["valid"] is False
    bad = verify(client, doc, signature_b64="!!not-base64!!").json()
    assert bad["valid"] is False and "base64" in bad["signature_reason"]


def test_unknown_key_rejected(client):
    _, r = dev_receipt(client)
    assert verify(client, r.json(), key_id="ed25519:deadbeefdeadbeef").json()["valid"] is False


def test_signature_by_untrusted_key_rejected(client, tmp_path):
    _, r = dev_receipt(client)
    doc = r.json()
    other = KeyStore(tmp_path / "evil")
    forged = other.sign("evil", doc["payload"])
    v = verify(client, doc, signature_b64=forged.signature_b64, key_id=forged.key_id).json()
    assert v["valid"] is False and "Unknown signing key" in v["signature_reason"]


def test_stored_valid_flag_is_not_trusted(client):
    _, r = dev_receipt(client)
    doc = r.json()
    doc["payload"]["amount"] = "1.00"
    body = {"payload": doc["payload"], "signature_b64": doc["signature_b64"], "key_id": doc["key_id"]}
    assert client.post("/api/receipts/verify", json=body).json()["valid"] is False
    assert client.post("/api/receipts/verify", json={**body, "valid": True}).status_code == 422  # extras refused


def test_float_in_payload_cannot_be_verified(client):
    _, r = dev_receipt(client)
    doc = r.json()
    doc["payload"]["amount"] = 9.99
    assert verify(client, doc).json()["valid"] is False


def test_consistency_check_catches_signed_but_false_payment_claim(app, client):
    """Even a correctly signed receipt cannot claim payment without a capture reference."""
    from app.services.receipts import RECEIPT_KEY_NAME
    _, r = dev_receipt(client)
    payload = copy.deepcopy(r.json()["payload"])
    payload.update({"receipt_type": "PAYMENT_CONFIRMED", "payment_status": "COMPLETED"})
    signed = app.state.keystore.sign(RECEIPT_KEY_NAME, payload)
    v = client.post("/api/receipts/verify", json={"payload": payload, "signature_b64": signed.signature_b64,
                                                  "key_id": signed.key_id}).json()
    assert v["signature_valid"] is True and v["valid"] is False and v["consistency_issues"]


def test_receipt_download_and_fetch(client):
    _, r = dev_receipt(client)
    rid = r.json()["payload"]["receipt_id"]
    d = client.get(f"/api/receipts/{rid}", params={"download": "true"})
    assert d.status_code == 200 and "attachment" in d.headers["content-disposition"]
    assert client.get("/api/receipts/nope").status_code == 404


def test_dev_receipt_blocked_without_required_approval(client):
    i = client.post("/api/transactions", json={"agent_id": AGENT, "product_id": "keyboard"}).json()
    assert client.post(f"/api/transactions/{i['id']}/dev-receipt").status_code == 409


def test_no_payment_receipt_without_paypal_confirmation(client):
    i, _ = dev_receipt(client)
    from app.models import TransactionIntent
    from app.services import receipts as rc
    from app.services import transactions as tx
    s = client.app.state.session_factory()
    try:
        with pytest.raises(tx.TxError):
            rc.issue_payment_receipt(s, client.app.state.keystore, tx.get_intent(s, i["id"]))
    finally:
        s.close()


def test_payment_receipt_issued_only_after_mocked_capture(tmp_path):
    fake = FakePayPal()
    settings = Settings(data_dir=tmp_path / "d", paypal_client_id="m", paypal_client_secret="m",
                        paypal_base_url="https://paypal.mock")
    app = create_app(settings)
    app.state.paypal = PayPalClient(settings, transport=fake.transport())
    c = TestClient(app)
    i = c.post("/api/transactions", json={"agent_id": AGENT, "product_id": "sticker-pack"}).json()
    o = c.post(f"/api/transactions/{i['id']}/paypal/order").json()
    assert c.get("/api/receipts", params={"intent_id": i["id"]}).json() == []  # nothing yet
    fake.buyer_approves(o["paypal"]["order_id"])
    done = c.post(f"/api/transactions/{i['id']}/paypal/capture").json()
    assert done["state"] == "CAPTURED" and done["receipt_id"]
    doc = c.get(f"/api/receipts/{done['receipt_id']}").json()
    assert doc["payload"]["receipt_type"] == "PAYMENT_CONFIRMED" and doc["payload"]["payment_status"] == "COMPLETED"
    assert doc["payload"]["paypal_capture_id"].startswith("MOCKCAP-")
    assert verify(c, doc).json()["valid"] is True


def test_uncertain_capture_issues_no_receipt(tmp_path):
    fake = FakePayPal()
    settings = Settings(data_dir=tmp_path / "d", paypal_client_id="m", paypal_client_secret="m",
                        paypal_base_url="https://paypal.mock")
    app = create_app(settings)
    app.state.paypal = PayPalClient(settings, transport=fake.transport())
    c = TestClient(app)
    i = c.post("/api/transactions", json={"agent_id": AGENT, "product_id": "sticker-pack"}).json()
    o = c.post(f"/api/transactions/{i['id']}/paypal/order").json()
    fake.buyer_approves(o["paypal"]["order_id"])
    fake.capture_mode = "timeout"
    c.post(f"/api/transactions/{i['id']}/paypal/capture")
    assert c.get("/api/receipts", params={"intent_id": i["id"]}).json() == []


def test_standalone_cli_verifier(client, tmp_path):
    _, r = dev_receipt(client)
    doc = r.json()
    good = tmp_path / "good.json"
    good.write_text(json.dumps(doc))
    cmd = [sys.executable, "-I", "verify_receipt.py", str(good), "--public-key", doc["signer_public_key_b64"]]
    assert subprocess.run(cmd, capture_output=True, text=True).returncode == 0
    doc["payload"]["amount"] = "0.01"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(doc))
    cmd[3] = str(bad)
    assert subprocess.run(cmd, capture_output=True, text=True).returncode == 1
