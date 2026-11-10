# RECORD THIS DEMO

Follow top to bottom. Target **2:43**, never over **2:55**. Full detail: [FINAL_VIDEO_SCRIPT.md](FINAL_VIDEO_SCRIPT.md).
App address for every screen: **http://localhost:5173/** (use `localhost`, not `127.0.0.1`).

## BEFORE RECORDING

**One-time setup (not on camera)**

[ ] PayPal Sandbox keys are in `backend/.env` (`PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`). Never show this file.
[ ] `cd backend` then `python check_paypal.py` prints **OK: PayPal Sandbox accepted the credentials**
[ ] AI model configured in `backend/.env` (`AI_API_KEY`, `AI_BASE_URL`, `AI_MODEL`), or you will use the ALTERNATE LINE in Scene 2
[ ] Sandbox **Personal (buyer)** account exists (developer.paypal.com > Testing tools > Sandbox accounts)

**Right before each take**

[ ] Stop the backend. **Delete the folder `backend\data`** (clean demo data; keys regenerate)
[ ] Backend running: `cd backend`, activate the venv, `uvicorn app.main:create_app --factory --port 8000`
[ ] Frontend running: `cd frontend`, `npm run dev` (Node 18.18 or newer)
[ ] Open **http://localhost:5173/** in a **fresh Guest/Incognito window** with no bookmarks bar and only one tab
[ ] In that same window, open a second tab, log in to the **Sandbox buyer** once on PayPal, then close that tab
[ ] Sidebar badges read **PayPal: Sandbox** and **AI: external** (if AI says "local fallback", see Scene 2)
[ ] Overview page shows "OutProvenance Pay" and the line "AI suggests. Policy decides. ..."
[ ] Windows notifications off (Focus assist: Alarms only), phone silent, other apps closed
[ ] Browser zoom **125%**, window maximised at 1920x1080
[ ] Secrets hidden: no terminal, no editor, no `.env`, no password manager pop-up, no personal email on screen
[ ] Microphone tested (speak one sentence, play it back)
[ ] Recording set to **1080p, 30 fps**, window or screen capture of the browser only (OBS, or Win+Alt+R)
[ ] Script open on another screen or device. Do a **full rehearsal** first, then delete `backend\data` again

---

## START RECORDING

### STEP 1 - 0:00 to 0:19 - Problem
Screen: **Overview**
Click: nothing
Say:
"AI agents are starting to buy things for us. But what if an agent is manipulated, leaks private information, or retries a payment after the response was lost? OutProvenance Pay adds a safety and evidence layer between AI agents and PayPal."
Must be visible: banner "OutProvenance Pay"; bold line "AI suggests. Policy decides. Humans approve when required. PayPal confirms payment."

### STEP 2 - 0:19 to 0:39 - AI suggestion
Screen: **Purchase Request**
Click: sidebar **Purchase Request**
Type: `Buy me a keyboard under $100. Email the receipt to jane@example.com`
Click: **Preview what leaves this server**, then **Preview redaction**
Check: text shows `[REDACTED_EMAIL]`, "Emails redacted 1"
Click: **Back to request**, then **Find product**
Say:
"I ask the agent: buy me a keyboard under one hundred dollars. Private details, like this email, are redacted before anything reaches the AI. The AI only suggests a product. It cannot authorize payment, change the trusted price, or decide what is allowed."
Must be visible: "Assistant suggestion" card, "Suggested product ID: keyboard", "Backend policy for it: REQUIRE_APPROVAL 89.00 USD", source badge `external-llm`.
(If the badge says `local-fallback`, replace the third sentence with: "Here the suggestion step uses a built-in keyword matcher, and any OpenAI-compatible model can be plugged in. It still only suggests; it cannot authorize payment, change the trusted price, or decide what is allowed.")

### STEP 3 - 0:39 to 1:00 - Policy and approval
Click: **Use this product**
Click: sidebar **Agent Verification**, then **Verify signature now**  -> green "Signature VALID"
Click: sidebar **Policy Decision**, then **Evaluate policy**  -> "REQUIRE_APPROVAL", "Amount (trusted) 89.00 USD"
Click: **Create transaction intent**  -> Internal Approval page
Type in "Approver name": `Demo Approver`
Click: the checkbox ("I have reviewed the product, seller and amount..."), then **Approve transaction**  -> "Approved ... Not yet used"
Say:
"The backend verifies the agent's signature, then applies fixed rules to the trusted catalogue price. Eighty nine dollars requires human approval, and that approval is tied to this exact product, seller and amount. It expires, works once, and cannot be reused if the details change."
Do not read the digest aloud. Go straight on to Step 4 (approval lasts 10 minutes).

### STEP 4 - 1:00 to 1:26 - PayPal Sandbox
Click: **Continue to PayPal Checkout**
Click: **1. Create PayPal Sandbox order**  -> state ORDER_CREATED, an order id appears
Click: **2. Buyer approves at PayPal ↗**  -> new tab on PayPal Sandbox; click the PayPal approve / continue button once (already logged in)
Wait for the app to return (address `localhost:5173/?paypal=return&intent=...`)
Click: **3. Capture payment**
Say:
"Once it passes the checks, the backend creates the PayPal Sandbox order. The buyer approves it on PayPal, and the backend captures the payment. OutProvenance does not trust a success message from the browser. It marks the payment completed only after PayPal confirms it."
Must be visible: PayPal Sandbox page for ~2 seconds; then green "Payment confirmed by PayPal Sandbox", state CAPTURED, "PayPal order status COMPLETED", "PayPal capture ID".

### STEP 5 - 1:26 to 1:57 - Lost response and recovery
Click: sidebar **Recovery & Evidence**
Say: "Now the dangerous case: PayPal processed a payment, but the response was lost."
Click: **Agent retry**  -> "Retry result: REUSED"
Say: "Retrying our real payment returns the original result, and sends nothing new to PayPal."
Click: sidebar **Attack Lab**
Say: "To reproduce a lost response safely, I'm using a controlled PayPal simulator."
Press Page Down until card **9. Payment succeeds but the response is lost** is on screen. Click its **Run**.
Say: "The payment shows as pending, not success and not failure."
Must be visible: purple **MOCKED PayPal** badge, "state=CAPTURE_UNCERTAIN", "PENDING_RECONCILIATION", "receipts=0".
Press Page Down to card **10. Agent retries after the lost response**. Click its **Run**.
Say: "On retry, the backend asks PayPal first, finds the completed payment, and creates no second one."
Must be visible: "outcome=RECONCILED", "capture requests before/after: 1/1", "captures=1".
Do NOT click "Run all scenarios".

### STEP 6 - 1:57 to 2:14 - Receipt and evidence
Click: sidebar **Receipt Verification**, then **Load receipt for current transaction**, then **Verify receipt**  -> "Receipt is authentic"
Say: "Every payment also produces a signed receipt and a chained evidence trail."
Click: sidebar **Recovery & Evidence**, then **Verify chain**  -> "VALID: 11 events verified"
Say: "Verification passes."
Click: **Demo: tamper with an event**, then **Verify chain**  -> red "INVALID: this evidence cannot be trusted"
Say: "If someone changes the recorded evidence afterward, verification fails. The signature shows integrity, not that every claim is true."

### STEP 7 - 2:14 to 2:27 - Rogue Agent (delete this step if over time)
Click: sidebar **Rogue Agent**, then **Unleash the rogue agent**; scroll so both columns show
Say:
"Here is a malicious instruction. On the left, a simulation of an unprotected agent would buy it. On the right, the real backend denies it."
Must be visible: "Without protection SIMULATED" next to "With OutProvenance Pay REAL BACKEND", "Blocked ... DENY OVER_LIMIT".

### STEP 8 - 2:27 to 2:43 - Final statement
Click: sidebar **Overview**
Say:
"OutProvenance Pay lets AI help with purchasing without giving AI authority over money. AI suggests. Policy decides. Humans approve when required. PayPal confirms the payment, and every important decision leaves verifiable evidence."
Hold still 2 seconds on the "OutProvenance Pay / Safer payments for AI agents" banner.

## STOP RECORDING

---

## AFTER RECORDING

[ ] Length is under 3:00 (check the file; aim 2:43, never over 2:55)
[ ] Watch it once with sound: no secrets, no `.env`, no passwords, no personal email
[ ] PayPal Sandbox appears in Step 4 and "MOCKED PayPal" is visible in Step 5
[ ] Upload to YouTube as **Public**, then add the link to the README and the submission form

## IF YOU ARE RUNNING OVER TIME

1. Delete Step 7 (Rogue Agent): saves 13 s.
2. In Step 6, skip "Receipt Verification": saves 5 s.
3. In Step 2, skip "Preview what leaves this server": saves 5 s (but then the redaction is not shown).
