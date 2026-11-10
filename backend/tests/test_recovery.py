"""Payment recovery, idempotency and TRACE-inspired evidence.

MOCKED PayPal only (in-memory fake with failure injection). No network, no credentials, no real payment.
These tests prove OUR handling of lost/unknown outcomes; they say nothing about live Sandbox behaviour.
"""
import copy

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services import attack_lab as lab
from app.services import evidence
from app.services.mock_paypal import FakePayPal
from app.services.paypal import PayPalClient

AGENT = "agent-shopper-001"
KEY = "agent-retry-0001"


@pytest.fixture()
def fake():
    return FakePayPal()


@pytest.fixture()
def pc(tmp_path, fake):
    settings = Settings(data_dir=tmp_path / "data", paypal_client_id="mock-id", paypal_client_secret="mock-secret",
                        paypal_base_url="https://paypal.mock")
    app = create_app(settings)
    app.state.paypal = PayPalClient(settings, transport=httpx.MockTransport(fake.handler))
    return TestClient(app)


def intent(c, product="sticker-pack"):
    i = c.post("/api/transactions", json={"agent_id": AGENT, "product_id": product}).json()
    if i["state"] == "AWAITING_INTERNAL_APPROVAL":
        assert c.post(f"/api/transactions/{i['id']}/approve",
                      json={"approver": "alice", "details_digest": i["details_digest"]}).status_code == 200
    return i["id"]


def to_order_approved(c, fake, product="sticker-pack"):
    iid = intent(c, product)
    o = c.post(f"/api/transactions/{iid}/paypal/order").json()
    fake.buyer_approves(o["paypal"]["order_id"])
    return iid


def retry(c, iid, key=KEY, body=None):
    return c.post(f"/api/transactions/{iid}/paypal/retry", headers={"Idempotency-Key": key}, json=body)


def lost_capture(c, fake):
    iid = to_order_approved(c, fake)
    fake.capture_mode = "lost_response"
    assert c.post(f"/api/transactions/{iid}/paypal/capture").status_code == 504
    return iid


def test_lost_response_is_unknown_not_success_or_failure(pc, fake):
    iid = lost_capture(pc, fake)
    s = pc.get(f"/api/transactions/{iid}").json()
    assert fake.captures_executed() == 1  # the processor really did capture
    assert s["state"] == "CAPTURE_UNCERTAIN" and s["recovery_status"] == "PENDING_RECONCILIATION"
    assert pc.get("/api/receipts", params={"intent_id": iid}).json() == []


def test_retry_reconciles_and_never_captures_twice(pc, fake):
    iid = lost_capture(pc, fake)
    sent = fake.capture_calls()
    r = retry(pc, iid)
    assert r.status_code == 200 and r.json()["retry"]["outcome"] == "RECONCILED" and r.json()["state"] == "CAPTURED"
    assert fake.capture_calls() == sent and fake.captures_executed() == 1
    again = retry(pc, iid)  # same key: a replay
    assert again.json()["retry"]["replay"] is True and again.json()["retry"]["outcome"] == "REUSED"
    assert retry(pc, iid, "another-key-0002").json()["retry"]["outcome"] == "REUSED"
    assert fake.capture_calls() == sent
    receipts = pc.get("/api/receipts", params={"intent_id": iid}).json()
    assert len(receipts) == 1 and receipts[0]["receipt_type"] == "PAYMENT_CONFIRMED"


def test_retry_after_capture_that_never_executed_recaptures_once_with_same_key(pc, fake):
    iid = to_order_approved(pc, fake)
    fake.capture_mode = "timeout"  # request lost BEFORE PayPal executed it
    assert pc.post(f"/api/transactions/{iid}/paypal/capture").status_code == 504
    assert fake.captures_executed() == 0
    fake.capture_mode = "ok"
    r = retry(pc, iid)
    assert r.status_code == 200 and r.json()["state"] == "CAPTURED"
    assert fake.captures_executed() == 1
    caps = [a for a in pc.get(f"/api/transactions/{iid}/attempts").json() if a["operation"] == "capture"]
    assert {a["idempotency_key"] for a in caps} == {f"opp-capture-{iid}"}  # the same key was reused


def test_unresolved_outcome_stays_pending_and_is_not_reported_as_success_or_error(pc, fake):
    iid = lost_capture(pc, fake)
    fake.order_lookup_fails = True
    r = retry(pc, iid)
    assert r.status_code == 202 and r.json()["retry"]["outcome"] == "PENDING_RECONCILIATION"
    assert r.json()["state"] == "CAPTURE_UNCERTAIN"
    assert pc.get("/api/receipts", params={"intent_id": iid}).json() == []
    fake.order_lookup_fails = False
    assert retry(pc, iid, "another-key-0002").json()["state"] == "CAPTURED"


def test_lost_order_creation_response_reuses_original_order(pc, fake):
    iid = intent(pc)
    fake.order_mode = "lost_response"
    assert pc.post(f"/api/transactions/{iid}/paypal/order").status_code == 504
    assert len(fake.orders) == 1  # PayPal created it, the caller never heard
    assert pc.get(f"/api/transactions/{iid}").json()["state"] == "READY_FOR_PAYMENT"
    fake.order_mode = "ok"
    r = retry(pc, iid)
    assert r.status_code == 200 and r.json()["state"] == "ORDER_CREATED"
    assert len(fake.orders) == 1  # same PayPal-Request-Id => PayPal handed back the original order
    atts = [a for a in pc.get(f"/api/transactions/{iid}/attempts").json() if a["operation"] == "create_order"]
    assert [a["outcome"] for a in atts] == ["OUTCOME_UNKNOWN", "SUCCEEDED"]
    assert len({a["idempotency_key"] for a in atts}) == 1


def test_retry_requires_idempotency_key(pc):
    iid = intent(pc)
    assert pc.post(f"/api/transactions/{iid}/paypal/retry").status_code == 428


def test_retry_with_altered_details_is_rejected_and_revokes_approval(pc, fake):
    iid = intent(pc, "keyboard")  # needs approval; approved, no order yet
    for body, fields in (({"amount": "0.01"}, ["amount"]), ({"product_id": "headphones"}, ["product_id"]),
                         ({"seller_name": "Acme Office Supply"}, ["seller_name"]), ({"currency": "EUR"}, ["currency"])):
        r = retry(pc, iid, body=body)
        assert r.status_code == 409 and r.json()["error"] == "RETRY_DETAILS_MISMATCH"
        assert r.json()["altered_fields"] == fields
    assert pc.post(f"/api/transactions/{iid}/paypal/order").json()["error"] == "APPROVAL_REPLAYED"
    assert fake.orders == {}


def test_matching_claims_in_a_retry_are_accepted(pc, fake):
    iid = lost_capture(pc, fake)
    assert retry(pc, iid, body={"product_id": "sticker-pack", "amount": "9.99", "currency": "USD"}).status_code == 200


def test_evidence_links_approval_attempts_and_paypal_references(pc, fake):
    iid = intent(pc, "keyboard")
    o = pc.post(f"/api/transactions/{iid}/paypal/order").json()
    fake.buyer_approves(o["paypal"]["order_id"])
    done = pc.post(f"/api/transactions/{iid}/paypal/capture").json()
    doc = pc.get(f"/api/transactions/{iid}/evidence").json()
    events = [e["payload"] for e in doc["events"]]
    assert "TRACE-inspired" in doc["profile_note"] and "Not a conformant" in doc["profile_note"]
    assert [e["seq"] for e in events] == list(range(len(events)))
    assert events[0]["prev_event_digest"] is None
    for prev, cur in zip(doc["events"], events[1:]):
        assert cur["prev_event_digest"] == prev["digest_sha256"]
    types = {e["event_type"]: e for e in events}
    assert types["APPROVAL_GRANTED"]["source"] == "INTERNAL"
    approval_id = pc.get(f"/api/transactions/{iid}").json()["internal_approval"]["id"]
    assert types["APPROVAL_GRANTED"]["refs"]["approval_id"] == approval_id
    assert types["ORDER_CREATED"]["source"] == "PAYPAL_OBSERVED"
    assert types["ORDER_CREATED"]["refs"]["paypal_order_id"] == o["paypal"]["order_id"]
    assert types["ORDER_CREATED"]["refs"]["attempt_id"]
    assert types["CAPTURE_CONFIRMED"]["source"] == "PAYPAL_OBSERVED"
    assert types["CAPTURE_CONFIRMED"]["refs"]["paypal_capture_id"] == done["paypal"]["capture_id"]
    assert types["CAPTURE_CONFIRMED"]["paypal_observation"]["capture_status"] == "COMPLETED"
    assert types["INTENT_CREATED"]["paypal_observation"] is None
    assert pc.post("/api/evidence/verify", json={"events": doc["events"]}).json()["valid"] is True


def test_receipt_references_the_evidence_it_was_issued_against(pc, fake):
    iid = to_order_approved(pc, fake)
    pc.post(f"/api/transactions/{iid}/paypal/capture")
    rid = pc.get("/api/receipts", params={"intent_id": iid}).json()[0]["id"]
    receipt = pc.get(f"/api/receipts/{rid}").json()
    ref = receipt["payload"]["evidence_reference"]
    doc = pc.get(f"/api/transactions/{iid}/evidence").json()
    assert ref["intent_id"] == iid and ref["head_digest"] in [e["digest_sha256"] for e in doc["events"]]
    ok = pc.post("/api/evidence/verify", json={"events": doc["events"], "expected_head_digest": ref["head_digest"]}).json()
    assert ok["valid"] is True
    # the receipt itself still verifies independently, and its new field is covered by the signature
    v = pc.post("/api/receipts/verify", json={k: receipt[k] for k in ("payload", "signature_b64", "key_id")}).json()
    assert v["valid"] is True
    forged = copy.deepcopy(receipt)
    forged["payload"]["evidence_reference"]["head_digest"] = "0" * 64
    assert pc.post("/api/receipts/verify", json={k: forged[k] for k in ("payload", "signature_b64", "key_id")}).json()["valid"] is False


def _doc(pc, fake):
    iid = to_order_approved(pc, fake)
    pc.post(f"/api/transactions/{iid}/paypal/capture")
    return pc.get(f"/api/transactions/{iid}/evidence").json()["events"]


def _valid(pc, events, **extra):
    return pc.post("/api/evidence/verify", json={"events": events, **extra}).json()["valid"]


def test_tampered_evidence_fails_independent_verification(pc, fake):
    events = _doc(pc, fake)
    assert _valid(pc, events)
    cases = []
    a = copy.deepcopy(events); a[2]["payload"]["status_to"] = "FAILED"; cases.append(a)
    b = copy.deepcopy(events); b[-2]["payload"]["source"] = "INTERNAL"; cases.append(b)
    c = copy.deepcopy(events); del c[1]; cases.append(c)
    d = copy.deepcopy(events); d[1], d[2] = d[2], d[1]; cases.append(d)
    e = copy.deepcopy(events); e[3]["key_id"] = "ed25519:0000000000000000"; cases.append(e)
    f = copy.deepcopy(events); f.append(copy.deepcopy(f[-1])); cases.append(f)  # duplicated event
    g = copy.deepcopy(events); g[0]["payload"]["intent_id"] = "txn_forged"; cases.append(g)
    for case in cases:
        assert _valid(pc, case) is False
    assert _valid(pc, []) is False


def test_stored_digest_and_valid_flags_are_ignored(pc, fake):
    events = _doc(pc, fake)
    forged = copy.deepcopy(events)
    forged[1]["payload"]["note"] = "edited"
    forged[1]["digest_sha256"] = events[1]["digest_sha256"]  # attacker keeps the old digest
    assert _valid(pc, forged) is False
    r = pc.post("/api/evidence/verify", json={"events": [{**events[0], "valid": True}]})
    assert r.status_code == 422  # unknown fields are refused rather than trusted


def test_evidence_sources_never_overclaim(pc, fake):
    events = _doc(pc, fake)
    for e in (x["payload"] for x in events):
        if e["source"] == "PAYPAL_OBSERVED":
            assert e["paypal_observation"] and "PayPal server API" in e["claim_basis"]
        else:
            assert e["paypal_observation"] is None and "Not independently observed" in e["claim_basis"]


def test_evidence_head_chain_survives_concurrent_appends(app, db):
    """Appends racing for the same sequence number are retried, never forked or skipped."""
    from concurrent.futures import ThreadPoolExecutor
    ks = app.state.keystore

    def add(n):
        with app.state.session_factory() as s:
            evidence.append(s, ks, "txn_race", f"E{n}", evidence.SOURCE_INTERNAL)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(add, range(24)))
    with app.state.session_factory() as s:
        doc = evidence.document(ks, s, "txn_race")
    assert [e["payload"]["seq"] for e in doc["events"]] == list(range(24))
    assert evidence.verify_chain(ks, doc["events"])["valid"] is True


def test_attack_lab_scenarios_report_fail_when_the_defense_is_broken(monkeypatch):
    """Guard against hardcoded PASS: disable the altered-details check and the lab must say FAIL."""
    from app.services import recovery
    monkeypatch.setattr(recovery, "altered_fields", lambda intent, claimed: [])
    assert lab.run_scenario("altered_retry_details")["result"] == "FAIL"


def test_attack_lab_fails_if_retry_would_blindly_recapture(monkeypatch):
    from app.services import recovery
    from app.services import transactions as tx

    def blind(session, keystore, settings, client, intent_id):  # a broken reconcile that pretends "no capture exists"
        intent = tx.get_intent(session, intent_id)
        tx.transition(session, intent.id, {tx.UNCERTAIN}, tx.ORDER_CREATED)
        return tx.get_intent(session, intent_id)

    monkeypatch.setattr(recovery.payments, "reconcile", blind)
    assert lab.run_scenario("retry_reuses_original")["result"] == "FAIL"
