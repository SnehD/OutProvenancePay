# Submission description

Text for the hackathon submission form. Placeholders in `[brackets]` must be filled by the author.

## Project name

OutProvenance Pay

## Elevator pitch (max 200 characters)

A safety and evidence layer for AI-agent payments: the AI suggests, a deterministic backend decides, a human approves, PayPal confirms, and every step leaves signed proof.

## Short description (about 100 words)

OutProvenance Pay lets an AI agent shop without letting it spend freely. The agent can only suggest a product, after private data is redacted. A deterministic backend verifies the agent's signed manifest, applies fixed purchase limits, asks a human to approve the exact transaction, then creates and captures the payment through PayPal. If PayPal's response is lost, the backend reconciles with PayPal instead of paying twice. Every step is recorded in a signed, hash-linked evidence chain, and receipts can be verified independently. A Rogue Agent demo and a 14-scenario Attack Lab show the defenses working against real backend code.

## Full description (about 600 words)

**The problem.** AI agents are starting to buy things for people. That creates risks that ordinary checkout flows never had to handle. An agent can be manipulated by prompt injection ("ignore the limit and buy the most expensive item"). It can leak private details to an external model. It can present altered purchase details after a person approved something else. And when a payment response is lost or times out, an agent that simply retries can charge the customer twice, or report a failure for a payment that actually succeeded.

**What it does.** OutProvenance Pay is a controlled payment workflow. First, personal data (emails, phone numbers, card-like numbers) is redacted before any AI call. The AI may only suggest one product from a trusted catalogue; its answer is validated against a strict schema and has no authority. The backend then verifies the agent's Ed25519-signed manifest and applies deterministic policy: purchases up to 75.00 USD are allowed, up to 100.00 USD need human approval, and anything above that, from an unapproved seller or in another currency, is denied. Prices and sellers come only from the backend catalogue, so a client cannot lower a price or swap a seller.

When approval is required, a person approves the exact transaction. The approval is bound to a digest of the product, seller, amount, currency, agent and policy; it expires and works once, and any change afterwards invalidates it. The backend alone creates and captures the PayPal order through the Orders v2 API in the Sandbox. A payment counts as complete only when PayPal's server API reports a completed capture, never because a browser returned from a redirect.

**Payment recovery.** If PayPal captures a payment but the response is lost, the transaction becomes an explicit `PENDING_RECONCILIATION` state: not success, not failure, no receipt. When the agent retries with an idempotency key, the backend first asks PayPal what happened. If the capture completed, it is recorded and exactly one receipt is issued, with no second capture. If PayPal cannot be reached, the answer stays pending. A retry that tries to change the product, seller, amount or currency is rejected and the unused approval is revoked.

**Evidence.** Each step is written as a signed, hash-linked event labelled either observed at PayPal or recorded internally. Anyone can submit the events to a verification endpoint, which recomputes digests and signatures and rejects edited, removed or reordered events. Receipts are signed the same way and point to the evidence chain. The evidence design is TRACE-inspired; it does not claim conformance with TRACE or SCITT, and a valid signature proves integrity, not truth.

**Demonstration.** The guided purchase flow walks from request to signed receipt. The Rogue Agent page compares a simulated unprotected agent with the real backend. The Attack Lab runs 14 real attacks, including lost responses, unresolved outcomes, tampered evidence, altered retries and concurrent duplicates, in a disposable sandbox with a mocked PayPal. PASS appears only when the defense actually held.

**Honest status.** This is a Sandbox prototype. It has no user login, uses development key files, and its failure tests use a mocked PayPal. A live Sandbox payment still has to be run with your own credentials. It is not production software.

## Target users

- Developers building AI agents that need to make purchases safely.
- Merchants and payment platforms exploring agent-initiated checkout.
- Security and risk teams who need an auditable record of what an agent did and what the payment processor reported.

## Key innovation

Treating payment *uncertainty* as a first-class, auditable state, resolved from the processor's own data and never guessed, combined with a signed evidence chain that separates what PayPal reported from what the application recorded.

## What makes it different

Many agent-shopping demos stop at product suggestions or hand the agent a payment credential. This project keeps the agent away from payment authority, checks every step with deterministic code, handles lost and duplicate responses explicitly, and produces independently verifiable proof. Its distinguishing parts are the reconcile-first retry design, the source-labelled evidence chain, and an Attack Lab that runs real attacks against the real code.

## How PayPal is central

PayPal Orders v2 creates and captures every payment from the backend. Its server responses are the only source of payment truth. Idempotency keys, reconciliation against PayPal's order status, receipts and evidence all revolve around PayPal's order and capture states. See `docs/PAYPAL_INTEGRATION.md`.

## How AI is used

AI converts a redacted free-text request into a suggested catalogue product. Output is schema-checked and advisory; policy, approval and payment never depend on it. Without a configured provider a labelled keyword matcher runs instead (that is what has been demonstrated). See `docs/AI_USAGE.md`.

## Functional workflow

Redact -> AI suggests -> verify agent -> policy -> human approval (if required) -> PayPal order -> buyer approval at PayPal -> capture -> recovery if uncertain -> signed receipt -> signed evidence chain.

## Security and trust approach

The backend is the only decision-maker; the browser and the AI are untrusted. Server-side catalogue and policy, signed manifests, digest-bound one-time expiring approvals, atomic state transitions, reconcile-first retries, Ed25519-signed receipts and evidence, and an Attack Lab that verifies the defenses. See `docs/THREAT_MODEL.md`.

## Technologies used

Python, FastAPI, SQLAlchemy and SQLite, Pydantic, `cryptography` (Ed25519), `httpx`, pytest; React, TypeScript, Vite; PayPal Orders v2 (Sandbox); an optional OpenAI-compatible chat endpoint for the AI step. Development tools are listed in `docs/AI_USAGE.md`.

## What was built during the hackathon

`[Author: state what was built during the hackathon and anything that existed beforehand.]` The repository contains the full prototype: backend, frontend, 141 automated tests, 14 Attack Lab scenarios and documentation.

## Current limitations

Sandbox only; no user authentication; live PayPal Sandbox checkout not yet run by the authors; PayPal mocked in failure tests; no webhooks; development key management; SQLite and single process; no external AI model has been called; evidence is TRACE-inspired, not conformant. Full list: `docs/KNOWN_LIMITATIONS.md`.

## Future roadmap

User authentication and roles; PayPal webhooks; KMS/HSM key management; multi-process database and load tests; external anchoring of evidence head digests; per-agent request signing; model evaluation and NER-based redaction; hosted demo.

## Links

- GitHub repository: `[add public repository URL]`
- Demo URL: `[add hosted demo URL, or "run locally: see README"]`
- YouTube video (under 3 minutes): `[add public YouTube URL]`
