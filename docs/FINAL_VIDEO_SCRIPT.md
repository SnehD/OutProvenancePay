# Final video script (under 3 minutes)

**Target 2:43. Absolute maximum 2:55.** Narration: 328 words, about 2:21 of speech at 140 words per minute (2:26 at a
slower 135). The rest is clicking and pauses. Every page, button, URL and state below was checked against the code and
dry-run in the real app (see "Verification status" at the end for what could not be run).

**Story in one line:** AI suggests. Policy decides. Humans approve when required. PayPal confirms payment.

**The one request to type** (works with the current catalogue; verified):

```
Buy me a keyboard under $100. Email the receipt to jane@example.com
```

It resolves to **Mechanical Keyboard, 89.00 USD, Northwind Electronics**, policy **REQUIRE_APPROVAL**, so the human-approval
step is real. The fake email address exists so the privacy redaction is visible on screen
(`Email the receipt to [REDACTED_EMAIL]`). `jane@example.com` is not a real address; do not substitute your own.

**Everything is one web page.** The app is a single-page app: the address bar stays `http://localhost:5173/` for every
screen (the sidebar changes the screen). The only other URLs you will see are PayPal's Sandbox pages and the return URL
`http://localhost:5173/?paypal=return&intent=txn_...`.

**Real versus simulated (say this honestly):**

| Part | Real PayPal Sandbox? |
|------|----------------------|
| Scenes 2-4, create order, buyer approval, capture, payment confirmation | **Real PayPal Sandbox** (needs your Sandbox credentials) |
| Scene 5, "Agent retry" on the real payment | **Real** (returns the stored result, sends nothing to PayPal) |
| Scene 5, lost-response demo (Attack Lab cards 9 and 10) | **Controlled PayPal simulator** (in-memory mock). Labelled "MOCKED PayPal" on screen. Never present it as a real transaction. |
| Scene 7, "without protection" side | **Simulation** in the browser. The right side is the real backend. |

---

## Scene 1 - Problem

TIME:
0:00 - 0:19

SCREEN:
Overview (sidebar item "Overview"). The big banner reads **OutProvenance Pay**; under it "Safer payments for AI agents".

URL:
`http://localhost:5173/`

ACTION:
Start recording on the Overview page. Do not click anything. Speak.

CLICK:
none

TYPE:
none

SAY:
"AI agents are starting to buy things for us. But what if an agent is manipulated, leaks private information, or retries a payment after the response was lost? OutProvenance Pay adds a safety and evidence layer between AI agents and PayPal."

EXPECTED RESULT:
Overview page, no errors. Banner title "OutProvenance Pay". Hero line: "AI suggests. Policy decides. Humans approve when required. PayPal confirms payment."

ON-SCREEN ELEMENTS TO SHOW:
The banner "OutProvenance Pay", the bold hero line "AI suggests. Policy decides. Humans approve when required. PayPal confirms payment.", the sidebar badges "PayPal: Sandbox" and "AI: external" (see the must-fix list).

RECORDING NOTE:
Let the bold hero line stay on screen for the last sentence. The sidebar must say **PayPal: Sandbox** (not "setup required").

RUNNING TOTAL: 0:19

---

## Scene 2 - AI suggestion

TIME:
0:19 - 0:39

SCREEN:
Purchase Request, then Privacy Preview, then back to Purchase Request.

URL:
`http://localhost:5173/` (unchanged)

ACTION:
Open the purchase flow, type the request, show what would be sent to the AI (redacted), then ask for the suggestion.

CLICK:
Sidebar **Purchase Request** -> (after typing) **Preview what leaves this server** -> **Preview redaction** -> **Back to request** -> **Find product**.

TYPE:
`Buy me a keyboard under $100. Email the receipt to jane@example.com` (into the "Purchase request" box)

SAY:
"I ask the agent: buy me a keyboard under one hundred dollars. Private details, like this email, are redacted before anything reaches the AI. The AI only suggests a product. It cannot authorize payment, change the trusted price, or decide what is allowed."

EXPECTED RESULT:
Privacy Preview shows `Buy me a keyboard under $100. Email the receipt to [REDACTED_EMAIL]` and "Emails redacted: 1". After **Find product**, the "Assistant suggestion" card shows: "Suggested product ID: keyboard", the source badge, and "Backend policy for it: **REQUIRE_APPROVAL** 89.00 USD from Northwind Electronics". The note "AI output is advisory. Price, seller and decision come from the backend." is on the same card.

ON-SCREEN ELEMENTS TO SHOW:
The redacted text with `[REDACTED_EMAIL]`; the "Assistant suggestion" card, with the AI suggestion on top and the "Backend policy for it" line beneath it (this is the AI suggestion -> backend policy distinction); the source badge should read **external-llm**.

RECORDING NOTE:
Say "The AI only suggests a product" while the suggestion card is visible. If you did not configure a real AI model, the badge says `local-fallback` and "not an LLM". Then use the ALTERNATE LINE below instead of the third sentence.

ALTERNATE LINE (only if no AI model is configured; do not pretend otherwise):
"Here the suggestion step uses a built-in keyword matcher, and any OpenAI-compatible model can be plugged in. It still only suggests; it cannot authorize payment, change the trusted price, or decide what is allowed."

RUNNING TOTAL: 0:39

---

## Scene 3 - Policy and approval

TIME:
0:39 - 1:00

SCREEN:
Agent Verification -> Policy Decision -> Approval (all sidebar items).

URL:
`http://localhost:5173/` (unchanged)

ACTION:
Verify the agent, evaluate policy, create the intent, approve it.

CLICK:
Sidebar **Agent Verification** -> **Verify signature now** -> sidebar **Policy Decision** -> **Evaluate policy** -> **Create transaction intent** -> (on Approval) tick the checkbox -> **Approve transaction**.

TYPE:
`Demo Approver` into "Approver name" (do not use your real name).

SAY:
"The backend verifies the agent's signature, then applies fixed rules to the trusted catalogue price. Eighty nine dollars requires human approval, and that approval is tied to this exact product, seller and amount. It expires, works once, and cannot be reused if the details change."

EXPECTED RESULT:
Agent Verification: green banner "Signature VALID". Policy Decision: Decision card **REQUIRE_APPROVAL**, "Amount 89.00 is above 75.00; explicit human approval required.", Amount (trusted) 89.00 USD, Seller (trusted) Northwind Electronics, Policy version policy-2026.1. After **Create transaction intent** the app moves to **Internal Approval**, which lists Product, Seller, Amount and the "Bound details digest". After **Approve transaction**: banner "Approved - By Demo Approver. Expires ... Not yet used."

ON-SCREEN ELEMENTS TO SHOW:
"Signature VALID"; "REQUIRE_APPROVAL" with "Amount (trusted) 89.00 USD"; the "Bound details digest" line; the "Approved ... Not yet used" banner.

RECORDING NOTE:
Approval works for 10 minutes and once, so do this scene and Scene 4 back to back. Do not read the digest aloud.

RUNNING TOTAL: 1:00

---

## Scene 4 - PayPal Sandbox (the central scene)

TIME:
1:00 - 1:26

SCREEN:
PayPal Checkout, then PayPal's own Sandbox page in a new tab, then back to PayPal Checkout.

URL:
`http://localhost:5173/` -> PayPal Sandbox approval page (opens in a new tab) -> `http://localhost:5173/?paypal=return&intent=txn_...` (PayPal sends the buyer back here).

ACTION:
Create the PayPal order, let the buyer approve at PayPal, capture, and show the confirmed payment.

CLICK:
**Continue to PayPal Checkout** -> **1. Create PayPal Sandbox order** -> **2. Buyer approves at PayPal ↗** (new tab; on PayPal click the approve/continue button; you are returned to the app) -> **3. Capture payment**.

TYPE:
nothing (be already logged in to the Sandbox buyer; see the cheat sheet).

SAY:
"Once it passes the checks, the backend creates the PayPal Sandbox order. The buyer approves it on PayPal, and the backend captures the payment. OutProvenance does not trust a success message from the browser. It marks the payment completed only after PayPal confirms it."

EXPECTED RESULT:
After step 1: state **ORDER_CREATED**, "PayPal order" shows an order id, "PayPal order status" shows the status PayPal returned (for example PAYER_ACTION_REQUIRED or CREATED; not verifiable here without credentials), the "2. Buyer approves at PayPal ↗" link appears. After capture: green banner **"Payment confirmed by PayPal Sandbox"** ("The backend read a COMPLETED capture from PayPal's API. A signed receipt was issued."), state **CAPTURED**, "PayPal order status" **COMPLETED**, and a "PayPal capture ID".

ON-SCREEN ELEMENTS TO SHOW:
The state badge CAPTURED; "Payment confirmed by PayPal Sandbox"; "PayPal order status COMPLETED"; "PayPal capture ID"; the PayPal Sandbox page for about 2 seconds so PayPal is visibly part of the flow.

RECORDING NOTE:
Be pre-logged-in to the Sandbox buyer so you only click once on PayPal (typing a password on camera is a leak and takes time). Say the first sentence over the checkout page, the second while the PayPal tab is open, the last two over the confirmation banner. If PayPal is slow, keep talking and cut the wait in editing. Order and capture ids are Sandbox test ids and are fine to show.

RUNNING TOTAL: 1:26

---

## Scene 5 - Lost response and safe recovery (hero scene)

TIME:
1:26 - 1:57

SCREEN:
Recovery & Evidence, then Attack Lab.

URL:
`http://localhost:5173/` (unchanged)

ACTION:
First retry the real payment and show nothing new is sent. Then run the two controlled-simulator scenarios that reproduce a lost response and its recovery.

CLICK:
Sidebar **Recovery & Evidence** -> **Agent retry** -> sidebar **Attack Lab** -> scroll to card **9. Payment succeeds but the response is lost** -> its **Run** -> scroll to card **10. Agent retries after the lost response** -> its **Run**.

TYPE:
nothing (the Idempotency-Key box is pre-filled).

SAY:
"Now the dangerous case: PayPal processed a payment, but the response was lost. Retrying our real payment returns the original result, and sends nothing new to PayPal. To reproduce a lost response safely, I'm using a controlled PayPal simulator. The payment shows as pending, not success and not failure. On retry, the backend asks PayPal first, finds the completed payment, and creates no second one."

EXPECTED RESULT:
Recovery & Evidence, after **Agent retry**: banner **"Retry result: REUSED"** with "Already captured. The original result is returned; nothing was sent to PayPal." The page also shows "Confirmed by PayPal" and the Execution attempts table. Attack Lab card 9 (badge **MOCKED PayPal**, then **PASS**): "The mock processor really executed one capture", "The caller is NOT told it succeeded - HTTP 504 CAPTURE_UNCERTAIN", "State is uncertain, not CAPTURED and not FAILED - state=CAPTURE_UNCERTAIN", "Explicit PENDING_RECONCILIATION marker is exposed", "No payment receipt is issued for an unconfirmed payment - receipts=0". Card 10 (**MOCKED PayPal**, **PASS**): "Retry is tied to the original intent and reconciled with PayPal - HTTP 200 outcome=RECONCILED state=CAPTURED", "No second capture request was sent to PayPal - capture requests before/after: 1/1", "Exactly one capture exists at the processor - captures=1".

ON-SCREEN ELEMENTS TO SHOW:
"Retry result: REUSED"; the purple **MOCKED PayPal** badge and the "Safe sandbox" banner at the top of the Attack Lab; the lines "state=CAPTURE_UNCERTAIN", "PENDING_RECONCILIATION", "receipts=0", "outcome=RECONCILED", "capture requests before/after: 1/1", "captures=1".

RECORDING NOTE:
The lost-response test is a mock; the words "controlled PayPal simulator" must be spoken while the **MOCKED PayPal** badge is on screen. Do not call it a real transaction. Do not click "Run all scenarios" (about 45 seconds). Scroll to cards 9 and 10 with Page Down; each Run finishes in under a second. The app's word for this state is **PENDING_RECONCILIATION** (shown after the simulated lost response as CAPTURE_UNCERTAIN); say "pending".

RUNNING TOTAL: 1:57

---

## Scene 6 - Signed receipt and evidence

TIME:
1:57 - 2:14

SCREEN:
Receipt Verification, then Recovery & Evidence.

URL:
`http://localhost:5173/` (unchanged)

ACTION:
Verify the real receipt, verify the evidence chain, tamper with one event, verify again.

CLICK:
Sidebar **Receipt Verification** -> **Load receipt for current transaction** -> **Verify receipt** -> sidebar **Recovery & Evidence** -> **Verify chain** -> **Demo: tamper with an event** -> **Verify chain**.

TYPE:
nothing.

SAY:
"Every payment also produces a signed receipt and a chained evidence trail. Verification passes. If someone changes the recorded evidence afterward, verification fails. The signature shows integrity, not that every claim is true."

EXPECTED RESULT:
Receipt Verification: the receipt JSON shows `"receipt_type": "PAYMENT_CONFIRMED"`; after **Verify receipt**, a big green **"Receipt is authentic"** and `VALID`. Recovery & Evidence: green **"VALID: 11 events verified"** (11 with one Agent retry from Scene 5, 9 without; "Check PayPal status" adds one more) with the timeline showing `INTERNAL` and **OBSERVED AT PAYPAL** badges. After the tamper: purple "Local copy edited" and a red **"INVALID: this evidence cannot be trusted"** listing "Signature does not verify for this exact payload."

ON-SCREEN ELEMENTS TO SHOW:
"Receipt is authentic"; "VALID: 11 events verified"; the OBSERVED AT PAYPAL badges; "INVALID: this evidence cannot be trusted".

RECORDING NOTE:
Say "verification passes" while the green banner is up, and "verification fails" as the red banner appears. Do not say the signature proves the payment details are true. Skipping "Receipt Verification" saves about 5 seconds if you are over time.

RUNNING TOTAL: 2:14

---

## Scene 7 - Rogue Agent

TIME:
2:14 - 2:27

SCREEN:
Rogue Agent.

URL:
`http://localhost:5173/` (unchanged)

ACTION:
Run the first preset against both sides.

CLICK:
Sidebar **Rogue Agent** -> **Unleash the rogue agent** (the first preset, "Ignore the limit", is already selected).

TYPE:
nothing.

SAY:
"Here is a malicious instruction. On the left, a simulation of an unprotected agent would buy it. On the right, the real backend denies it."

EXPECTED RESULT:
Two columns. Left: **"Without protection" SIMULATED**, "Bought: Noise-Cancelling Headphones ... No limit, no seller check, no human in the loop." Right: **"With OutProvenance Pay" REAL BACKEND**, "Blocked: Noise-Cancelling Headphones - DENY OVER_LIMIT. Amount 129.00 exceeds the 100.00 maximum purchase limit."

ON-SCREEN ELEMENTS TO SHOW:
Both column headings including the **SIMULATED** and **REAL BACKEND** badges, and the red "Bought" box beside the green "Blocked" box.

RECORDING NOTE:
Scroll down slightly after clicking so both columns are fully visible. If you are running over time, **delete this scene** (saves 13 seconds) and go straight to Scene 8.

RUNNING TOTAL: 2:27

---

## Scene 8 - Final statement

TIME:
2:27 - 2:43

SCREEN:
Overview.

URL:
`http://localhost:5173/`

ACTION:
Return to the clean start screen, speak, stop recording.

CLICK:
Sidebar **Overview**.

TYPE:
none.

SAY:
"OutProvenance Pay lets AI help with purchasing without giving AI authority over money. AI suggests. Policy decides. Humans approve when required. PayPal confirms the payment, and every important decision leaves verifiable evidence."

EXPECTED RESULT:
Overview with the banner "OutProvenance Pay" and "Safer payments for AI agents: every decision is made by the backend, never by the browser or the AI." and the bold hero line.

ON-SCREEN ELEMENTS TO SHOW:
Banner "OutProvenance Pay" and "Safer payments for AI agents"; the hero line "AI suggests. Policy decides. Humans approve when required. PayPal confirms payment."

RECORDING NOTE:
Stay still for 2 seconds after the last word, then stop recording.

RUNNING TOTAL: 2:43

---

## Timing check

| Scene | Words | Speech at 140 wpm | Scene time | Running total |
|-------|-------|-------------------|------------|---------------|
| 1 Problem | 41 | 17.6 s | 0:19 | 0:19 |
| 2 AI suggestion | 43 | 18.4 s | 0:20 | 0:39 |
| 3 Policy and approval | 45 | 19.3 s | 0:21 | 1:00 |
| 4 PayPal Sandbox | 44 | 18.9 s | 0:26 | 1:26 |
| 5 Lost response and recovery | 65 | 27.9 s | 0:31 | 1:57 |
| 6 Receipt and evidence | 33 | 14.1 s | 0:17 | 2:14 |
| 7 Rogue Agent | 25 | 10.7 s | 0:13 | 2:27 |
| 8 Final statement | 32 | 13.7 s | 0:16 | 2:43 |
| **Total** | **328** | **140.6 s (2:21)** | | **2:43** |

At a slower 135 words per minute the speech is 145.8 s (2:26), still inside every scene's time. If PayPal's approval
page is slow, Scene 4 can grow by up to 9 seconds and the video still ends before 2:55. If you are over 2:55, delete
Scene 7.

## Do not say

"first solution", "nothing like this exists", "completely secure", "100% secure", "unhackable", "prevents all fraud",
"guarantees no duplicate payments", "the signature proves the receipt is true", "production-ready".

## Verification status (what was and was not checked)

Dry-run on the real app, with the exact clicks and text above, and everything worked: Scenes 1, 2 (with the fallback AI),
3, 5 (Attack Lab cards 9, 10, 11), 6 (with a development receipt), 7 and 8, and the checkout page's "setup required"
behaviour. **Not run on this machine** because they need your credentials: the real PayPal create, buyer approval and
capture (Scene 4), "Agent retry" returning REUSED on a real payment (Scene 5 first half), the real PAYMENT_CONFIRMED
receipt and the OBSERVED AT PAYPAL badges (Scene 6), and the `external-llm` AI badge (Scene 2). Those are covered by
mocked automated tests only, so do one full rehearsal with your credentials before the final take.
