"""Agent manifest endpoints."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..models import AgentManifestRecord
from ..services import manifest as manifest_svc
from .deps import get_db

router = APIRouter(prefix="/api/agents", tags=["agents"])

TRUST_NOTE = (
    "A valid signature proves the manifest is unchanged since it was signed by the trusted key. "
    "It does not prove the claims in it are true or establish the agent's real-world identity."
)


@router.get("/{agent_id}/manifest")
def get_manifest(agent_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    record = db.get(AgentManifestRecord, agent_id)
    if record is None:
        raise HTTPException(404, "Unknown agent.")
    return {
        "payload": json.loads(record.payload_json),
        "signature_b64": record.signature_b64,
        "key_id": record.key_id,
        "algorithm": "Ed25519",
        "digest_sha256": record.digest_sha256,
        "issuer_public_key_b64": request.app.state.keystore.public_key_b64(manifest_svc.MANIFEST_KEY_NAME),
    }


@router.post("/{agent_id}/verify")
def verify(agent_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    """Re-verifies the stored manifest from scratch (signature recomputed every call)."""
    if db.get(AgentManifestRecord, agent_id) is None:
        raise HTTPException(404, "Unknown agent.")
    result, _ = manifest_svc.verify_stored_manifest(db, request.app.state.keystore, agent_id)
    return {**result.to_dict(), "agent_id": agent_id, "note": TRUST_NOTE}
