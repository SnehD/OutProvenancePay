"""Attack Lab: runs real attacks against the real backend code inside a disposable sandbox.

Each run builds a fresh app (temporary SQLite DB, throwaway keys, MOCK PayPal) and drives it over
its HTTP API. The developer's real database, keys and PayPal account are never touched, and no
real payment is possible. PASS is computed from observed responses, never hardcoded.
"""
from __future__ import annotations

import json
import shutil
import tempfile
from datetime import timedelta
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from fastapi.testclient import TestClient

from ..config import Settings
from ..models import AgentManifestRecord, Approval, Product
from . import transactions as tx
from .mock_paypal import FakePayPal
from .paypal import PayPalClient

AGENT = "agent-shopper-001"

SANDBOX_NOTICE = (
    "Runs against an isolated temporary database with throwaway keys and a MOCKED PayPal. "
    "Your real data, keys and PayPal account are untouched and no real payment can occur."
)

SCENARIOS = [
    {"id": "over_limit", "title": "Purchase over the USD 100 limit", "mocked_paypal": False,
     "defense": "Server-side policy engine denies amounts above the limit."},
    {"id": "unapproved_or_unknown", "title": "Unapproved seller / unknown product", "mocked_paypal": False,
     "defense": "Seller allow-list and trusted catalogue lookups."},
    {"id": "tampered_manifest", "title": "Tampered agent manifest (original signature kept)", "mocked_paypal": False,
     "defense": "Ed25519 signature verification over canonical manifest JSON."},
    {"id": "changed_after_approval", "title": "Price / seller changed after approval", "mocked_paypal": True,
     "defense": "Approval bound to a digest of exact details; re-validated before any order."},
    {"id": "expired_or_replayed_approval", "title": "Expired or replayed approval", "mocked_paypal": True,
     "defense": "Approval expiry and atomic one-time use."},
    {"id": "tampered_receipt", "title": "Tampered signed receipt", "mocked_paypal": False,
     "defense": "Independent verification recomputes digest and checks the signature."},
    {"id": "duplicate_operations", "title": "Duplicate / replayed order and capture", "mocked_paypal": True,
     "defense": "Idempotent order creation, atomic state claims, single capture."},
    {"id": "paypal_timeout_uncertain", "title": "Simulated PayPal timeout during capture", "mocked_paypal": True,
     "defense": "Timeout is UNCERTAIN, never retried blindly, no receipt issued."},
    {"id": "lost_response_capture", "title": "Payment succeeds but the response is lost", "mocked_paypal": True,
     "defense": "A lost response is recorded as an unknown outcome, never as success or failure."},
    {"id": "retry_reuses_original", "title": "Agent retries after the lost response", "mocked_paypal": True,
     "defense": "Retry reconciles with PayPal and reuses the original capture instead of paying twice."},
    {"id": "unresolved_outcome", "title": "Outcome cannot be established", "mocked_paypal": True,
     "defense": "PENDING_RECONCILIATION stays explicit: no success, no failure, no receipt."},
    {"id": "tampered_evidence", "title": "Tampered signed evidence", "mocked_paypal": False,
     "defense": "Independent verification recomputes digests, checks signatures, order and hash links."},
    {"id": "altered_retry_details", "title": "Retry or approval replay with altered details", "mocked_paypal": True,
     "defense": "Retries are compared with the approved intent; differences revoke approval and need fresh authorization."},
    {"id": "concurrent_duplicates", "title": "Concurrent duplicate requests", "mocked_paypal": True,
     "defense": "Atomic state claims and unique keys allow exactly one order and one capture."},
]


@dataclass
class Lab:
    client: TestClient
    app: object
    fake: FakePayPal
    checks: list[dict] = field(default_factory=list)
    observed: dict = field(default_factory=dict)

    def expect(self, label: str, ok: bool, detail: str) -> bool:
        self.checks.append({"check": label, "ok": bool(ok), "detail": detail})
        return bool(ok)

    def session(self):
        return self.app.state.session_factory()

    def intent(self, product: str, **extra):
        return self.client.post("/api/transactions", json={"agent_id": AGENT, "product_id": product, **extra})

    def approve(self, i: dict):
        return self.client.post(f"/api/transactions/{i['id']}/approve",
                                json={"approver": "attack-lab", "details_digest": i["details_digest"]})


@contextmanager
def sandbox():
    from ..main import create_app  # local import avoids a cycle
    tmp = Path(tempfile.mkdtemp(prefix="opp-attacklab-"))
    settings = Settings(data_dir=tmp / "data", paypal_client_id="mock-id", paypal_client_secret="mock-secret",
                        paypal_base_url="https://paypal.mock")
    app = create_app(settings)
    fake = FakePayPal()
    app.state.paypal = PayPalClient(settings, transport=fake.transport())
    try:
        yield Lab(TestClient(app), app, fake)
    finally:
        app.state.engine.dispose()
        shutil.rmtree(tmp, ignore_errors=True)


def _status(r) -> int:
    return r.status_code


def s_over_limit(lab: Lab) -> None:
    r = lab.intent("headphones")
    body = r.json()
    lab.observed = {"http_status": r.status_code, "error": body.get("error"), "policy_codes": body.get("policy", {}).get("codes")}
    lab.expect("Purchase intent for USD 129.00 item is refused", r.status_code == 403 and body.get("error") == "POLICY_DENIED",
               f"HTTP {r.status_code} {body.get('error')}")
    lab.expect("Denial reason is OVER_LIMIT", "OVER_LIMIT" in (lab.observed["policy_codes"] or []), f"codes={lab.observed['policy_codes']}")
    ev = lab.client.post("/api/policies/evaluate", json={"product_id": "headphones", "claimed_amount": "1.00"}).json()
    lab.expect("Client-claimed price of 1.00 cannot override the catalogue", ev["decision"] == "DENY" and ev["amount"] == "129.00",
               f"decision={ev['decision']} amount={ev['amount']}")


def s_unapproved_or_unknown(lab: Lab) -> None:
    a = lab.intent("gadget-gray")
    b = lab.intent("not-a-product")
    lab.observed = {"http_status": [a.status_code, b.status_code], "error": [a.json().get("error"), b.json().get("error")]}
    codes_a = a.json().get("policy", {}).get("codes", [])
    codes_b = b.json().get("policy", {}).get("codes", [])
    lab.expect("Unapproved seller refused", a.status_code == 403 and "UNAPPROVED_SELLER" in codes_a, f"HTTP {a.status_code} {codes_a}")
    lab.expect("Unknown product refused", b.status_code == 403 and "UNKNOWN_PRODUCT" in codes_b, f"HTTP {b.status_code} {codes_b}")
    c = lab.intent("gadget-gray", claimed_seller="Acme Office Supply")
    lab.expect("Spoofing an approved seller name does not help", c.status_code == 403, f"HTTP {c.status_code}")


def s_tampered_manifest(lab: Lab) -> None:
    ok0 = lab.client.post(f"/api/agents/{AGENT}/verify").json()
    lab.expect("Control: untouched manifest verifies", ok0["valid"] is True, ok0["reason"])
    with lab.session() as s:
        rec = s.get(AgentManifestRecord, AGENT)
        original = rec.payload_json
        data = json.loads(original)
        data["capabilities"].append("transfer_funds")  # attacker adds a capability, keeps signature
        rec.payload_json = json.dumps(data, sort_keys=True)
        s.commit()
    try:
        v = lab.client.post(f"/api/agents/{AGENT}/verify")
        t = lab.intent("sticker-pack")
        lab.observed = {"http_status": [v.status_code, t.status_code], "verification": v.json()["valid"], "error": t.json().get("error")}
        lab.expect("Verification of altered payload fails", v.json()["valid"] is False, v.json()["reason"])
        lab.expect("Purchase workflow is blocked", t.status_code == 403 and t.json().get("error") == "MANIFEST_INVALID",
                   f"HTTP {t.status_code} {t.json().get('error')}")
    finally:
        with lab.session() as s:  # restore the fixture
            s.get(AgentManifestRecord, AGENT).payload_json = original
            s.commit()
    back = lab.client.post(f"/api/agents/{AGENT}/verify").json()
    lab.expect("Fixture restored: manifest verifies again", back["valid"] is True, back["reason"])


def s_changed_after_approval(lab: Lab) -> None:
    i = lab.intent("keyboard").json()
    lab.expect("Approval granted for exact details", lab.approve(i).status_code == 200, "approved at USD 89.00")
    results = []
    for field_name, new_value in (("price_cents", 8000), ("seller_name", "Acme Office Supply")):
        with lab.session() as s:
            p = s.get(Product, "keyboard")
            old = getattr(p, field_name)
            setattr(p, field_name, new_value)
            s.commit()
        try:
            r = lab.client.post(f"/api/transactions/{i['id']}/paypal/order")
            results.append((field_name, r.status_code, r.json().get("error")))
            lab.expect(f"Changed {field_name} invalidates approval and blocks order",
                       r.status_code == 409 and r.json().get("error") == "DETAILS_CHANGED", f"HTTP {r.status_code} {r.json().get('error')}")
        finally:
            with lab.session() as s:
                setattr(s.get(Product, "keyboard"), field_name, old)
                s.commit()
    lab.expect("No PayPal order was created by the attack",
               not any(c == ("POST", "/v2/checkout/orders") for c in lab.fake.calls), f"mock PayPal calls: {len(lab.fake.calls)}")
    lab.observed = {"http_status": [r[1] for r in results], "error": [r[2] for r in results]}


def s_expired_or_replayed(lab: Lab) -> None:
    i = lab.intent("keyboard").json()
    lab.approve(i)
    with lab.session() as s:
        a = s.query(Approval).one()
        future = a.expires_at
        a.expires_at = tx.utcnow() - timedelta(seconds=5)
        s.commit()
    exp = lab.client.post(f"/api/transactions/{i['id']}/paypal/order")
    lab.expect("Expired approval is refused", exp.status_code == 409 and exp.json().get("error") == "APPROVAL_EXPIRED",
               f"HTTP {exp.status_code} {exp.json().get('error')}")
    with lab.session() as s:  # restore fixture
        s.query(Approval).one().expires_at = future
        s.commit()
    ok = lab.client.post(f"/api/transactions/{i['id']}/paypal/order")
    lab.expect("Control: fresh approval works exactly once (mock order)", ok.status_code == 200 and ok.json()["state"] == "ORDER_CREATED",
               f"HTTP {ok.status_code}")
    dup = lab.approve(i)
    lab.expect("Second approval request refused", dup.status_code == 409, f"HTTP {dup.status_code} {dup.json().get('error')}")
    with lab.session() as s:  # attacker rewinds the intent to try to reuse the consumed approval
        row = tx.get_intent(s, i["id"])
        row.state, row.paypal_order_id = tx.READY, None
        s.commit()
    rep = lab.client.post(f"/api/transactions/{i['id']}/paypal/order")
    lab.expect("Replayed (already used) approval is refused", rep.status_code == 409 and rep.json().get("error") == "APPROVAL_REPLAYED",
               f"HTTP {rep.status_code} {rep.json().get('error')}")
    lab.observed = {"http_status": [exp.status_code, dup.status_code, rep.status_code],
                    "error": [exp.json().get("error"), dup.json().get("error"), rep.json().get("error")]}


def s_tampered_receipt(lab: Lab) -> None:
    i = lab.intent("sticker-pack").json()
    doc = lab.client.post(f"/api/transactions/{i['id']}/dev-receipt").json()

    def verify(payload):
        return lab.client.post("/api/receipts/verify", json={"payload": payload, "signature_b64": doc["signature_b64"],
                                                             "key_id": doc["key_id"]}).json()

    lab.expect("Control: untouched receipt verifies", verify(doc["payload"])["valid"] is True, "valid")
    outcomes = []
    for fld, val in (("amount", "0.01"), ("product_id", "headphones"), ("transaction_intent_id", "txn_forged")):
        tampered = dict(doc["payload"])
        tampered[fld] = val
        v = verify(tampered)
        outcomes.append(v["valid"])
        lab.expect(f"Altered '{fld}' is detected", v["valid"] is False and v["signature_valid"] is False, v["signature_reason"])
    lab.observed = {"http_status": 200, "tampered_results_valid": outcomes}


def s_duplicate_operations(lab: Lab) -> None:
    i = lab.intent("sticker-pack").json()
    o1 = lab.client.post(f"/api/transactions/{i['id']}/paypal/order").json()
    o2 = lab.client.post(f"/api/transactions/{i['id']}/paypal/order").json()
    lab.expect("Duplicate order request returns the same order", o1["paypal"]["order_id"] == o2["paypal"]["order_id"],
               f"order {o1['paypal']['order_id']}")
    lab.expect("Only one order exists at (mock) PayPal", len(lab.fake.orders) == 1, f"orders={len(lab.fake.orders)}")
    lab.fake.buyer_approves(o1["paypal"]["order_id"])
    c1 = lab.client.post(f"/api/transactions/{i['id']}/paypal/capture")
    c2 = lab.client.post(f"/api/transactions/{i['id']}/paypal/capture")
    lab.expect("Duplicate capture request does not capture twice", lab.fake.capture_calls() == 1,
               f"capture calls to PayPal: {lab.fake.capture_calls()}")
    lab.expect("Both responses agree on one capture", c1.json()["paypal"]["capture_id"] == c2.json()["paypal"]["capture_id"], "same capture id")
    lab.observed = {"http_status": [c1.status_code, c2.status_code], "capture_calls": lab.fake.capture_calls()}


def s_paypal_timeout(lab: Lab) -> None:
    i = lab.intent("sticker-pack").json()
    o = lab.client.post(f"/api/transactions/{i['id']}/paypal/order").json()
    lab.fake.buyer_approves(o["paypal"]["order_id"])
    lab.fake.capture_mode = "timeout"
    t = lab.client.post(f"/api/transactions/{i['id']}/paypal/capture")
    state = lab.client.get(f"/api/transactions/{i['id']}").json()["state"]
    lab.expect("Timeout is reported as UNCERTAIN, not success", t.status_code == 504 and t.json().get("error") == "CAPTURE_UNCERTAIN" and state == "CAPTURE_UNCERTAIN",
               f"HTTP {t.status_code} state={state}")
    lab.fake.capture_mode = "ok"
    retry = lab.client.post(f"/api/transactions/{i['id']}/paypal/capture")
    lab.expect("Blind retry is refused until reconciled", retry.status_code == 409 and lab.fake.capture_calls() == 1,
               f"HTTP {retry.status_code}, capture calls={lab.fake.capture_calls()}")
    receipts = lab.client.get("/api/receipts", params={"intent_id": i["id"]}).json()
    lab.expect("No payment receipt issued for an unconfirmed payment", receipts == [], f"receipts={len(receipts)}")
    lab.observed = {"http_status": [t.status_code, retry.status_code], "state": state}


def _ready_to_capture(lab: Lab, product: str = "sticker-pack") -> dict:
    """Intent (approved if needed) with a mock order that the mock buyer approved. Nothing is captured yet."""
    i = lab.intent(product).json()
    if i["state"] == "AWAITING_INTERNAL_APPROVAL":
        lab.approve(i)
    o = lab.client.post(f"/api/transactions/{i['id']}/paypal/order").json()
    lab.fake.buyer_approves(o["paypal"]["order_id"])
    return i


def _retry(lab: Lab, intent_id: str, key: str, body: dict | None = None):
    return lab.client.post(f"/api/transactions/{intent_id}/paypal/retry", headers={"Idempotency-Key": key}, json=body)


def _evidence_ok(lab: Lab, intent_id: str, **extra) -> dict:
    doc = lab.client.get(f"/api/transactions/{intent_id}/evidence").json()
    return lab.client.post("/api/evidence/verify", json={"events": doc["events"], **extra}).json()


def s_lost_response(lab: Lab) -> None:
    i = _ready_to_capture(lab)
    lab.fake.capture_mode = "lost_response"  # PayPal executes the capture, the answer never arrives
    r = lab.client.post(f"/api/transactions/{i['id']}/paypal/capture")
    now = lab.client.get(f"/api/transactions/{i['id']}").json()
    atts = lab.client.get(f"/api/transactions/{i['id']}/attempts").json()
    cap = [a for a in atts if a["operation"] == "capture"]
    receipts = lab.client.get("/api/receipts", params={"intent_id": i["id"]}).json()
    lab.observed = {"http_status": r.status_code, "state": now["state"], "recovery_status": now["recovery_status"],
                    "captures_executed_at_mock_paypal": lab.fake.captures_executed()}
    lab.expect("The mock processor really executed one capture", lab.fake.captures_executed() == 1,
               f"captures at mock PayPal: {lab.fake.captures_executed()}")
    lab.expect("The caller is NOT told it succeeded", r.status_code == 504 and r.json().get("error") == "CAPTURE_UNCERTAIN",
               f"HTTP {r.status_code} {r.json().get('error')}")
    lab.expect("State is uncertain, not CAPTURED and not FAILED", now["state"] == "CAPTURE_UNCERTAIN", f"state={now['state']}")
    lab.expect("Explicit PENDING_RECONCILIATION marker is exposed", now["recovery_status"] == "PENDING_RECONCILIATION",
               f"recovery_status={now['recovery_status']}")
    lab.expect("No payment receipt is issued for an unconfirmed payment", receipts == [], f"receipts={len(receipts)}")
    lab.expect("The attempt and its idempotency key are persisted with an unknown outcome",
               len(cap) == 1 and cap[0]["outcome"] == "OUTCOME_UNKNOWN" and cap[0]["idempotency_key"] == f"opp-capture-{i['id']}",
               f"attempts={[(a['operation'], a['outcome']) for a in atts]}")


def s_retry_reuses_original(lab: Lab) -> None:
    i = _ready_to_capture(lab)
    lab.fake.capture_mode = "lost_response"
    lab.client.post(f"/api/transactions/{i['id']}/paypal/capture")
    calls_before = lab.fake.capture_calls()
    r1 = _retry(lab, i["id"], "agent-retry-0001")
    b1 = r1.json()
    r2 = _retry(lab, i["id"], "agent-retry-0001")  # the agent repeats the very same retry
    r3 = _retry(lab, i["id"], "agent-retry-0002")
    receipts = lab.client.get("/api/receipts", params={"intent_id": i["id"]}).json()
    atts = lab.client.get(f"/api/transactions/{i['id']}/attempts").json()
    lab.observed = {"http_status": [r1.status_code, r2.status_code, r3.status_code],
                    "retry_outcomes": [x.json().get("retry", {}).get("outcome") for x in (r1, r2, r3)],
                    "capture_requests_sent_during_retries": lab.fake.capture_calls() - calls_before,
                    "captures_executed_at_mock_paypal": lab.fake.captures_executed()}
    lab.expect("Retry is tied to the original intent and reconciled with PayPal",
               r1.status_code == 200 and b1["id"] == i["id"] and b1["retry"]["outcome"] == "RECONCILED" and b1["state"] == "CAPTURED",
               f"HTTP {r1.status_code} outcome={b1.get('retry', {}).get('outcome')} state={b1.get('state')}")
    lab.expect("No second capture request was sent to PayPal", lab.fake.capture_calls() == calls_before,
               f"capture requests before/after: {calls_before}/{lab.fake.capture_calls()}")
    lab.expect("Exactly one capture exists at the processor", lab.fake.captures_executed() == 1,
               f"captures={lab.fake.captures_executed()}")
    lab.expect("Repeating the same Idempotency-Key is recognised as a replay",
               r2.status_code == 200 and r2.json()["retry"]["replay"] is True and r2.json()["retry"]["outcome"] == "REUSED",
               f"replay={r2.json()['retry']['replay']} outcome={r2.json()['retry']['outcome']}")
    lab.expect("A new key still reuses the original result", r3.json()["retry"]["outcome"] == "REUSED"
               and r3.json()["paypal"]["capture_id"] == b1["paypal"]["capture_id"], "same capture id")
    lab.expect("Exactly one payment receipt, issued only after PayPal confirmed",
               len(receipts) == 1 and receipts[0]["receipt_type"] == "PAYMENT_CONFIRMED", f"receipts={len(receipts)}")
    lab.expect("Only one capture attempt was ever made (retries added no capture)",
               sum(1 for a in atts if a["operation"] == "capture") == 1, f"attempts={[a['operation'] for a in atts]}")
    v = _evidence_ok(lab, i["id"])
    lab.expect("Evidence chain verifies and records what PayPal reported",
               v["valid"] is True and any(e["event_type"] == "RECONCILIATION_OBSERVED" or e["event_type"] == "CAPTURE_CONFIRMED"
                                          for e in v["events"]) and any(e["source"] == "PAYPAL_OBSERVED" for e in v["events"]),
               f"{v['event_count']} events, valid={v['valid']}")


def s_unresolved_outcome(lab: Lab) -> None:
    i = _ready_to_capture(lab)
    lab.fake.capture_mode = "lost_response"
    lab.client.post(f"/api/transactions/{i['id']}/paypal/capture")
    lab.fake.order_lookup_fails = True  # PayPal cannot be asked, so the outcome cannot be established
    r = _retry(lab, i["id"], "agent-retry-0001")
    mid = lab.client.get(f"/api/transactions/{i['id']}").json()
    receipts = lab.client.get("/api/receipts", params={"intent_id": i["id"]}).json()
    body = r.json()
    lab.observed = {"http_status": r.status_code, "retry_outcome": body.get("retry", {}).get("outcome"),
                    "state": mid["state"], "recovery_status": mid["recovery_status"]}
    lab.expect("API answers 202 PENDING_RECONCILIATION, not a success and not an error",
               r.status_code == 202 and body["retry"]["outcome"] == "PENDING_RECONCILIATION", f"HTTP {r.status_code} {body.get('retry')}")
    lab.expect("State stays CAPTURE_UNCERTAIN with an explicit marker",
               mid["state"] == "CAPTURE_UNCERTAIN" and mid["recovery_status"] == "PENDING_RECONCILIATION", f"state={mid['state']}")
    lab.expect("No receipt claims a payment while unresolved", receipts == [], f"receipts={len(receipts)}")
    lab.expect("No additional capture request was sent", lab.fake.capture_calls() == 1, f"capture requests={lab.fake.capture_calls()}")
    lab.fake.order_lookup_fails = False  # PayPal is reachable again
    r2 = _retry(lab, i["id"], "agent-retry-0002")
    lab.expect("Once PayPal can be asked, the outcome resolves from PayPal's own data",
               r2.status_code == 200 and r2.json()["state"] == "CAPTURED" and lab.fake.captures_executed() == 1,
               f"HTTP {r2.status_code} state={r2.json().get('state')}")


def s_tampered_evidence(lab: Lab) -> None:
    i = _ready_to_capture(lab)
    lab.client.post(f"/api/transactions/{i['id']}/paypal/capture")
    doc = lab.client.get(f"/api/transactions/{i['id']}/evidence").json()
    events = doc["events"]
    receipt = lab.client.get(f"/api/receipts/{lab.client.get('/api/receipts', params={'intent_id': i['id']}).json()[0]['id']}").json()
    pinned = receipt["payload"]["evidence_reference"]["head_digest"]

    def verify(evts, **extra):
        return lab.client.post("/api/evidence/verify", json={"events": evts, **extra}).json()

    lab.expect("Control: untouched evidence verifies, including the head pinned by the receipt",
               verify(events, expected_head_digest=pinned)["valid"] is True, f"{len(events)} events")
    import copy
    idx = next(n for n, e in enumerate(events) if e["payload"]["event_type"] == "CAPTURE_CONFIRMED")
    cases = []
    a = copy.deepcopy(events); a[idx]["payload"]["status_to"] = "FAILED"; cases.append(("status changed", a, {}))
    b = copy.deepcopy(events); b[idx]["payload"]["source"] = "INTERNAL"; cases.append(("PayPal-observed relabelled as internal", b, {}))
    c = copy.deepcopy(events); del c[1]; cases.append(("an event removed from the middle", c, {}))
    d = copy.deepcopy(events); d[1], d[2] = d[2], d[1]; cases.append(("two events reordered", d, {}))
    e = copy.deepcopy(events); e[idx]["signature_b64"] = events[0]["signature_b64"]; cases.append(("signature swapped", e, {}))
    f = copy.deepcopy(events); del f[idx]; cases.append(("capture confirmation deleted (pinned head missing)", f, {"expected_head_digest": pinned}))
    outcomes = []
    for label, evts, extra in cases:
        v = verify(evts, **extra)
        outcomes.append(v["valid"])
        lab.expect(f"Rejected: {label}", v["valid"] is False,
                   (v["issues"] or [x["issues"] for x in v["events"] if x["issues"]][:1] or ["no issue reported"])[0].__str__()[:140])
    lab.observed = {"http_status": 200, "tampered_results_valid": outcomes}


def s_altered_retry(lab: Lab) -> None:
    k = lab.intent("keyboard").json()
    lab.approve(k)  # approved at 89.00, order not yet created
    r = _retry(lab, k["id"], "agent-retry-0001", {"amount": "0.01"})
    after = lab.client.post(f"/api/transactions/{k['id']}/paypal/order")
    lab.expect("Retry with a changed amount is rejected", r.status_code == 409 and r.json().get("error") == "RETRY_DETAILS_MISMATCH"
               and r.json().get("altered_fields") == ["amount"], f"HTTP {r.status_code} {r.json().get('error')} {r.json().get('altered_fields')}")
    lab.expect("The unused approval was revoked", r.json().get("approval_revoked") is True, "approval_revoked=True")
    lab.expect("The old approval cannot be used to create an order afterwards",
               after.status_code == 409 and after.json().get("error") == "APPROVAL_REPLAYED",
               f"HTTP {after.status_code} {after.json().get('error')}")
    lab.expect("No PayPal order was created by either attempt", len(lab.fake.orders) == 0, f"mock orders={len(lab.fake.orders)}")
    k2 = lab.intent("keyboard").json()  # still awaiting approval
    other = lab.intent("monitor-stand").json()
    swap = lab.client.post(f"/api/transactions/{k2['id']}/approve", json={"approver": "attack-lab", "details_digest": other["details_digest"]})
    lab.expect("An approval carrying another transaction's details digest is refused",
               swap.status_code == 409 and swap.json().get("error") == "DIGEST_MISMATCH", f"HTTP {swap.status_code} {swap.json().get('error')}")
    s = _ready_to_capture(lab)
    lab.client.post(f"/api/transactions/{s['id']}/paypal/capture")
    sent = lab.fake.capture_calls()
    r2 = _retry(lab, s["id"], "agent-retry-0003", {"product_id": "headphones", "seller_name": "Gray Market Gadgets"})
    lab.expect("Retry naming a different product/seller on a captured intent is rejected",
               r2.status_code == 409 and sorted(r2.json().get("altered_fields", [])) == ["product_id", "seller_name"],
               f"HTTP {r2.status_code} fields={r2.json().get('altered_fields')}")
    lab.expect("Nothing more was sent to PayPal", lab.fake.capture_calls() == sent, f"capture requests={lab.fake.capture_calls()}")
    ev = _evidence_ok(lab, s["id"])
    lab.expect("The rejected retry is on the signed evidence trail",
               ev["valid"] is True and any(x["event_type"] == "RETRY_REJECTED_ALTERED_DETAILS" for x in ev["events"]), f"{ev['event_count']} events")
    lab.observed = {"http_status": [r.status_code, after.status_code, swap.status_code, r2.status_code],
                    "error": [r.json().get("error"), after.json().get("error"), swap.json().get("error"), r2.json().get("error")]}


def s_concurrent_duplicates(lab: Lab) -> None:
    from concurrent.futures import ThreadPoolExecutor
    i = lab.intent("sticker-pack").json()
    with ThreadPoolExecutor(max_workers=8) as pool:
        orders = list(pool.map(lambda _: lab.client.post(f"/api/transactions/{i['id']}/paypal/order"), range(8)))
    lab.expect("8 concurrent order requests create exactly one mock order", len(lab.fake.orders) == 1,
               f"mock orders={len(lab.fake.orders)}")
    lab.expect("No concurrent order request crashed", all(o.status_code in (200, 409) for o in orders),
               f"statuses={sorted(o.status_code for o in orders)}")
    oid = next(iter(lab.fake.orders))
    lab.fake.buyer_approves(oid)

    def hit(n: int):
        if n % 2:
            return lab.client.post(f"/api/transactions/{i['id']}/paypal/capture")
        return _retry(lab, i["id"], f"agent-retry-{n % 4:04d}-xx")  # several workers share a key on purpose

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(hit, range(16)))
    state = lab.client.get(f"/api/transactions/{i['id']}").json()
    receipts = lab.client.get("/api/receipts", params={"intent_id": i["id"]}).json()
    atts = lab.client.get(f"/api/transactions/{i['id']}/attempts").json()
    v = _evidence_ok(lab, i["id"])
    lab.observed = {"http_status": sorted(r.status_code for r in results), "captures_executed_at_mock_paypal": lab.fake.captures_executed(),
                    "final_state": state["state"]}
    lab.expect("16 concurrent capture/retry requests produce no server error", all(r.status_code < 500 for r in results),
               f"statuses={sorted(set(r.status_code for r in results))}")
    lab.expect("Exactly one capture request reached PayPal", lab.fake.capture_calls() == 1, f"capture requests={lab.fake.capture_calls()}")
    lab.expect("Exactly one capture executed", lab.fake.captures_executed() == 1, f"captures={lab.fake.captures_executed()}")
    lab.expect("Final state is CAPTURED", state["state"] == "CAPTURED", f"state={state['state']}")
    lab.expect("Exactly one receipt", len(receipts) == 1, f"receipts={len(receipts)}")
    lab.expect("One capture attempt row, even though many requests raced",
               sum(1 for a in atts if a["operation"] == "capture") == 1, f"capture attempts={sum(1 for a in atts if a['operation'] == 'capture')}")
    lab.expect("Evidence stayed a single valid chain (no sequence gaps or forks)", v["valid"] is True,
               f"{v['event_count']} events, valid={v['valid']}")


RUNNERS = {
    "lost_response_capture": s_lost_response, "retry_reuses_original": s_retry_reuses_original,
    "unresolved_outcome": s_unresolved_outcome, "tampered_evidence": s_tampered_evidence,
    "altered_retry_details": s_altered_retry, "concurrent_duplicates": s_concurrent_duplicates,
    "over_limit": s_over_limit, "unapproved_or_unknown": s_unapproved_or_unknown,
    "tampered_manifest": s_tampered_manifest, "changed_after_approval": s_changed_after_approval,
    "expired_or_replayed_approval": s_expired_or_replayed, "tampered_receipt": s_tampered_receipt,
    "duplicate_operations": s_duplicate_operations, "paypal_timeout_uncertain": s_paypal_timeout,
}


def run_scenario(scenario_id: str) -> dict:
    meta = next(s for s in SCENARIOS if s["id"] == scenario_id)
    with sandbox() as lab:
        try:
            RUNNERS[scenario_id](lab)
            error = None
        except Exception as exc:  # a crashed scenario is a FAIL, never a silent pass
            error = f"{type(exc).__name__}: {exc}"
    passed = error is None and bool(lab.checks) and all(c["ok"] for c in lab.checks)
    failed = [c["check"] for c in lab.checks if not c["ok"]]
    reason = (f"Scenario errored: {error}" if error else
              "Defense held: " + meta["defense"] if passed else "Defense did NOT hold: " + "; ".join(failed))
    return {**meta, "result": "PASS" if passed else "FAIL", "reason": reason, "observed": lab.observed,
            "checks": lab.checks, "sandbox_notice": SANDBOX_NOTICE,
            "label": "MOCKED PayPal (no real payment)" if meta["mocked_paypal"] else "Real backend code, no PayPal involved"}
