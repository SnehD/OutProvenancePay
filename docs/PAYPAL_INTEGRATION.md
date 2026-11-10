# PayPal integration

PayPal is the system of record for money in OutProvenance Pay. The backend uses PayPal's **Orders v2 REST API**
(Sandbox) to create and capture every payment, and treats PayPal's server response as the only proof that money moved.
The rest of the project (policy, approval, recovery, receipts, evidence) exists to wrap that call safely.

## What is used

| Item | Value |
|------|-------|
| PayPal product | Checkout Orders **v2** REST API (`/v2/checkout/orders`) and OAuth 2.0 client credentials (`/v1/oauth2/token`) |
| Environment | **Sandbox** only (`https://api-m.sandbox.paypal.com`). The backend refuses to start if `PAYPAL_BASE_URL` is PayPal's live host. |
| Where | `backend/app/services/paypal.py` (HTTP client), `services/payments.py` (orchestration), `api/payments.py` and `api/recovery.py` (routes) |
| Intent | `CAPTURE`; `payment_source.paypal.experience_context` with `user_action: PAY_NOW`, `shipping_preference: NO_SHIPPING` |
| Webhooks | **Not implemented.** Status is read synchronously (`GET order`) and by reconciliation. |
| PayPal JS SDK / client-side buttons | **Not used.** The buyer is sent to the approval link returned by the server. |

## Configuration

| Variable | Purpose |
|----------|---------|
| `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` | Sandbox REST app credentials. **Server only.** Empty means "setup required" (HTTP 503). |
| `PAYPAL_BASE_URL` | Default `https://api-m.sandbox.paypal.com` |
| `OPP_FRONTEND_URL` | Where PayPal returns the buyer (`?paypal=return&intent=...`) |

Get credentials: <https://developer.paypal.com> -> Apps & Credentials -> **Sandbox** -> Create App (Merchant). Use a
Sandbox **Personal** account as the buyer (Testing tools -> Sandbox accounts). Put the keys in `backend/.env`
(git-ignored) and restart. Never put them in a `VITE_` variable or commit them.

## Flow

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant BE as Backend
    participant PP as PayPal Sandbox
    participant BU as Buyer (paypal.com)
    FE->>BE: POST /api/transactions/{id}/paypal/order
    BE->>BE: assert_payable (manifest, policy, digest, approval)
    BE->>PP: POST /v2/checkout/orders  (PayPal-Request-Id: opp-order-<id>)
    PP-->>BE: order id + payer-action link
    BE->>BE: order must match intent id, amount, currency; consume approval
    BE-->>FE: ORDER_CREATED + approval_url
    FE->>BU: open approval_url
    BU->>PP: buyer logs in and approves
    FE->>BE: POST /api/transactions/{id}/paypal/capture
    BE->>PP: GET /v2/checkout/orders/{order}
    PP-->>BE: status APPROVED
    BE->>PP: POST .../capture  (PayPal-Request-Id: opp-capture-<id>)
    PP-->>BE: COMPLETED capture
    BE->>BE: CAPTURED + signed receipt + evidence
```

1. **Create order** (`POST /api/transactions/{id}/paypal/order`): the amount, currency and description come from the stored intent. The client sends **no amounts**. The returned order must carry the intent id as `reference_id` and the same amount and currency, otherwise the intent fails (`ORDER_MISMATCH`).
2. **Buyer approval** happens on paypal.com with a Sandbox buyer account. It is separate from our internal human approval.
3. **Capture** (`POST .../paypal/capture`): the backend re-validates everything, fetches the order from PayPal, requires `APPROVED` and a matching amount/reference, then captures. Only a response with order `COMPLETED` **and** capture `COMPLETED` sets `CAPTURED`.
4. **Status** (`GET .../paypal/status`) refreshes the PayPal order status from the server API. **Reconcile** (`POST .../paypal/reconcile`) is for `CAPTURE_UNCERTAIN`.
5. **Agent retry** (`POST .../paypal/retry`, `Idempotency-Key` header) is the recovery entry point described below.

## Transaction state handling

`AWAITING_INTERNAL_APPROVAL -> READY_FOR_PAYMENT -> ORDER_CREATING -> ORDER_CREATED -> CAPTURING -> CAPTURED`, with
`CAPTURE_UNCERTAIN` and `FAILED` branches. A browser redirect to `?paypal=return` only opens the checkout page;
status always comes from the backend asking PayPal. Full diagram: [ARCHITECTURE.md](ARCHITECTURE.md#10-transaction-states).

## Idempotency and duplicate prevention

Layers, from PayPal's side to ours:

| Layer | Mechanism |
|-------|-----------|
| PayPal request header | `PayPal-Request-Id: opp-order-<intent id>` on create and `opp-capture-<intent id>` on capture. The same key on a retry asks PayPal to return the original result instead of repeating the operation. |
| State machine | Atomic `UPDATE ... WHERE state IN (...)`; only one request can claim `ORDER_CREATING` or `CAPTURING`. |
| Already done | An intent in `ORDER_CREATED` returns the existing order; an intent in `CAPTURED` returns the existing result. |
| Approval | One-time, atomic consumption. |
| Receipts | A unique index allows one receipt per intent and type. |
| Agent retry | Unique `(intent_id, client_key)` on `payment_attempts` recognises a repeated `Idempotency-Key`. |

**Honest note:** the `PayPal-Request-Id` layer relies on PayPal honouring its documented idempotency behaviour. The
in-memory fake models "same key returns the same result"; this was **not** verified against the live Sandbox. That is
why the backend does not rely on it alone: it reconciles with PayPal's order state before any retry.

## Recovery after an uncertain response

A timeout, network error, 5xx, or a response that does not show a completed capture is **unknown**, not failure and not
success:

1. State becomes `CAPTURE_UNCERTAIN` (exposed as `recovery_status: PENDING_RECONCILIATION`); no receipt is issued.
2. Plain `capture` is refused (409) until reconciled.
3. `reconcile` and `retry` first `GET` the order. A `COMPLETED` capture -> `CAPTURED` (no second capture). `APPROVED` with no capture -> back to `ORDER_CREATED`, then one capture with the **same** request id. `VOIDED` -> `FAILED`. Anything else, or PayPal unreachable -> stays uncertain (HTTP 202 from the retry endpoint).
4. Every attempt and observation is stored (`payment_attempts`) and signed (`evidence_events`), marked `PAYPAL_OBSERVED` or `INTERNAL`.

Order creation is handled the same way: a lost create response reverts to `READY_FOR_PAYMENT` and the retry re-sends the
same `PayPal-Request-Id`, so PayPal hands back the original order.

## The fake PayPal used in tests

`backend/app/services/mock_paypal.py` is an in-memory `httpx.MockTransport` handler. It supports `ok`, `timeout`,
`declined`, `server_error`, `already_captured`, `pending`, and two failure-injection modes: `lost_response` (the
capture or order **is** executed, then the reply is dropped) and `order_lookup_fails` (reads time out). It also
honours same-key idempotency for orders and captures. Everything that uses it is labelled **MOCKED** in the UI and
documents: no network, no credentials, no real money, and passing these tests shows our handling of PayPal's
documented HTTP behaviour, **not** that live Sandbox works. The Attack Lab never calls PayPal.

## Sandbox versus real payments

Sandbox money is fake and the buyer is a test account. This prototype is **not** configured, tested or permitted for
real payments, and the backend will not start against PayPal's live host. Moving to production would need, at least:
authentication and authorisation, webhook handling, real key management, live-account review, and a security audit.

## Test it

```powershell
# check your Sandbox credentials without moving money (from backend/, venv active)
python check_paypal.py            # OAuth token only
python check_paypal.py --order    # also creates one 1.00 USD test order (never captured)

# mocked PayPal tests (no credentials needed), from backend/ with the venv active
python -m pytest -q tests/test_paypal_mocked.py tests/test_recovery.py
```

Live Sandbox (needs your credentials): follow [DEMO_GUIDE.md](DEMO_GUIDE.md) section "Real PayPal Sandbox payment".

## Limitations

- Live Sandbox checkout, PayPal's actual idempotency behaviour and real error codes were **not exercised** here.
- No webhooks; no refunds, disputes, partial captures or multi-currency (USD only).
- One merchant account (the app's), no marketplace or multi-party flows.
- Capture status `PENDING` is treated as "not confirmed" and goes to reconciliation.
