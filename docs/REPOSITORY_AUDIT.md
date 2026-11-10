# Repository audit

Audit of the OutProvenance Pay repository, performed against the source code, configuration, tests and running
application (not against the README). Every claim below was checked in code or by running something; where a
claim could not be checked, it says so. No secret values appear in this document.

- Audited on: 2026-11-10
- Method: read every backend service/API file, the frontend pages and API client, the tests, the environment
  examples, `.gitignore`, `LICENSE` and the existing docs; ran the test suite, type-check, lint, build and a
  live smoke run (see [VERIFICATION_REPORT.md](VERIFICATION_REPORT.md)).
- Repository state: a local git repository with **no commits yet**. Everything is untracked. Publishing the
  repository (public GitHub) has not happened.

## 1. Features confirmed in code

| Feature | Where in the code | Confirmed how |
|---------|-------------------|---------------|
| Privacy redaction (email, phone, card-like numbers) before any AI call | `backend/app/services/privacy.py`, `api/purchase.py` | code read, `test_privacy_ai.py`, live smoke (email redacted) |
| Advisory AI: OpenAI-compatible chat endpoint **or** a local keyword matcher | `backend/app/services/ai.py` | code read, tests with a mock transport. No live AI provider was called. |
| Strict AI output schema (`extra=forbid`, product id must exist in the catalogue) | `ai.py` (`AiProposal`) | code read, tests |
| Signed agent manifest (Ed25519 over canonical JSON), verified before every intent | `services/manifest.py`, `services/transactions.py` | code read, `test_manifest.py`, Attack Lab scenario 3 |
| Deterministic policy engine: ALLOW <= 75.00, REQUIRE_APPROVAL <= 100.00, DENY above; unknown product, unapproved seller, wrong currency | `services/policy.py`, `config.py` | code read, 21 tests in `test_policy.py` |
| Trusted catalogue is the only source of price and seller | `services/catalogue.py` | code read; client "claims" can only cause DENY |
| Human approval bound to a digest of intent id, agent, manifest digest, product, seller, amount, currency, policy version and decision | `services/transactions.py` (`details_dict`, `approve`, `assert_payable`) | code read, tests, live smoke (wrong digest -> 409) |
| Approval expires (600 s default) and is single-use (atomic `UPDATE ... WHERE used_at IS NULL`) | `config.py`, `transactions.py` (`consume_approval`) | code read, `test_expired_approval_rejected`, `test_approval_is_one_time_use` |
| PayPal Orders v2 client, server-side only (OAuth, create order, get order, capture) | `services/paypal.py`, `services/payments.py`, `api/payments.py` | code read, 18 mocked tests. **Live Sandbox not exercised.** |
| `PayPal-Request-Id` idempotency key on create and capture (`opp-order-<intent>`, `opp-capture-<intent>`) | `payments.py`, `paypal.py` | code read; mock honours same-key semantics. Real PayPal behaviour not verified live. |
| Payment state machine with atomic compare-and-set transitions | `services/transactions.py` (`ALLOWED_TRANSITIONS`, `transition`) | code read, concurrency Attack Lab scenario |
| `CAPTURE_UNCERTAIN` + reconcile against PayPal; no blind capture retry | `payments.py` (`capture`, `reconcile`) | code read, tests, Attack Lab 8 |
| Agent retry endpoint with `Idempotency-Key`, reconcile-first, altered-details rejection | `services/recovery.py`, `api/recovery.py` | code read, `test_recovery.py`, Attack Lab 9-14 |
| Persisted execution attempts (idempotency key, order/capture refs, outcome, timestamps) | `models.py` (`PaymentAttempt`), `services/attempts.py` | code read, tests, `GET /attempts` |
| Signed, hash-linked evidence events marked `PAYPAL_OBSERVED` or `INTERNAL` | `services/evidence.py`, `models.py` (`EvidenceEvent`) | code read, tests, live smoke (chain valid) |
| Independent evidence verification from submitted payloads only | `evidence.verify_chain`, `POST /api/evidence/verify` | code read, 8 tamper cases in tests |
| Signed receipts (`PAYMENT_CONFIRMED` only after PayPal reports a COMPLETED capture; `DEV_TEST_NO_PAYMENT` otherwise) | `services/receipts.py` | code read, 20 tests, live smoke (tamper -> invalid) |
| Receipt carries `evidence_reference` (chain head at issue time) | `receipts._base_payload` | code read, test |
| One receipt per intent and type, enforced by a database unique index | `main.py` (index), `receipts._store` | found by the concurrency scenario, fixed, tested |
| Attack Lab: 14 scenarios against the real backend in a disposable sandbox with a mocked PayPal where needed | `services/attack_lab.py`, `api/attack_lab.py` | ran all 14: 14/14 PASS in the UI and in tests |
| Rogue Agent page (left side is a **client-side simulation** of an unprotected agent; right side is real backend calls) | `frontend/src/pages/RogueAgent.tsx` | code read, ran in browser |
| Receipt QR code that opens the verifier | `frontend/src/pages/ReceiptVerification.tsx` | code read, ran in browser |
| CORS allow-list (GET/POST, `Content-Type`, `Idempotency-Key`) | `main.py`, `config.py` | live check: allowed origin accepted, `evil.example` gets no header |
| Secrets kept out of git and the browser bundle | `.gitignore`, `frontend` build | scanned `dist/`: only a variable *name* in help text, no value |

## 2. Partially implemented

| Area | State |
|------|-------|
| PayPal live Sandbox checkout | Code path exists and passes mocked tests. Never run with real Sandbox credentials in this audit. |
| AI via external provider | Implemented against the OpenAI-compatible `/chat/completions` shape. Never called live. No model name is fixed in the repository (configured by `AI_MODEL`). Without configuration, a labelled keyword matcher is used and that is what was exercised. |
| Concurrency safety | Verified in one process on SQLite (threads). Not tested across processes or on another database. |
| Evidence integrity | Detects edits, removal and reordering of events *inside a submitted chain*. Deleting the **tail** of a chain is only detectable if a pinned head digest (for example from a receipt) is supplied. |
| "TRACE" evidence | TRACE-**inspired** (signed, hash-linked, source-labelled events). It does not implement a published TRACE or SCITT schema or protocol and does not claim to. |
| Rogue Agent comparison | The unprotected side is a labelled simulation in the browser, not a second real agent. |

## 3. Missing features

- **User authentication and authorisation.** No login. Anyone who can reach the API can approve, capture or retry. The "approver name" is a free-text label.
- **PayPal webhooks.** Not implemented. Payment status comes only from synchronous server API calls (create, get, capture) and reconciliation.
- **Hosted demo.** None. The project runs locally.
- **Frontend automated tests.** Only type-check, lint and build are configured.
- **Key management beyond local files** (KMS/HSM, rotation automation, revocation list).
- **Rate limiting** on any endpoint (only the Attack Lab got a one-at-a-time guard during this audit).
- **A transparency log or third-party witness** for evidence.

## 4. Run blockers

None in the repository. Environment notes:

- The frontend needs **Node >= 18.18** (`frontend/package.json` `engines`). The audit machine's default Node was 12, which cannot run Vite 5; a portable Node 20.18 was used instead. This is documented in the README prerequisites.
- Python 3.11+ is required. The audit used Python 3.13.0.
- Without PayPal credentials the app still starts; checkout shows "setup required" and returns HTTP 503 `PAYPAL_NOT_CONFIGURED`.

## 5. Incorrect documentation found (and fixed)

| Problem | Fix |
|---------|-----|
| README reported 112 passing tests and 8 Attack Lab scenarios | Now 141 tests and 14 scenarios, matched to a real run |
| README said no visual check had been done | Replaced with an accurate description (headless browser click-through) |
| `docs/architecture.md` and `docs/threat-model.md` did not cover payment recovery, evidence, or Rogue Agent | Rewritten as `ARCHITECTURE.md` and `THREAT_MODEL.md` |
| Docs said keys were `manifest-issuer` and `receipt-signer` only | A third key, `evidence-signer`, now exists and is documented |
| Docs had no PayPal/AI/judging/limitations pages | Added (see README "Documentation") |

## 6. Broken links

A link check over every Markdown file was run after the documentation rewrite; its result is recorded in
[VERIFICATION_REPORT.md](VERIFICATION_REPORT.md) section 6.

## 7. Insecure defaults and risks

| Item | Status |
|------|--------|
| No authentication | Open. Documented in the README, `SECURITY.md`, `THREAT_MODEL.md` and `KNOWN_LIMITATIONS.md`. |
| `PAYPAL_BASE_URL` could be set to PayPal's **live** API | **Fixed:** the backend now refuses to start if the host is `api-m.paypal.com` or `api.paypal.com` (test: `test_refuses_to_start_against_live_paypal`). |
| Attack Lab endpoints are unauthenticated and each run builds a whole app | **Mitigated:** one run at a time, otherwise HTTP 429 `ATTACK_LAB_BUSY` (test: `test_attack_lab_refuses_overlapping_runs`). Still no general rate limiting. |
| Private keys are plain `*.pem` files in `backend/data/keys/` (mode 0600 where the OS supports it) | Open, development-grade. Git-ignored. |
| `POST /api/transactions/{id}/dev-receipt` is open | By design for demos. The receipt type is `DEV_TEST_NO_PAYMENT`, claims no payment, and verification flags it. |
| Duplicate receipts under concurrent capture | **Fixed:** found by the new concurrency scenario (two receipts for one capture). Unique index plus idempotent issue. |
| SQLite, single process | Open. Fine for a prototype. |
| `requirements.txt` has lower bounds only and no lock file | Open. The tested versions are listed in the verification report. |
| `pytest` is listed in the runtime `requirements.txt` | Cosmetic. Left so `pip install -r requirements.txt` also lets judges run the tests. |

## 8. Hardcoded secrets

None found. A search of `backend/app` and `frontend/src` for secret-looking assignments found only the
placeholders `mock-id` and `mock-secret`, used for the in-memory fake PayPal in `services/attack_lab.py` and in
tests. `.env` files, `backend/data/`, `*.pem`, `*.db` and `*.log` are git-ignored. `backend/.env.example` and
`frontend/.env.example` contain empty values only.

## 9. Environment variables

All are read in `backend/app/config.py`; none are missing from `backend/.env.example`:

`OPP_DATA_DIR`, `OPP_CORS_ORIGINS`, `OPP_FRONTEND_URL`, `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`,
`PAYPAL_BASE_URL`, `AI_API_KEY`, `AI_BASE_URL`, `AI_MODEL`. The frontend reads only `VITE_API_BASE_URL`.

## 10. Failing tests

None. 141 passed in the final run. Three consecutive full runs of 134 tests were green after the receipt race was fixed, then two tests were added (live-PayPal-host refusal, Attack Lab overlap guard) and the suite was run again.
One run before that fix failed on `receipts=2`, which was a real bug and was fixed rather than the test being
changed.

## 11. Dependency and version notes

- `pip check`: no broken requirements.
- `npm audit --omit=dev`: 0 vulnerabilities.
- One test warning: Starlette deprecates using `httpx` with its `TestClient` (`StarletteDeprecationWarning`). Cosmetic; tests pass.
- Backend dependencies are not pinned to exact versions.

## 12. Hackathon requirement gaps (as of this audit)

| Requirement | Gap |
|-------------|-----|
| Public open-source repository | Not yet published. The repository has no commits. |
| Visible license file | Present (`LICENSE`, MIT). |
| Public YouTube video under 3 minutes | Not yet recorded or uploaded. |
| Hosted demo or run instructions | Run instructions exist. No hosted demo. |
| Meaningful PayPal use | Implemented, but a live Sandbox payment has not been demonstrated. |
| Meaningful AI use | Implemented, but only the keyword fallback has actually run. Using a real model needs the three `AI_*` variables. |
| Tools used and how | Documented in `AI_USAGE.md`; the author must confirm the list. |
| No unlicensed assets | No music, images or fonts from third parties are in the repository. The screenshots in `docs/images/` are captures of this app. |
