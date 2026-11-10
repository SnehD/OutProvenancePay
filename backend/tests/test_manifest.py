import json

from app.models import AgentManifestRecord
from app.services import manifest as m
from app.services.crypto import KeyStore, canonical_json


def test_canonical_json_is_deterministic_and_rejects_floats():
    assert canonical_json({"b": 1, "a": [2, {"d": 1, "c": 2}]}) == canonical_json({"a": [2, {"c": 2, "d": 1}], "b": 1})
    import pytest
    with pytest.raises(TypeError):
        canonical_json({"price": 1.5})


def test_seeded_manifest_verifies(client):
    r = client.post("/api/agents/agent-shopper-001/verify")
    assert r.status_code == 200 and r.json()["valid"] is True


def test_unknown_agent_404(client):
    assert client.post("/api/agents/nope/verify").status_code == 404


def test_tampered_payload_with_original_signature_rejected(app, client):
    with app.state.session_factory() as s:
        rec = s.get(AgentManifestRecord, "agent-shopper-001")
        payload = json.loads(rec.payload_json)
        payload["capabilities"].append("transfer_funds")  # attacker adds a capability
        rec.payload_json = json.dumps(payload, sort_keys=True)  # signature left unchanged
        s.commit()
    body = client.post("/api/agents/agent-shopper-001/verify").json()
    assert body["valid"] is False and "altered" in body["reason"]


def test_signature_from_unknown_key_rejected(app, tmp_path):
    other = KeyStore(tmp_path / "other-keys")
    other.ensure("manifest-issuer")
    payload = m.build_default_payload(other)
    signed = other.sign("manifest-issuer", payload)
    result, _ = m.verify_manifest(app.state.keystore, json.dumps(payload), signed.signature_b64, signed.key_id)
    assert result.valid is False and "Unknown signing key" in result.reason


def test_payload_key_id_must_match_signer(app):
    ks = app.state.keystore
    ks.ensure("other-signer")
    payload = m.build_default_payload(ks)  # claims manifest-issuer's key id
    signed = ks.sign("other-signer", payload)  # but signed by a different (trusted) key
    result, _ = m.verify_manifest(ks, json.dumps(payload), signed.signature_b64, signed.key_id)
    assert result.valid is False


def test_private_key_stored_only_under_data_dir(settings, app):
    assert list(settings.keys_dir.glob("*.private.pem"))
