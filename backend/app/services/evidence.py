"""Linked, signed evidence for a purchase lifecycle (TRACE-inspired).

Each event is canonical JSON, hash-linked to the previous event of the same intent and signed with
Ed25519. This is *inspired by* trace/transparency ideas; it is NOT a conformant TRACE or SCITT
implementation (no registered schema, no transparency service, no third-party receipts).

What a valid chain proves: the events are unchanged, in order, and signed by a trusted backend key.
What it does NOT prove: that every claim is true. Each event says where its facts came from:
  PAYPAL_OBSERVED - read by this backend from a PayPal server API response
  INTERNAL        - recorded by this application (an internal decision or state change)
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import EvidenceEvent
from .crypto import KeyStore

EVIDENCE_KEY_NAME = "evidence-signer"
SCHEMA = "opp-evidence/1"
SOURCE_PAYPAL = "PAYPAL_OBSERVED"
SOURCE_INTERNAL = "INTERNAL"
SOURCES = {SOURCE_PAYPAL, SOURCE_INTERNAL}

PROFILE_NOTE = (
    "TRACE-inspired evidence. Not a conformant TRACE or SCITT implementation. A valid chain proves the "
    "events are unchanged, ordered and signed by a trusted key; it does not prove each claim is true."
)
BASIS = {
    SOURCE_PAYPAL: "Observed in a PayPal server API response received by this backend.",
    SOURCE_INTERNAL: "Recorded by this application. Not independently observed.",
}
REQUIRED = {"schema", "event_id", "intent_id", "seq", "event_type", "source", "recorded_at", "prev_event_digest",
            "refs", "status_from", "status_to", "paypal_observation", "claim_basis", "note"}
REF_KEYS = ("approval_id", "details_digest", "attempt_id", "idempotency_key", "paypal_order_id",
            "paypal_capture_id", "receipt_id")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def append(session: Session, keystore: KeyStore, intent_id: str, event_type: str, source: str, *,
           refs: dict | None = None, status_from: str | None = None, status_to: str | None = None,
           observation: dict | None = None, note: str | None = None) -> EvidenceEvent:
    """Append one signed event. Safe under concurrency: (intent_id, seq) is unique and we retry on conflict."""
    if source not in SOURCES:
        raise ValueError(f"Unknown evidence source {source!r}")
    clean_refs = {k: (refs or {}).get(k) for k in REF_KEYS}
    for _ in range(25):
        last = session.scalars(select(EvidenceEvent).where(EvidenceEvent.intent_id == intent_id)
                               .order_by(EvidenceEvent.seq.desc())).first()
        seq = 0 if last is None else last.seq + 1
        event_id = f"evt_{uuid.uuid4().hex[:20]}"
        payload = {
            "schema": SCHEMA, "event_id": event_id, "intent_id": intent_id, "seq": seq,
            "event_type": event_type, "source": source, "recorded_at": _now(),
            "prev_event_digest": None if last is None else last.digest_sha256,
            "refs": clean_refs, "status_from": status_from, "status_to": status_to,
            "paypal_observation": observation if source == SOURCE_PAYPAL else None,
            "claim_basis": BASIS[source], "note": note,
        }
        signed = keystore.sign(EVIDENCE_KEY_NAME, payload)
        row = EvidenceEvent(id=event_id, intent_id=intent_id, seq=seq, event_type=event_type, source=source,
                            payload_json=json.dumps(payload, sort_keys=True), signature_b64=signed.signature_b64,
                            key_id=signed.key_id, digest_sha256=signed.digest_sha256, created_at=_naive_now())
        session.add(row)
        try:
            session.commit()
            return row
        except IntegrityError:  # another request appended the same seq first: re-read the head and retry
            session.rollback()
    raise RuntimeError("Could not append evidence after repeated conflicts.")


def events_for(session: Session, intent_id: str) -> list[EvidenceEvent]:
    return list(session.scalars(select(EvidenceEvent).where(EvidenceEvent.intent_id == intent_id)
                                .order_by(EvidenceEvent.seq)))


def head(session: Session, intent_id: str) -> dict | None:
    rows = events_for(session, intent_id)
    if not rows:
        return None
    return {"schema": SCHEMA, "intent_id": intent_id, "event_count": len(rows),
            "head_event_id": rows[-1].id, "head_digest": rows[-1].digest_sha256}


def document(keystore: KeyStore, session: Session, intent_id: str) -> dict:
    rows = events_for(session, intent_id)
    return {
        "schema": SCHEMA, "profile_note": PROFILE_NOTE, "intent_id": intent_id,
        "algorithm": "Ed25519", "signer_public_key_b64": keystore.public_key_b64(EVIDENCE_KEY_NAME),
        "canonicalization": "JSON, UTF-8, sorted keys, separators (',', ':'), no floats",
        "head_digest": rows[-1].digest_sha256 if rows else None,
        "events": [{"payload": json.loads(r.payload_json), "signature_b64": r.signature_b64, "key_id": r.key_id,
                    "digest_sha256": r.digest_sha256} for r in rows],
    }


def verify_chain(keystore: KeyStore, events: list, expected_head_digest: str | None = None) -> dict:
    """Verify submitted events only. Digests are recomputed; stored 'valid' flags and digests are ignored."""
    issues: list[str] = []
    results: list[dict] = []
    prev_digest: str | None = None
    seen: set = set()
    intent_id = None
    digests: list[str] = []
    for i, ev in enumerate(events):
        item: dict = {"index": i, "event_id": None, "event_type": None, "source": None,
                      "signature_valid": False, "reason": "", "issues": []}
        results.append(item)
        if not isinstance(ev, dict) or not isinstance(ev.get("payload"), dict):
            item["issues"].append("Event must be an object with a payload object.")
            item["reason"] = "Malformed event."
            digests.append("")
            prev_digest = None
            continue
        payload = ev["payload"]
        item.update(event_id=payload.get("event_id"), event_type=payload.get("event_type"), source=payload.get("source"))
        sig = keystore.verify(payload, str(ev.get("signature_b64", "")), str(ev.get("key_id", "")))
        item["signature_valid"], item["reason"] = sig.valid, sig.reason
        digests.append(sig.digest_sha256 or "")
        if not sig.valid:
            item["issues"].append("Signature does not verify for this exact payload.")
        missing = REQUIRED - set(payload)
        if missing:
            item["issues"].append(f"Missing fields: {', '.join(sorted(missing))}")
        if payload.get("schema") != SCHEMA:
            item["issues"].append("Unknown schema.")
        source = payload.get("source")
        if source not in SOURCES:
            item["issues"].append("Unknown source label.")
        elif source == SOURCE_PAYPAL and not payload.get("paypal_observation"):
            item["issues"].append("PAYPAL_OBSERVED event carries no PayPal observation.")
        elif source == SOURCE_INTERNAL and payload.get("paypal_observation"):
            item["issues"].append("INTERNAL event must not carry a PayPal observation.")
        if payload.get("seq") != i:
            item["issues"].append(f"Sequence is {payload.get('seq')!r}, expected {i}: an event was removed, added or reordered.")
        if payload.get("prev_event_digest") != prev_digest:
            item["issues"].append("prev_event_digest does not match the previous event: the chain is broken.")
        if payload.get("event_id") in seen:
            item["issues"].append("Duplicate event_id.")
        seen.add(payload.get("event_id"))
        if intent_id is None:
            intent_id = payload.get("intent_id")
        elif payload.get("intent_id") != intent_id:
            item["issues"].append("Event belongs to a different intent.")
        prev_digest = sig.digest_sha256
    if not events:
        issues.append("No events submitted.")
    if expected_head_digest is not None and expected_head_digest not in digests:
        issues.append("The pinned head digest (e.g. from a receipt) is not in this chain: events were removed or altered.")
    bad = [r for r in results if r["issues"] or not r["signature_valid"]]
    return {
        "valid": bool(events) and not bad and not issues,
        "event_count": len(events), "intent_id": intent_id,
        "head_digest": digests[-1] if digests else None,
        "events": results, "issues": issues, "note": PROFILE_NOTE,
    }
