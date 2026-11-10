"""Versioned, signed agent manifest: build, persist, verify."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from ..models import AgentManifestRecord
from .crypto import KeyStore, VerifyResult, digest_of

MANIFEST_KEY_NAME = "manifest-issuer"
DEFAULT_AGENT_ID = "agent-shopper-001"
SCHEMA_VERSION = "1.0"


class ManifestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(pattern=r"^\d+\.\d+$")
    agent_id: str = Field(min_length=1, max_length=64)
    agent_version: str = Field(min_length=1, max_length=32)
    capabilities: list[str] = Field(min_length=1)
    allowed_transaction_categories: list[str] = Field(min_length=1)
    issuer: str = Field(min_length=1, max_length=120)
    key_id: str = Field(min_length=1, max_length=64)
    issued_at: str


def build_default_payload(keystore: KeyStore) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "agent_id": DEFAULT_AGENT_ID,
        "agent_version": "1.0.0",
        "capabilities": ["browse_catalogue", "propose_purchase"],
        "allowed_transaction_categories": ["office", "electronics", "home"],
        "issuer": "OutProvenance Dev Issuer (local development key)",
        "key_id": keystore.key_id(MANIFEST_KEY_NAME),
        "issued_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def seed_manifest(session: Session, keystore: KeyStore) -> None:
    if session.get(AgentManifestRecord, DEFAULT_AGENT_ID) is not None:
        return
    payload = build_default_payload(keystore)
    signed = keystore.sign(MANIFEST_KEY_NAME, payload)
    session.add(AgentManifestRecord(
        agent_id=payload["agent_id"],
        payload_json=json.dumps(payload, sort_keys=True),
        signature_b64=signed.signature_b64,
        key_id=signed.key_id,
        digest_sha256=signed.digest_sha256,
    ))
    session.commit()


def verify_manifest(keystore: KeyStore, payload_json: str, signature_b64: str, key_id: str) -> tuple[VerifyResult, dict | None]:
    """Verify signature first, then schema, then that the payload's key_id matches the signer."""
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        return VerifyResult(False, "Manifest payload is not valid JSON.", None, key_id), None
    result = keystore.verify(payload, signature_b64, key_id)
    if not result.valid:
        return result, None
    try:
        parsed = ManifestPayload.model_validate(payload)
    except ValidationError:
        return VerifyResult(False, "Signature valid but manifest does not match the required schema.",
                            result.digest_sha256, key_id), None
    if parsed.key_id != key_id:
        return VerifyResult(False, "Manifest key_id does not match the signing key.", result.digest_sha256, key_id), None
    return result, payload


def verify_stored_manifest(session: Session, keystore: KeyStore, agent_id: str) -> tuple[VerifyResult, dict | None]:
    record = session.get(AgentManifestRecord, agent_id)
    if record is None:
        return VerifyResult(False, "No manifest is registered for this agent."), None
    result, payload = verify_manifest(keystore, record.payload_json, record.signature_b64, record.key_id)
    if result.valid and record.digest_sha256 != digest_of(payload):
        return VerifyResult(False, "Stored digest does not match the payload.", result.digest_sha256, record.key_id), None
    return result, payload
