# Verification report

What was actually run, with the commands and results. Nothing here is estimated. Where something could not be run,
the reason and the manual steps are given. See [REPOSITORY_AUDIT.md](REPOSITORY_AUDIT.md) for the code audit.

- Date: 2026-11-10
- OS: Windows 11 Pro (PowerShell and Git Bash)
- Python 3.13.0, Node v20.18.0 (portable; the machine's default Node is v12.16.3, which cannot run Vite 5), Microsoft Edge (headless) for UI checks
- Backend versions installed during the run: FastAPI 0.162.0, Starlette 1.10.0, Uvicorn 0.54.0, Pydantic 2.14.1, SQLAlchemy 2.1.6, cryptography 50.0.2, httpx 0.28.1, pytest 9.2.0
- Frontend: React 18.3.1, TypeScript ~5.6.3, Vite ^5.4.9, `qrcode` ^1.5.4

## 1. Commands and results

| # | Command (working directory) | Result |
|---|------------------------------|--------|
| 1 | `.\.venv\Scripts\python.exe -m pip check` (`backend/`) | `No broken requirements found.` |
| 2 | `.\.venv\Scripts\python.exe -m pytest -q` (`backend/`) | **`141 passed, 1 warning in 86.89s`**. Warning: `StarletteDeprecationWarning` about `httpx` with `TestClient` (cosmetic). |
| 3 | `npm run typecheck` (`frontend/`) | passes (`tsc --noEmit`, no output) |
| 4 | `npm run lint` (`frontend/`) | passes (`eslint src`, no output) |
| 5 | `npm run build` (`frontend/`) | `built in 2.29s`; `dist/assets/index-*.js` 215.16 kB (gzip 70.51 kB) |
| 6 | `npm audit --omit=dev` (`frontend/`) | `found 0 vulnerabilities` |
| 7 | Scan of `frontend/dist` for `PAYPAL_CLIENT_SECRET`, `client_secret`, `AI_API_KEY` | 1 file matched: the **text** "Add PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET to backend/.env" in a help message. No secret values. |
| 8 | Search of `frontend/src` for `paypal.com`, `paypal.js`, `sdk/js`, `client-id`, `clientId` | no matches: no PayPal SDK, client id or secret in the browser |
| 9 | `uvicorn app.main:create_app --factory --port 8001` with `OPP_DATA_DIR` set to a temporary folder, then the requests in section 2 | backend started and answered; see below |
| 10 | `npm run dev` / Vite on port 5173 | HTTP 200; the UI loaded data from the backend with no console errors |
| 11 | Headless Edge click-through of Overview, Rogue Agent, the purchase and approval flow, Recovery & Evidence, Receipt Verification and Attack Lab (Run all) | no console errors; Attack Lab showed "14/14 defenses held"; screenshots in `docs/images/` |
| 12 | `python check_paypal.py` (`backend/`, empty `.env`) | `NOT CONFIGURED ...`, exit code 2, no request sent to PayPal (5 tests cover the not-configured, live-host-refused, bad-credentials, good-credentials and `--order` paths against the fake) |
| 13 | Link check over `README.md`, `SECURITY.md`, `docs/*.md` (relative links, anchors, image files) | see section 6 |

Test counts by file (sum 141): `test_api_core` 8, `test_check_paypal` 5, `test_attack_lab` 18, `test_manifest` 7, `test_paypal_mocked` 18,
`test_policy` 21, `test_privacy_ai` 12, `test_receipts` 20, `test_recovery` 16, `test_transactions` 16.

**Issues found by running things, and what was done:**

1. The new concurrency scenario produced **two receipts for one capture** in one of two full runs (`receipts=2`). Root cause: two requests both passed the "no receipt yet" check. Fixed with a database unique index and idempotent issuing. The test was not weakened; three consecutive full runs afterwards were green.
2. The Attack Lab check "approval for different details is refused" initially passed for the wrong reason (the intent was already approved). The scenario now uses an intent still awaiting approval and asserts `DIGEST_MISMATCH`.
3. Two safe hardening fixes were added with tests: refusal to start against PayPal's live host, and one-at-a-time Attack Lab runs.

## 2. Live smoke run (isolated backend, no PayPal or AI credentials)

```
GET  /api/health                         -> status ok, paypal "not configured - setup required", ai "local deterministic fallback"
POST /api/purchase/propose (email in text)
     -> redacted "...email me at [REDACTED_EMAIL]", ai source local-fallback, suggestion keyboard, policy REQUIRE_APPROVAL
POST /api/transactions headphones (129.00)  -> 403 POLICY_DENIED "Amount 129.00 exceeds the 100.00 maximum purchase limit."
POST /api/transactions keyboard (89.00)     -> AWAITING_INTERNAL_APPROVAL, REQUIRE_APPROVAL
POST .../approve with a WRONG digest        -> 409 DIGEST_MISMATCH
POST .../approve with the correct digest    -> READY_FOR_PAYMENT
POST .../paypal/order (no credentials)      -> 503 PAYPAL_NOT_CONFIGURED "No payment was attempted."
POST .../paypal/retry without a key         -> 428 IDEMPOTENCY_KEY_REQUIRED
POST .../dev-receipt, verify, then amount changed to 0.01
     -> untouched receipt valid: True ; tampered receipt valid: False
GET  .../evidence then POST /api/evidence/verify
     -> events INTENT_CREATED, APPROVAL_GRANTED, RECEIPT_ISSUED (all INTERNAL) ; chain valid: True
CORS: Origin http://localhost:5173 -> allowed ; Origin http://evil.example -> no CORS header
GET  /api/attack-lab/scenarios              -> 14 scenarios, 9 use mocked PayPal
```

Note: with no credentials the order endpoint answers 503 before it reaches the approval check, so "an order is
blocked without approval" is proven by `test_order_blocked_without_internal_approval` (mocked credentials) rather than
by this live run.

## 3. The 16 verification items

Status key: **Live** = observed against the running app; **Mocked** = proven by automated tests against the in-memory
PayPal; **Code** = confirmed by reading the code; **Not verified** = could not be checked here.

| # | Item | Status | Evidence |
|---|------|--------|----------|
| 1 | Install or validate dependencies | Live | `pip check` clean; `npm audit` 0 vulnerabilities; portable Node 20 used |
| 2 | Run backend tests | Live | 141 passed |
| 3 | Frontend tests or build checks | Live | typecheck, lint, build pass. **No frontend unit tests exist.** |
| 4 | Backend can start | Live | uvicorn on port 8001 and 8000, `/api/health` ok |
| 5 | Frontend can start or build | Live | Vite dev server 200; production build passes |
| 6 | Frontend points to the correct backend | Live + Code | `frontend/src/services/api.ts` uses `VITE_API_BASE_URL`, default `http://localhost:8000`; UI loaded data; CORS allow-list verified |
| 7 | PayPal integration is server-side | Code | all PayPal calls in `backend/app/services/paypal.py`; frontend contains no PayPal SDK, client id or secret (command 8). The buyer is sent to the approval link returned by the server. |
| 8 | Create-order and capture use real backend routes | Code + Mocked | `POST /api/transactions/{id}/paypal/order`, `/capture`, `/retry`, `/reconcile`, `GET .../status`; 18 tests in `test_paypal_mocked.py`. **Live Sandbox not verified.** |
| 9 | Handling of lost, delayed, duplicate, unknown responses | Mocked | `test_capture_timeout_is_uncertain_and_never_blindly_retried`, `test_server_error_on_capture_is_uncertain`, `test_reconcile_*`, `test_duplicate_capture_does_not_capture_twice`, `test_retry_reconciles_and_never_captures_twice`, `test_unresolved_outcome_stays_pending_and_is_not_reported_as_success_or_error`, `test_lost_order_creation_response_reuses_original_order`; Attack Lab 7-11 |
| 10 | Idempotency or duplicate prevention is real | Code + Mocked | `PayPal-Request-Id` headers (`opp-order-<id>`, `opp-capture-<id>`) in `payments.py`/`paypal.py`; atomic `UPDATE ... WHERE state IN (...)` claims; unique `(intent_id, client_key)`, `(intent_id, seq)`, `(intent_id, receipt_type)`; Attack Lab 14 (24 racing requests -> 1 order, 1 capture, 1 receipt). **PayPal's own idempotency behaviour not verified live.** |
| 11 | Approval tied to exact product, seller, amount, currency, transaction | Code + Live | `transactions.details_dict` includes intent id, agent id, manifest digest, product id and name, seller, amount, currency, policy version, decision; wrong digest -> 409 (live); `test_price_change_after_approval_invalidates`, `test_seller_change_after_approval_invalidates`, `test_approval_cannot_be_reused_for_another_intent` |
| 12 | Approvals expire and are one-time | Code + Mocked | 600 s TTL in `config.py`; `test_expired_approval_rejected`, `test_approval_is_one_time_use`; Attack Lab 5 |
| 13 | Receipts and evidence are cryptographically signed | Code + Live | Ed25519 via `cryptography` in `services/crypto.py`; keys `manifest-issuer`, `receipt-signer`, `evidence-signer`; verified through the live API |
| 14 | Tampering is detected | Live + Mocked | receipt amount 0.01 -> `valid False` (live); evidence tampering: 6 cases in Attack Lab 12 and 8 cases in `test_tampered_evidence_fails_independent_verification` |
| 15 | Attack Lab: number and behaviour | Live | **14 scenarios** (9 with mocked PayPal, 5 without); UI "14/14 defenses held"; each scenario computes PASS from observed checks; two tests break a defense on purpose and require FAIL |
| 16 | Actual number of passing tests | Live | **141** |

## 4. Not run, and how to verify manually

| What | Why it could not run | Manual verification |
|------|----------------------|---------------------|
| Live PayPal Sandbox order, buyer approval and capture | No Sandbox credentials were available | [DEMO_GUIDE.md](DEMO_GUIDE.md) section 10. Expected: `CAPTURED` only after PayPal reports COMPLETED; a `PAYMENT_CONFIRMED` receipt; `PAYPAL_OBSERVED` evidence events with PayPal order and capture ids |
| PayPal's real idempotency behaviour (same `PayPal-Request-Id` twice) | Needs the live Sandbox | After a live capture, call `POST .../paypal/retry` twice and confirm the PayPal dashboard shows exactly one capture |
| A real lost response against PayPal | Cannot be induced on demand | Covered by the mocked failure injection; the reconciliation path is the same code a real timeout would use |
| External AI model call | No `AI_API_KEY`, `AI_BASE_URL`, `AI_MODEL` configured | Set all three in `backend/.env`, restart, run Purchase Request -> Find product; the response `source` should read `external-llm` |
| Multi-process or non-SQLite concurrency | Out of scope for the environment | Run the backend with several workers against a shared database and repeat Attack Lab scenario 14's request pattern |
| Hosted deployment, public GitHub repository, YouTube upload | Not done; the repository has no commits | See the submission checklist in [JUDGING_ALIGNMENT.md](JUDGING_ALIGNMENT.md) |
| Default Node v12 install of the frontend | Not attempted; Vite 5 requires Node 18+ | Use Node 18.18+ |

## 5. Reproduce

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q          # 141 passed
cd ..\frontend
npm run typecheck; npm run lint; npm run build
```

Counts and timings can change with dependency versions; rerun rather than trusting this page.

## 6. Link check

All relative links, section anchors and image files in `README.md`, `SECURITY.md` and `docs/*.md` were checked with a
script after the documentation rewrite. **70 relative links checked; 0 broken** (the script is a few lines of
Python that resolves each link against the file system and each `#anchor` against the target's headings).
External `https://` links were not fetched.
