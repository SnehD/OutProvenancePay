def test_health_without_credentials(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "not configured" in body["paypal"]
    assert "fallback" in body["ai"]


def test_products_use_trusted_prices(client):
    r = client.get("/api/products")
    assert r.status_code == 200
    by_id = {p["id"]: p for p in r.json()}
    assert by_id["keyboard"]["price"] == "89.00"
    assert by_id["gadget-gray"]["seller_approved"] is False


def test_policies_endpoint(client):
    body = client.get("/api/policies").json()
    assert body["max_purchase"] == "100.00" and body["approval_threshold"] == "75.00"
    assert "Acme Office Supply" in body["approved_sellers"]


def test_evaluate_endpoint_decisions(client):
    def decide(pid, **extra):
        return client.post("/api/policies/evaluate", json={"product_id": pid, **extra})

    assert decide("sticker-pack").json()["decision"] == "ALLOW"
    assert decide("keyboard").json()["decision"] == "REQUIRE_APPROVAL"
    assert decide("headphones").json()["decision"] == "DENY"
    assert decide("gadget-gray").json()["decision"] == "DENY"


def test_evaluate_rejects_bad_input(client):
    assert client.post("/api/policies/evaluate", json={}).status_code == 422
    assert client.post("/api/policies/evaluate", json={"product_id": "keyboard", "price": "1"}).status_code == 422
    r = client.post("/api/policies/evaluate", json={"product_id": "keyboard", "claimed_amount": "NaN"})
    assert r.status_code == 422


def test_evaluate_ignores_client_price_claim(client):
    r = client.post("/api/policies/evaluate", json={"product_id": "headphones", "claimed_amount": "1.00"})
    body = r.json()
    assert body["decision"] == "DENY" and body["amount"] == "129.00"


def test_refuses_to_start_against_live_paypal(tmp_path):
    import pytest
    from app.config import Settings
    from app.main import create_app
    for host in ("https://api-m.paypal.com", "https://api.paypal.com/"):
        with pytest.raises(RuntimeError, match="LIVE"):
            create_app(Settings(data_dir=tmp_path / "d", paypal_client_id="x", paypal_client_secret="y", paypal_base_url=host.rstrip("/")))
    create_app(Settings(data_dir=tmp_path / "ok", paypal_base_url="https://api-m.sandbox.paypal.com"))  # sandbox is fine


def test_attack_lab_refuses_overlapping_runs(client):
    from app.api import attack_lab as api
    assert api._busy.acquire(blocking=False)
    try:
        r = client.post("/api/attack-lab/run/over_limit")
        assert r.status_code == 429 and r.json()["error"] == "ATTACK_LAB_BUSY"
        assert client.post("/api/attack-lab/run-all").status_code == 429
    finally:
        api._busy.release()
    assert client.post("/api/attack-lab/run/over_limit").json()["result"] == "PASS"
