# Judge FAQ

Short, factual answers. Details are linked.

**Why is this an AI project if AI cannot approve a payment?**
Because AI agents buying things is the problem it addresses. AI does a useful job here (turns messy text into a
product suggestion, behind redaction and schema checks) and the project is the safety layer that makes letting an
agent act on that suggestion reasonable. The point is that autonomy is bounded by deterministic rules, not by trusting
the model. See [AI_USAGE.md](AI_USAGE.md).

**Why is PayPal central?**
PayPal Orders v2 moves the money, and PayPal's server response is the only thing that can mark a payment complete.
The recovery logic, idempotency keys, reconciliation, signed receipts and evidence all revolve around PayPal's order
and capture states. Without PayPal there is nothing to recover or prove. See [PAYPAL_INTEGRATION.md](PAYPAL_INTEGRATION.md).

**Why not let PayPal alone handle duplicate payments?**
We do use PayPal's idempotency header. But an agent that lost a response may retry with a new request, or after a
state change, so our backend keeps its own state: one atomic state claim per operation, one approval per transaction,
and a reconcile-first rule. We also do not assume PayPal's idempotency behaves as documented in every case, so we
check PayPal's actual order state before sending anything again.

**How do you know a charge was not duplicated?**
Three independent signs: our attempt records show a single `capture` attempt; the signed evidence chain shows one
`CAPTURE_CONFIRMED` with one PayPal capture id; and PayPal's order shows one capture. In tests, the mock processor
counts executed captures and the Attack Lab asserts exactly one. (On real PayPal, the order in the PayPal dashboard is
the authoritative check.)

**What happens if PayPal captures the payment but your server loses the response?**
The transaction becomes `CAPTURE_UNCERTAIN` (shown as `PENDING_RECONCILIATION`); no receipt is issued and nothing is
reported as success or failure. On retry the backend asks PayPal first. If PayPal shows a completed capture, we record
it and issue one receipt, with no second capture request. If PayPal shows no capture, one capture is sent with the same
request id. If PayPal can't be reached, the answer stays "pending". This is demonstrated with a **mocked** PayPal.

**Why do you need signed receipts?**
So anyone can check, without trusting our database, that a receipt is unchanged since the backend signed it. Changing
the amount from 89.00 to 0.01 makes verification fail. A payment receipt is only issued after PayPal confirmed the capture.

**What is the difference between a receipt and an evidence chain?**
A receipt is one signed statement about the outcome ("this was paid"). The evidence chain is the signed, ordered
history of how we got there: intent, approval, each attempt, what PayPal reported, the uncertainty, the receipt. The
receipt points at the evidence head it was issued against.

**Does a digital signature prove that the original claim is true?**
No. It proves the content is unchanged since a trusted key signed it. An `INTERNAL` event is our own record; a
`PAYPAL_OBSERVED` event records what PayPal's API returned to us. Neither proves anything about the real world beyond that.

**What stops a rogue agent?**
The agent has no payment authority. The backend verifies its signed manifest, reads price and seller only from the
trusted catalogue, applies fixed limits (deny above 100.00, approval above 75.00), requires a human approval bound to
the exact details, and only PayPal's response marks a payment complete. Try the **Rogue Agent** page.

**Is this production-ready?**
No. It is a Sandbox-only prototype with no user authentication, development key handling and a mocked PayPal in its
failure tests. See [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

**How is this different from a normal AI shopping assistant?**
A normal assistant ends at "here is a product" or hands the agent a payment credential. Here the agent never holds
payment authority, every step is checked by deterministic code, uncertain payment outcomes are handled explicitly, and
every decision leaves tamper-evident proof. The differentiation is the controlled workflow, recovery and evidence, not
the shopping suggestion.

**Is the evidence format an official standard?**
No. It is **TRACE-inspired** (signed, hash-linked, source-labelled events). It does not implement a published TRACE or
SCITT schema or protocol and we do not claim conformance.

**What is implemented versus simulated?**
Implemented and run: privacy redaction, keyword fallback AI, manifest signing, policy, approvals, state machine,
receipts, evidence chain, retry/reconcile logic, the UI and 14 Attack Lab scenarios. **Mocked:** PayPal in all
failure-injection tests and in 9 Attack Lab scenarios. **Simulated:** the "without protection" side of Rogue Agent.
**Not verified:** a live Sandbox payment, an external AI model call. **Not implemented:** login, webhooks.

**How would this scale beyond PayPal?**
The payment provider is behind one client module (`services/paypal.py`) and one orchestration module. A second
processor would implement the same create, observe and capture operations, with its own idempotency mechanism, and the
policy, approval, recovery and evidence layers would apply unchanged. Not implemented today.

**What is the strongest innovation?**
Treating *uncertainty* as a first-class state: a lost payment response becomes an explicit, auditable
`PENDING_RECONCILIATION` that is resolved from the processor's own data, never guessed, together with a signed evidence
chain that separates what PayPal reported from what our application recorded.
