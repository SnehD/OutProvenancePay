# Demo guide (about five minutes)

Follow this to see every feature work. Sections 1-9 need **no PayPal credentials and no AI key**. Section 10 is the
optional real PayPal Sandbox payment.

> Honest labels you will see: "Local deterministic keyword matcher (not an LLM)", "PayPal: setup required" (until you add Sandbox credentials), "MOCKED PayPal" on Attack Lab scenarios that need PayPal, and "development receipt, no payment". These are correct, not errors.

## Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.11 or newer |
| Node.js | **18.18 or newer** (20 LTS recommended) |

## Start (two terminals, PowerShell)

```powershell
# Terminal 1 - backend, from the repository root
cd backend
py -3.13 -m venv .venv                  # or -3.12 / -3.11
.\.venv\Scripts\Activate.ps1            # if blocked: Set-ExecutionPolicy -Scope Process Bypass
python -m pip install -r requirements.txt
uvicorn app.main:create_app --factory --port 8000
```

```powershell
# Terminal 2 - frontend, from the repository root
cd frontend
copy .env.example .env
npm install
npm run dev
```

| URL | What |
|-----|------|
| <http://localhost:5173> | The app |
| <http://localhost:8000/docs> | Interactive API docs |
| <http://localhost:8000/api/health> | Should say `"status":"ok"` |

Check: the left sidebar shows **PayPal: setup required** and **AI: local fallback**.

## 1. Confirm the app is running (about 10 s)

Open <http://localhost:5173>. The **Overview** page should show **Backend: ok**, **PayPal: Setup required** and **AI
assistant: Local fallback (not an LLM)**. The sidebar badges say the same. These are correct for a run with no
credentials.

## 2. Happy path (ALLOW, about 40 s)

1. **Purchase Request**: type `I need a USB-C cable` -> **Find product** -> **Use this product**.
2. **Policy Decision**: click **Evaluate policy**. Expected `ALLOW`, 24.50 USD from Northwind Electronics. Click **Create transaction intent**; the app moves to **PayPal Checkout**.
3. **PayPal Checkout**: expected state `READY_FOR_PAYMENT`. Without credentials, **Create PayPal Sandbox order** is disabled and a banner says setup is required. Click **Issue development receipt**.
4. **Receipt Verification** opens: **Verify receipt** -> expected `VALID`, receipt type `DEV_TEST_NO_PAYMENT`.

## 3. Human approval (about 40 s)

1. **Purchase Request**: `I need a mechanical keyboard, email me at jane@example.com` -> **Preview what leaves this server**: the email is shown as `[REDACTED_EMAIL]`.
2. Back -> **Find product** -> **Use this product** -> **Policy Decision** -> **Evaluate policy**: `REQUIRE_APPROVAL` (89.00 USD). Click **Create transaction intent**; the app moves to **Approval**.
3. **Approval**: **Approve transaction** is disabled until you enter a name and tick the box. Approve.
4. Expected: an "Approved" banner ("By <name>. Expires ..."), state `READY_FOR_PAYMENT`. The approval is bound to the digest shown; it works once and expires in 10 minutes.

## 4. Denied purchase (about 20 s)

**Product Catalogue** -> **Select & evaluate policy** on **Noise-Cancelling Headphones** (129.00) -> **Evaluate policy**:
expected `DENY` (`OVER_LIMIT`). Click **Create transaction intent**: "Transaction refused by the backend" (HTTP 403, no
intent is created). Also try **Bargain Gadget** (Gray Market
Gadgets): `DENY` (`UNAPPROVED_SELLER`).

## 5. Rogue Agent (about 40 s)

Sidebar -> **Rogue Agent** -> keep the first preset ("Ignore the limit") -> **Unleash the rogue agent**.

Expected: left, *Without protection* (**SIMULATED**): "Bought: Noise-Cancelling Headphones, 129.00". Right, *With
OutProvenance Pay* (**REAL BACKEND**): "Blocked ... DENY OVER_LIMIT". Click **Shady seller + data leak** and run again:
`UNAPPROVED_SELLER` is denied and "2 item(s) redacted before the AI" (card number and email).

## 6. Attack Lab (about 60 s)

Sidebar -> **Attack Lab** -> **Run all scenarios** (about 40-60 seconds).

Expected: **14/14 defenses held**. Each card lists the real checks it made. Scenarios 9-14 are the payment-recovery
and evidence ones. Nine scenarios say **MOCKED PayPal (no real payment)**; no scenario can create a real payment.
Open **Observed result** on any card to see the raw responses.

## 7. Lost-response recovery (about 60 s)

This needs a failure that a real Sandbox cannot be made to produce, so it runs against the mocked PayPal in the Attack Lab.

In **Attack Lab**, read these three cards:

| Card | What it proves (all checks green) |
|------|-----------------------------------|
| 9. Payment succeeds but the response is lost | Mock processor executed **1** capture; the caller got **504 CAPTURE_UNCERTAIN**; state is uncertain, not CAPTURED and not FAILED; marker `PENDING_RECONCILIATION`; **no receipt** |
| 10. Agent retries after the lost response | Retry returned `RECONCILED`/`CAPTURED`; **no second capture request was sent**; exactly one capture and one receipt; the same `Idempotency-Key` is a replay (`REUSED`) |
| 11. Outcome cannot be established | PayPal lookup fails: **HTTP 202 `PENDING_RECONCILIATION`**, state unchanged, no receipt, no extra capture; resolves once PayPal is reachable |

Command-line proof: `python -m pytest -q tests/test_recovery.py` (from `backend/`, venv active) -> `16 passed`.

## 8. Evidence verification and tampering (about 50 s)

1. Make a transaction with a receipt first: do section 3 (keyboard, approve), then on **PayPal Checkout** click **Issue development receipt**.
2. Sidebar -> **Recovery & Evidence** -> **Verify chain**. Expected: green "VALID: 3 events verified". The timeline shows each event with a badge: `INTERNAL` (our own record) or `OBSERVED AT PAYPAL` (read from PayPal's API; appears with a real or mocked PayPal payment).
3. Click **Demo: tamper with an event**, then **Verify chain**. Expected: red "INVALID", with reasons such as "Signature does not verify for this exact payload" and "prev_event_digest does not match the previous event: the chain is broken".
4. **Download JSON** and call `POST http://localhost:8000/api/evidence/verify` with `{"events": [...]}` from the file to verify outside the UI.

Attack Lab card 12 repeats this for six kinds of tampering (edited field, relabelled source, deleted event, reordered
events, swapped signature, deleted tail with a pinned head).

## 9. Receipt verification and tampering (about 40 s)

1. **Receipt Verification** -> **Load receipt for current transaction** -> **Verify receipt**: expected **"Receipt is authentic"**, `VALID`, a QR code to share it.
2. Click **Demo: change amount to 0.01** -> **Verify receipt**: expected **"Receipt is NOT valid"**, `INVALID`.
3. Outside the app: save the receipt as `receipt.json` and run `python backend/verify_receipt.py receipt.json --public-key <key from the receipt document>` (needs only the `cryptography` package; exit code 0 = valid, 1 = invalid).

## 10. Real PayPal Sandbox payment (optional, needs credentials)

1. <https://developer.paypal.com> -> Apps & Credentials -> **Sandbox** -> Create App. Copy the Client ID and Secret.
2. `copy backend\.env.example backend\.env`, fill `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET` (no quotes or spaces). Then, from `backend/` with the venv active, check them **without moving money**: `python check_paypal.py` should print `OK: PayPal Sandbox accepted the credentials`. (`python check_paypal.py --order` also creates one 1.00 USD test order and prints the buyer-approval link; it never captures.) Restart the backend. The sidebar should show **PayPal: Sandbox**. (Never commit `.env`.)
3. Testing tools -> Sandbox accounts: note the **Personal** (buyer) account's email and password.
4. In the app: create a `REQUIRE_APPROVAL` intent (Mechanical Keyboard), approve it, open **PayPal Checkout**.
5. **Create PayPal Sandbox order** -> **Buyer approves at PayPal** (log in with the Sandbox buyer) -> return to the app -> **Capture payment**.
6. Expected: state `CAPTURED` **only** because PayPal's API reported a COMPLETED capture; a `PAYMENT_CONFIRMED` receipt appears; **Recovery & Evidence** shows `PAYPAL_OBSERVED` events (`ORDER_CREATED`, `CAPTURE_CONFIRMED`) with PayPal order and capture ids.
7. Optional: on **Recovery & Evidence** click **Agent retry**: expected outcome `REUSED` with no second capture.

> This path has **not** been verified by the project authors yet. Record your own result before relying on it.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| "Cannot reach the backend" in the UI | Backend not running on port 8000, or `VITE_API_BASE_URL` / `OPP_CORS_ORIGINS` mismatch |
| `npm install` or `vite` errors | `node --version` must be 18.18 or newer |
| `Activate.ps1 cannot be loaded` | `Set-ExecutionPolicy -Scope Process Bypass`, or run `.\.venv\Scripts\python.exe -m uvicorn ...` directly |
| `python` opens the Microsoft Store | Use `py -3.13` before the venv is active |
| Everything shows `MANIFEST_INVALID` | Keys and signed manifest are out of step; stop the backend and delete `backend/data/` (development only) |
| Attack Lab says `ATTACK_LAB_BUSY` (429) | Another run is in progress; wait and retry |
| Backend refuses to start with "LIVE API" | `PAYPAL_BASE_URL` must be the Sandbox host `https://api-m.sandbox.paypal.com` |
| Port in use | Stop the other process or change the port and the matching CORS/URL settings |
