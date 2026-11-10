"""Canonical JSON, SHA-256 digests, Ed25519 signing/verification and a local key store.

Signature verification proves integrity relative to a trusted public key. It does not prove
that the signed claims are true or who the signer is in the real world.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

ALGORITHM = "Ed25519"


def _reject_floats(obj: object) -> None:
    if isinstance(obj, float):
        raise TypeError("Floats are not allowed in signed payloads; use strings for decimals.")
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                raise TypeError("Signed payload keys must be strings.")
            _reject_floats(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _reject_floats(v)


def canonical_json(obj: object) -> bytes:
    """Deterministic UTF-8 JSON: sorted keys, no whitespace, no floats, no NaN."""
    _reject_floats(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_of(obj: object) -> str:
    return sha256_hex(canonical_json(obj))


def key_id_for(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return "ed25519:" + sha256_hex(raw)[:16]


def public_key_b64(public_key: Ed25519PublicKey) -> str:
    raw = public_key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


@dataclass(frozen=True)
class SignedBlob:
    key_id: str
    algorithm: str
    digest_sha256: str
    signature_b64: str


@dataclass(frozen=True)
class VerifyResult:
    valid: bool
    reason: str
    digest_sha256: str | None = None
    key_id: str | None = None

    def to_dict(self) -> dict:
        return {"valid": self.valid, "reason": self.reason, "digest_sha256": self.digest_sha256, "key_id": self.key_id}


class KeyStore:
    """Loads (or securely generates) named Ed25519 keys under a git-ignored directory.

    Private keys never leave this object except through `sign`. Public keys of every
    key ever generated here are the trust set used by `verify`.
    """

    def __init__(self, keys_dir: Path) -> None:
        self.keys_dir = keys_dir
        self.keys_dir.mkdir(parents=True, exist_ok=True)
        self._private: dict[str, Ed25519PrivateKey] = {}
        self._public_by_id: dict[str, Ed25519PublicKey] = {}

    def _path(self, name: str) -> Path:
        return self.keys_dir / f"{name}.private.pem"

    def ensure(self, name: str) -> str:
        """Load key `name`, generating it if absent. Returns its key id."""
        if name not in self._private:
            path = self._path(name)
            if path.is_file():
                key = serialization.load_pem_private_key(path.read_bytes(), password=None)
                if not isinstance(key, Ed25519PrivateKey):
                    raise ValueError(f"Key {name} is not an Ed25519 key.")
            else:
                key = Ed25519PrivateKey.generate()
                pem = key.private_bytes(
                    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
                )
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as fh:
                    fh.write(pem)
            self._private[name] = key
            self._public_by_id[key_id_for(key.public_key())] = key.public_key()
        return key_id_for(self._private[name].public_key())

    def key_id(self, name: str) -> str:
        return self.ensure(name)

    def public_key_b64(self, name: str) -> str:
        self.ensure(name)
        return public_key_b64(self._private[name].public_key())

    def sign(self, name: str, payload: object) -> SignedBlob:
        self.ensure(name)
        data = canonical_json(payload)
        key = self._private[name]
        return SignedBlob(
            key_id=key_id_for(key.public_key()),
            algorithm=ALGORITHM,
            digest_sha256=sha256_hex(data),
            signature_b64=base64.b64encode(key.sign(data)).decode("ascii"),
        )

    def trusted_key_ids(self) -> list[str]:
        return sorted(self._public_by_id)

    def verify(self, payload: object, signature_b64: str, key_id: str) -> VerifyResult:
        """Recompute the digest from `payload` and verify the signature. Never trusts stored flags."""
        try:
            data = canonical_json(payload)
        except (TypeError, ValueError) as exc:
            return VerifyResult(False, f"Payload cannot be canonicalised: {exc}", None, key_id)
        digest = sha256_hex(data)
        public = self._public_by_id.get(key_id)
        if public is None:
            return VerifyResult(False, "Unknown signing key id: not in the trusted key set.", digest, key_id)
        try:
            sig = base64.b64decode(signature_b64, validate=True)
        except (ValueError, TypeError):
            return VerifyResult(False, "Signature is not valid base64.", digest, key_id)
        try:
            public.verify(sig, data)
        except InvalidSignature:
            return VerifyResult(False, "Signature does not match the payload (payload or signature was altered).",
                                digest, key_id)
        return VerifyResult(True, "Signature is valid for this exact payload and trusted key.", digest, key_id)
