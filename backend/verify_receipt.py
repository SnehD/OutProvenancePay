"""Standalone receipt verifier. Needs only the `cryptography` package, not the backend.

Usage:
  python verify_receipt.py receipt.json --public-key <base64 Ed25519 public key>

Get the public key from a source you trust (not from the receipt itself). If --public-key is
omitted the key embedded in the file is used, which only checks internal consistency.
Exit code 0 = signature valid, 1 = invalid.
"""
import argparse
import base64
import hashlib
import json
import sys

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--public-key", help="base64 raw Ed25519 public key you trust")
    args = ap.parse_args()
    with open(args.file, encoding="utf-8") as fh:
        doc = json.load(fh)
    pub_b64 = args.public_key or doc.get("signer_public_key_b64")
    if not args.public_key:
        print("WARNING: using the public key embedded in the file; supply --public-key to check trust.")
    data = canonical(doc["payload"])
    print("recomputed sha256:", hashlib.sha256(data).hexdigest())
    try:
        Ed25519PublicKey.from_public_bytes(base64.b64decode(pub_b64)).verify(base64.b64decode(doc["signature_b64"]), data)
    except (InvalidSignature, ValueError, TypeError, KeyError):
        print("RESULT: INVALID signature (content altered, wrong key or malformed).")
        return 1
    print("RESULT: VALID signature. This proves integrity, not that every claim is true.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
