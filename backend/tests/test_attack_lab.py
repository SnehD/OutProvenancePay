import pytest

from app.services import attack_lab as lab


@pytest.mark.parametrize("scenario", [s["id"] for s in lab.SCENARIOS])
def test_each_scenario_passes_from_real_execution(client, scenario):
    r = client.post(f"/api/attack-lab/run/{scenario}")
    body = r.json()
    assert r.status_code == 200
    assert body["checks"], "a scenario must execute real checks"
    assert body["result"] == "PASS", [c for c in body["checks"] if not c["ok"]]


def test_unknown_scenario_404(client):
    assert client.post("/api/attack-lab/run/nope").status_code == 404


def test_run_all_counts_match(client):
    body = client.post("/api/attack-lab/run-all").json()
    assert body["total"] == 14 and body["passed"] == 14


def test_attack_lab_does_not_touch_real_data(app, client):
    from app.models import AgentManifestRecord, Product, TransactionIntent
    with app.state.session_factory() as s:
        before = (s.get(Product, "keyboard").price_cents, s.get(AgentManifestRecord, "agent-shopper-001").payload_json)
    client.post("/api/attack-lab/run-all")
    with app.state.session_factory() as s:
        after = (s.get(Product, "keyboard").price_cents, s.get(AgentManifestRecord, "agent-shopper-001").payload_json)
        assert s.query(TransactionIntent).count() == 0
    assert before == after


def test_scenario_reports_fail_when_defense_is_broken(monkeypatch):
    """Guard against hardcoded PASS: break a defense and the lab must say FAIL."""
    from app.services import policy
    real = policy.evaluate_purchase

    def broken(session, product_id, **kw):
        r = real(session, product_id, **kw)
        if product_id == "headphones":  # pretend the limit check is missing
            return policy.PolicyResult(policy.Decision.ALLOW, ["bug"], product_id=r.product_id, product_name=r.product_name,
                                       seller_name=r.seller_name, amount=r.amount, currency=r.currency, codes=["BUG"])
        return r

    monkeypatch.setattr(policy, "evaluate_purchase", broken)
    assert lab.run_scenario("over_limit")["result"] == "FAIL"
