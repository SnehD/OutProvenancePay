# Architecture

OutProvenance Pay is a safety and evidence layer for AI-agent payments. The rule that shapes everything:
**the AI suggests, the deterministic backend decides, a human approves, PayPal confirms the money.**

Related: [PAYPAL_INTEGRATION.md](PAYPAL_INTEGRATION.md) · [AI_USAGE.md](AI_USAGE.md) · [THREAT_MODEL.md](THREAT_MODEL.md) ·
[KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)

## 1. System context

```mermaid
flowchart LR
    U[User / approver] -->|browser| FE[React frontend<br/>view only, no secrets]
    FE -->|JSON over HTTP| BE[FastAPI backend<br/>policy, approvals, signing, payments]
    BE -->|redacted text only| AI[(Optional AI provider<br/>OpenAI-compatible)]
    BE -->|server-side OAuth + Orders v2| PP[(PayPal Sandbox)]
    BE --> DB[(SQLite<br/>backend/data)]
    BE --> K[(Ed25519 key files<br/>backend/data/keys)]
    U -.buyer approval on paypal.com.-> PP
```

## 2. Component responsibilities

| Component | Responsibility | Never does |
|-----------|----------------|------------|
| Frontend (`frontend/`, React + TypeScript + Vite) | Show state, send product IDs and button presses | Decide, price, approve or confirm payment; hold secrets |
| API routers (`backend/app/api/`) | Thin HTTP layer, turn `TxError` into JSON errors | Contain business rules |
| Privacy filter (`services/privacy.py`) | Redact emails, phone numbers, card-like numbers | Guarantee all PII is removed (best-effort regex) |
| AI (`services/ai.py`) | Suggest one catalogue product id | Set price, pick seller, decide policy, approve, sign, capture |
| Catalogue (`services/catalogue.py`) | The only source of price and seller | Accept client-supplied prices |
| Manifest (`services/manifest.py`) | Build, store and verify the signed agent manifest | Trust an unsigned or edited manifest |
| Policy engine (`services/policy.py`) | ALLOW / REQUIRE_APPROVAL / DENY from fixed rules | Use AI or client input to decide |
| Transactions (`services/transactions.py`) | Intent state machine, approvals, `assert_payable` | Skip re-validation before money moves |
| Payments (`services/payments.py`, `paypal.py`) | Create and capture the PayPal order, reconcile | Mark success without PayPal's API saying so |
| Recovery (`services/recovery.py`, `attempts.py`) | Safe agent retries, persisted attempts | Re-send a capture before checking PayPal |
| Receipts (`services/receipts.py`) | Signed receipts, independent verification | Issue a payment receipt without a confirmed capture |
| Evidence (`services/evidence.py`) | Signed, hash-linked event chain, verification | Claim a valid signature means a claim is true |
| Crypto (`services/crypto.py`) | Canonical JSON, SHA-256, Ed25519, `KeyStore` | Float values in signed data |
| Attack Lab (`services/attack_lab.py`, `mock_paypal.py`) | Real attacks on a disposable copy with a mock PayPal | Touch real data, keys or PayPal |

## 3. Trust boundaries

```mermaid
flowchart TB
    subgraph Untrusted
      B[Browser / any API client]
      A[AI output]
    end
    subgraph Trusted["Trusted: backend process"]
      V[Validation + policy + approvals]
      S[Signing keys]
    end
    subgraph External
      P[PayPal server API = source of truth for payment status]
    end
    B -->|any JSON, replays, duplicates| V
    A -->|schema-checked suggestion| V
    V <-->|HTTPS, server-side credentials| P
    V --- S
```

1. **Browser -> backend.** Untrusted. It can send any JSON, replay and duplicate requests.
2. **AI -> backend.** Output is untrusted input. Input to the AI is redacted text only.
3. **Backend <-> PayPal.** PayPal's server API is the only source of truth for payment status. A browser redirect back from PayPal is **not** proof of payment.
4. **Backend <-> disk.** Keys and the database live in `backend/data/` (git-ignored). Disk access means key compromise.

## 4. Frontend / backend separation

The frontend (`services/api.ts` is its single typed client; base URL from `VITE_API_BASE_URL`) sends IDs and button
presses. Prices, sellers, decisions, approval validity, payment status, signatures and evidence all come from the
backend. There is no PayPal SDK, client ID, secret or policy logic in the browser. Pages: Overview,
Rogue Agent, Product Catalogue, Purchase Request, Privacy Preview, Agent Verification, Policy Decision, Approval,
PayPal Checkout, Recovery & Evidence, Receipt Verification, Attack Lab.

## 5. The AI boundary

The AI receives only redacted text and may return only `{product_id, rationale}`. The reply is validated with a strict
schema (`extra="forbid"`) and the id must exist in the trusted catalogue. A valid suggestion then goes through the same
policy engine as any other request. Details in [AI_USAGE.md](AI_USAGE.md).

## 6. Policy engine

Constants in `backend/app/config.py` (`POLICY_VERSION = policy-2026.1`):

| Rule | Result |
|------|--------|
| amount <= 75.00 USD | `ALLOW` |
| 75.00 < amount <= 100.00 USD | `REQUIRE_APPROVAL` |
| amount > 100.00 USD | `DENY` (`OVER_LIMIT`) |
| unknown product / unapproved seller / non-USD currency | `DENY` |
| client claims a different price or seller than the catalogue | `DENY` (`AMOUNT_MISMATCH`, `SELLER_MISMATCH`) |

## 7. Human approval

`POST /api/transactions/{id}/approve` takes the digest the approver reviewed. The backend recomputes the digest from
current trusted data; a mismatch is 409. An approval row stores the digest, policy version, `expires_at` (600 s by
default) and `used_at`. The digest covers intent id, agent id, manifest digest, product id and name, seller, amount,
currency, policy version and decision, so changing any of them invalidates the approval. Consuming an approval is an
atomic `UPDATE ... WHERE used_at IS NULL`; only one caller can win.

## 8. PayPal communication

All PayPal calls are made by `services/paypal.py` from the backend. Details, flows and idempotency are in
[PAYPAL_INTEGRATION.md](PAYPAL_INTEGRATION.md).

## 9. Data model (SQLite, SQLAlchemy)

```mermaid
erDiagram
    PRODUCT ||--o{ TRANSACTION_INTENT : "priced from"
    TRANSACTION_INTENT ||--o{ APPROVAL : has
    TRANSACTION_INTENT ||--o{ PAYMENT_ATTEMPT : has
    TRANSACTION_INTENT ||--o{ EVIDENCE_EVENT : has
    TRANSACTION_INTENT ||--o{ RECEIPT : has
    AGENT_MANIFEST ||--o{ TRANSACTION_INTENT : "authorises"
    APPROVED_SELLER ||--o{ PRODUCT : "allows"
```

| Table | Notes |
|-------|-------|
| `products`, `approved_sellers` | Seeded fixed catalogue (7 products, 3 approved sellers). Money in integer cents. |
| `agent_manifests` | Payload and signature in **separate columns** so tampering with either is detectable. |
| `transaction_intents` | Server-generated intent with `details_digest`, state, PayPal order/capture ids. |
| `approvals` | Digest, policy version, expiry, `used_at`. |
| `payment_attempts` | Operation, idempotency key, outcome, PayPal refs, timestamps. Unique `(intent_id, client_key)`. |
| `evidence_events` | Payload, signature, key id, digest. Unique `(intent_id, seq)`. |
| `receipts` | Payload, signature, key id, digest. Unique `(intent_id, receipt_type)`. |

Validity is never stored. Receipts, manifests and evidence are always re-verified from their content.

## 10. Transaction states

```mermaid
stateDiagram-v2
    [*] --> AWAITING_INTERNAL_APPROVAL: REQUIRE_APPROVAL
    [*] --> READY_FOR_PAYMENT: ALLOW
    AWAITING_INTERNAL_APPROVAL --> READY_FOR_PAYMENT: approved (exact digest)
    READY_FOR_PAYMENT --> ORDER_CREATING
    ORDER_CREATING --> ORDER_CREATED: PayPal order matches
    ORDER_CREATING --> READY_FOR_PAYMENT: create failed or outcome unknown (same request id on retry)
    ORDER_CREATING --> FAILED: order mismatch / approval replay
    ORDER_CREATED --> CAPTURING
    CAPTURING --> CAPTURED: PayPal reports COMPLETED capture
    CAPTURING --> CAPTURE_UNCERTAIN: timeout, 5xx, not confirmed
    CAPTURING --> ORDER_CREATED: buyer not approved yet
    CAPTURING --> FAILED: declined
    CAPTURE_UNCERTAIN --> CAPTURED: reconcile finds COMPLETED
    CAPTURE_UNCERTAIN --> ORDER_CREATED: reconcile finds no capture
    CAPTURE_UNCERTAIN --> FAILED: order voided
    CAPTURED --> [*]
```

Transitions are single-statement `UPDATE ... WHERE state IN (...)`; the caller that updates one row wins and the rest
get 409. `CAPTURE_UNCERTAIN` is exposed to clients as `recovery_status: PENDING_RECONCILIATION`.

## 11. Recovery behaviour

`POST /api/transactions/{id}/paypal/retry` (requires an `Idempotency-Key` header, 8-100 characters):

| Stored state | Action |
|--------------|--------|
| `CAPTURED` | Return the original result. Nothing is sent to PayPal. |
| `CAPTURING` / `ORDER_CREATING` | Refuse as a duplicate (409). |
| `CAPTURE_UNCERTAIN` | Reconcile with PayPal. Completed -> `CAPTURED`. No capture -> capture once with the same `PayPal-Request-Id`. Cannot ask / inconclusive -> HTTP 202 `PENDING_RECONCILIATION`. |
| `READY_FOR_PAYMENT` | Create the order again with the same `PayPal-Request-Id`; PayPal returns the original order. |
| `ORDER_CREATED` | Capture (idempotent). |

If the retry body names a different product, seller, amount or currency, it is rejected (409
`RETRY_DETAILS_MISMATCH`) and any unused approval is revoked. A repeated `Idempotency-Key` is a replay and is not
re-executed.

## 12. Receipt creation

A `PAYMENT_CONFIRMED` receipt is issued only when the intent is `CAPTURED`, has a PayPal capture id, and PayPal's
status was `COMPLETED`. Otherwise only a `DEV_TEST_NO_PAYMENT` receipt exists, labelled as claiming no payment.
The payload includes `evidence_reference` (chain head at issue time). The payload is canonicalised, signed with the
`receipt-signer` key and stored. Verification (`POST /api/receipts/verify`) recomputes the digest from the submitted
content, checks the signature against trusted keys, and runs consistency checks (for example a payment receipt that
lacks a capture id is invalid even if correctly signed).

## 13. Evidence-chain construction

Each lifecycle step appends one event for the intent. Fields: `schema` (`opp-evidence/1`), `event_id`, `intent_id`,
`seq`, `event_type`, `source` (`PAYPAL_OBSERVED` or `INTERNAL`), `recorded_at`, `prev_event_digest`, `refs`
(approval id, details digest, attempt id, idempotency key, PayPal order/capture ids, receipt id), `status_from`,
`status_to`, `paypal_observation`, `claim_basis`, `note`. The digest of an event is SHA-256 of its canonical JSON;
the next event stores it as `prev_event_digest`; the event is signed with the `evidence-signer` key.
`PAYPAL_OBSERVED` events carry what PayPal's API actually returned; `INTERNAL` events are the application's own
records and must not carry a PayPal observation (verification enforces both).

This is **TRACE-inspired**. It is not a conformant TRACE or SCITT implementation.

## 14. Cryptographic signing

- Canonical JSON: UTF-8, sorted keys, separators `(",", ":")`, no NaN, **floats rejected** (money is a string).
- Digest: SHA-256. Signature: Ed25519 (`cryptography`). Key id: `ed25519:` + first 16 hex characters of SHA-256 of the raw public key.
- Three keys generated on first start in `backend/data/keys/`: `manifest-issuer`, `receipt-signer`, `evidence-signer`.
- Development key handling only. Rotation: stop the backend, delete the `*.private.pem`, restart (new key id). Old signatures then no longer verify because the old key leaves the trust set; delete `backend/data/` in development to regenerate everything. A real deployment needs a KMS/HSM, a registry that keeps retired key ids for verifying history, and revocation.

## 15. Verification process

- Receipt: `POST /api/receipts/verify` with `{payload, signature_b64, key_id}`.
- Evidence: `POST /api/evidence/verify` with `{events: [...], expected_head_digest?}`. Per event: signature, required fields, schema, source/observation consistency, `seq` equals position, `prev_event_digest` equals the previous recomputed digest, no duplicate ids, same intent. With `expected_head_digest` (for example the receipt's `evidence_reference.head_digest`), removal of the pinned point is also detected.
- A standalone script, `backend/verify_receipt.py`, verifies a downloaded receipt with only the `cryptography` package.

A valid signature proves the content is unchanged since a trusted key signed it. It does not prove the claims are
true, the signer's real-world identity, or that goods were delivered.

## 16. Failure scenarios

| Failure | Behaviour |
|---------|-----------|
| PayPal credentials missing | 503 `PAYPAL_NOT_CONFIGURED`; nothing attempted |
| PayPal declines capture | `FAILED`, no receipt |
| Timeout / 5xx on capture | `CAPTURE_UNCERTAIN`; blind capture refused; reconcile or retry resolves it |
| Response lost after PayPal captured | Same as above; reconcile finds `COMPLETED`; one capture, one receipt |
| PayPal unreachable during reconcile | Stays uncertain; 202 `PENDING_RECONCILIATION` from the retry endpoint |
| Price/seller changed after approval | `DETAILS_CHANGED`; approval invalid; no order |
| Approval expired or already used | `APPROVAL_EXPIRED` / `APPROVAL_REPLAYED` |
| Two requests race | One wins an atomic state claim; the other gets 409 |
| Manifest edited | Signature fails; every purchase blocked (`MANIFEST_INVALID`) |

## 17. Sequence diagrams

### 17.1 Normal purchase (ALLOW)

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant BE as Backend
    participant AI as AI / fallback
    participant PP as PayPal Sandbox
    U->>FE: "I need a USB-C cable"
    FE->>BE: POST /api/purchase/propose
    BE->>BE: redact private data
    BE->>AI: redacted text only
    AI-->>BE: {product_id: usbc-cable}
    BE->>BE: validate against catalogue
    FE->>BE: POST /api/transactions (agent, product)
    BE->>BE: verify manifest, evaluate policy -> ALLOW (24.50)
    BE-->>FE: intent READY_FOR_PAYMENT
    FE->>BE: POST .../paypal/order
    BE->>PP: create order (PayPal-Request-Id)
    PP-->>BE: order + approval link
    U->>PP: buyer approves on paypal.com
    FE->>BE: POST .../paypal/capture
    BE->>PP: get order, then capture
    PP-->>BE: COMPLETED capture
    BE->>BE: CAPTURED, signed receipt, evidence event
    BE-->>FE: CAPTURED + receipt
```

### 17.2 Purchase that needs human approval

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant BE as Backend
    participant H as Human approver
    FE->>BE: POST /api/transactions (keyboard)
    BE->>BE: policy -> REQUIRE_APPROVAL (89.00)
    BE-->>FE: AWAITING_INTERNAL_APPROVAL + details_digest
    FE->>H: show exact product, seller, amount
    H->>FE: confirm
    FE->>BE: POST .../approve {details_digest}
    BE->>BE: recompute digest from trusted data, compare
    alt digest matches
        BE-->>FE: READY_FOR_PAYMENT (approval expires, one use)
    else digest differs
        BE-->>FE: 409 DIGEST_MISMATCH
    end
    FE->>BE: POST .../paypal/order
    BE->>BE: assert_payable: approval exists, matches, unexpired, unused
```

### 17.3 Denied purchase

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant BE as Backend
    FE->>BE: POST /api/transactions (headphones, 129.00)
    BE->>BE: manifest ok, policy: amount > 100.00
    BE-->>FE: 403 POLICY_DENIED (OVER_LIMIT). No intent is created.
    Note over FE,BE: A claimed price of 1.00 changes nothing: the catalogue price is used
```

### 17.4 Successful PayPal capture

```mermaid
sequenceDiagram
    participant BE as Backend
    participant DB as Database
    participant PP as PayPal
    BE->>BE: assert_payable (manifest, policy, digest, approval)
    BE->>DB: state ORDER_CREATED -> CAPTURING (atomic)
    BE->>DB: attempt(capture, key opp-capture-<id>) + evidence CAPTURE_STARTED
    BE->>PP: GET order
    PP-->>BE: status APPROVED, amount/reference match
    BE->>DB: evidence ORDER_STATUS_OBSERVED (PAYPAL_OBSERVED)
    BE->>PP: POST capture (PayPal-Request-Id)
    PP-->>BE: COMPLETED capture + capture id
    BE->>DB: CAPTURING -> CAPTURED, evidence CAPTURE_CONFIRMED
    BE->>DB: signed PAYMENT_CONFIRMED receipt (+ evidence_reference)
```

### 17.5 Lost PayPal response and recovery

```mermaid
sequenceDiagram
    participant AG as Agent
    participant BE as Backend
    participant PP as PayPal
    AG->>BE: POST capture
    BE->>PP: capture
    PP->>PP: captures the payment
    PP--xBE: response lost (timeout)
    BE->>BE: CAPTURING -> CAPTURE_UNCERTAIN (PENDING_RECONCILIATION), no receipt
    BE-->>AG: 504 CAPTURE_UNCERTAIN
    AG->>BE: POST retry (Idempotency-Key)
    BE->>PP: GET order (reconcile first, never capture first)
    PP-->>BE: COMPLETED capture
    BE->>BE: CAPTURED, one receipt, evidence RECONCILED
    BE-->>AG: 200 outcome RECONCILED (no second capture was sent)
    AG->>BE: POST retry (same key)
    BE-->>AG: 200 REUSED, replay=true
    Note over BE,PP: If PayPal cannot be reached: 202 PENDING_RECONCILIATION, state unchanged
```

### 17.6 Evidence verification

```mermaid
sequenceDiagram
    participant J as Judge / verifier
    participant BE as Backend
    J->>BE: GET /api/transactions/{id}/evidence
    BE-->>J: events [{payload, signature, key_id}]
    J->>BE: POST /api/evidence/verify {events, expected_head_digest?}
    loop each event, in order
        BE->>BE: recompute SHA-256 of payload
        BE->>BE: verify Ed25519 signature with trusted key
        BE->>BE: check seq, prev_event_digest, source/observation rules
    end
    BE-->>J: valid + per-event results
```

### 17.7 Tamper detection

```mermaid
sequenceDiagram
    participant X as Attacker
    participant J as Verifier
    participant BE as Backend
    X->>X: edit status_to, relabel a source, delete or reorder an event
    X->>BE: POST /api/evidence/verify {edited events}
    BE->>BE: recompute digest -> signature no longer matches
    BE->>BE: seq / prev_event_digest chain broken
    BE-->>X: valid=false with the reasons
    Note over X,BE: The same applies to receipts: changing amount 89.00 to 0.01 makes the receipt INVALID
```

## 18. Attack Lab design

Each run builds a disposable app (temporary SQLite, throwaway keys, in-memory fake PayPal), drives it over its HTTP
API, then deletes it. Fixtures that an attack alters (manifest payload, prices, approval expiry) are restored inside
that sandbox; the real database, keys and PayPal account are never touched. PASS or FAIL is computed from observed
responses. Tests deliberately break a defense and assert that the lab reports FAIL.
