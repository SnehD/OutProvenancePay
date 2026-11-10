import json
from datetime import timedelta

import pytest

from app.models import AgentManifestRecord, Approval, Product
from app.services import transactions as tx

AGENT = "agent-shopper-001"


def new_intent(client, product_id, **extra):
    return client.post("/api/transactions", json={"agent_id": AGENT, "product_id": product_id, **extra})


def approve(client, intent, approver="alice"):
    return client.post(f"/api/transactions/{intent['id']}/approve",
                       json={"approver": approver, "details_digest": intent["details_digest"]})


def test_allowed_purchase_is_ready_without_approval(client):
    body = new_intent(client, "sticker-pack").json()
    assert body["state"] == "READY_FOR_PAYMENT" and body["policy_decision"] == "ALLOW"
    assert body["id"].startswith("txn_")


def test_over_limit_and_unapproved_seller_denied_at_api(client):
    r = new_intent(client, "headphones")
    assert r.status_code == 403 and r.json()["error"] == "POLICY_DENIED"
    assert new_intent(client, "gadget-gray").status_code == 403
    assert new_intent(client, "nope").status_code == 403


def test_client_price_claim_cannot_lower_price(client):
    r = new_intent(client, "keyboard", claimed_amount="1.00")
    assert r.status_code == 403 and r.json()["error"] == "POLICY_DENIED"


def test_invalid_amount_claim_422(client):
    assert new_intent(client, "keyboard", claimed_amount="-3").status_code == 422


def test_approval_flow_and_duplicate_refused(client):
    intent = new_intent(client, "keyboard").json()
    assert intent["state"] == "AWAITING_INTERNAL_APPROVAL"
    ok = approve(client, intent)
    assert ok.status_code == 200 and ok.json()["state"] == "READY_FOR_PAYMENT"
    dup = approve(client, intent)
    assert dup.status_code == 409 and dup.json()["error"] == "ALREADY_APPROVED_OR_PROCESSED"


def test_approval_with_wrong_digest_refused(client):
    intent = new_intent(client, "keyboard").json()
    r = client.post(f"/api/transactions/{intent['id']}/approve",
                    json={"approver": "alice", "details_digest": "0" * 64})
    assert r.status_code == 409 and r.json()["error"] == "DIGEST_MISMATCH"


def test_approval_not_required_for_allowed(client):
    intent = new_intent(client, "sticker-pack").json()
    assert approve(client, intent).status_code == 409


def test_manifest_tamper_blocks_intent(app, client):
    with app.state.session_factory() as s:
        rec = s.get(AgentManifestRecord, AGENT)
        data = json.loads(rec.payload_json)
        data["capabilities"].append("x")
        rec.payload_json = json.dumps(data, sort_keys=True)
        s.commit()
    r = new_intent(client, "sticker-pack")
    assert r.status_code == 403 and r.json()["error"] == "MANIFEST_INVALID"


def _payable_error(app, intent_id):
    with app.state.session_factory() as s:
        with pytest.raises(tx.TxError) as e:
            tx.assert_payable(s, app.state.keystore, tx.get_intent(s, intent_id), consuming=True)
    return e.value.code


def test_price_change_after_approval_invalidates(app, client):
    intent = new_intent(client, "keyboard").json()
    approve(client, intent)
    with app.state.session_factory() as s:
        s.get(Product, "keyboard").price_cents = 8000  # still legal, but different from what was approved
        s.commit()
    assert _payable_error(app, intent["id"]) == "DETAILS_CHANGED"


def test_seller_change_after_approval_invalidates(app, client):
    intent = new_intent(client, "keyboard").json()
    approve(client, intent)
    with app.state.session_factory() as s:
        s.get(Product, "keyboard").seller_name = "Acme Office Supply"
        s.commit()
    assert _payable_error(app, intent["id"]) == "DETAILS_CHANGED"


def test_product_pushed_over_limit_after_approval_is_denied(app, client):
    intent = new_intent(client, "keyboard").json()
    approve(client, intent)
    with app.state.session_factory() as s:
        s.get(Product, "keyboard").price_cents = 15000
        s.commit()
    assert _payable_error(app, intent["id"]) == "POLICY_DENIED"


def test_expired_approval_rejected(app, client):
    intent = new_intent(client, "keyboard").json()
    approve(client, intent)
    with app.state.session_factory() as s:
        s.query(Approval).one().expires_at = tx.utcnow() - timedelta(seconds=1)
        s.commit()
    assert _payable_error(app, intent["id"]) == "APPROVAL_EXPIRED"


def test_approval_is_one_time_use(app, client):
    intent = new_intent(client, "keyboard").json()
    approve(client, intent)
    with app.state.session_factory() as s:
        row = tx.get_intent(s, intent["id"])
        appr = tx.assert_payable(s, app.state.keystore, row, consuming=True)
        assert tx.consume_approval(s, appr) is True
        assert tx.consume_approval(s, appr) is False  # replay loses the race
    assert _payable_error(app, intent["id"]) == "APPROVAL_REPLAYED"


def test_missing_approval_blocks_payment(app, client):
    intent = new_intent(client, "keyboard").json()
    assert _payable_error(app, intent["id"]) == "APPROVAL_REQUIRED"


def test_approval_cannot_be_reused_for_another_intent(app, client):
    a = new_intent(client, "keyboard").json()
    approve(client, a)
    b = new_intent(client, "keyboard").json()
    assert _payable_error(app, b["id"]) == "APPROVAL_REQUIRED"


def test_state_transition_is_atomic(app, client):
    intent = new_intent(client, "sticker-pack").json()
    with app.state.session_factory() as s:
        assert tx.transition(s, intent["id"], {tx.READY}, tx.ORDER_CREATING) is True
        assert tx.transition(s, intent["id"], {tx.READY}, tx.ORDER_CREATING) is False
        with pytest.raises(AssertionError):
            tx.transition(s, intent["id"], {tx.READY}, tx.CAPTURED)
