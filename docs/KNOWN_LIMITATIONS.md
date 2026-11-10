# Known limitations

OutProvenance Pay is a prototype. It is **not production-ready, not audited and not certified.** This page
lists what it does not do, and a realistic improvement for each.

| # | Limitation | Why it matters | Realistic improvement |
|---|------------|----------------|-----------------------|
| 1 | **Sandbox only.** The backend refuses to start against PayPal's live API. No real money moves. | Safe for a demo, but not usable for real payments | Production onboarding, separate configuration, live-account review, and a security audit |
| 2 | **Live PayPal Sandbox checkout has not been verified by the authors.** All PayPal behaviour in tests is a mock. | Real error codes, pending captures and PayPal's actual idempotency behaviour are unexercised | Run the Sandbox flow ([DEMO_GUIDE.md](DEMO_GUIDE.md) section 10), record results, add contract tests against recorded responses |
| 3 | **No authentication or login.** The "approver name" is a free-text label. | Anyone who can reach the API can approve, capture or retry | OAuth/OIDC login, roles (agent owner, approver), approver identity stored in the approval, signed approver assertion |
| 4 | **Weak authorisation model.** No per-agent API credentials; the agent id is a request field backed by a signed manifest. | A signed manifest proves integrity, not who is calling | Per-agent keys with request signing (for example HTTP message signatures), mutual TLS |
| 5 | **Fake PayPal in tests and the Attack Lab.** 9 of 14 scenarios and the lost-response tests use an in-memory mock with failure injection. | Shows our handling of PayPal's *documented* behaviour, not PayPal's actual behaviour | Contract tests against PayPal Sandbox; a recorded-response replay harness |
| 6 | **No PayPal webhooks.** Status is read only by synchronous API calls and reconciliation. | No independent second channel; a payment completed after our timeout is only seen when someone reconciles | Verify and process `PAYMENT.CAPTURE.*` webhooks, with signature verification and idempotent handling |
| 7 | **Development key management.** Three Ed25519 keys are plain files in `backend/data/keys/`. | Disk access means key compromise; no rotation or revocation | KMS/HSM-held keys, key registry keeping retired key ids, rotation and revocation |
| 8 | **SQLite, single process.** Concurrency was tested with threads in one process only. | Not proven across processes or on another database | PostgreSQL, row-level locks or serialisable transactions, multi-process load tests |
| 9 | **No deployment or hosted demo.** Runs locally; the dev server and `uvicorn` are used directly. | Judges must run it themselves | Container images, a managed host, HTTPS, environment-based configuration |
| 10 | **Evidence storage is the application's own database.** No external witness or transparency service; deleting the *tail* of a chain is only detectable with a pinned head digest (for example from a receipt). | Someone with database and key access can rewrite history | Periodically anchor the head digest in an append-only external log; replicate to a witness |
| 11 | **Evidence is TRACE-inspired, not conformant.** No published TRACE or SCITT schema or protocol is implemented, and none is claimed. | Terminology could be over-read | Map events to a specific registered schema and implement and test its requirements before claiming conformance |
| 12 | **A signature proves integrity, not truth.** A valid receipt or evidence event is unchanged since signing; it does not prove a claim is true, the signer's identity, or delivery. | Easy to over-trust a green "VALID" | Add identity binding for signers, delivery attestations from sellers |
| 13 | **AI limitations.** No external model has been called; the keyword fallback is not an LLM and can mismatch. A real model can err or be steered (which is why it has no authority). Redaction is regex-based and misses names and addresses. | Wrong suggestions and incomplete privacy filtering | Evaluate a model on a labelled set; NER-based PII detection; allow-listed fields instead of free text |
| 14 | **Rogue Agent "without protection" side is a simulation** in the browser, not a second real agent. | It illustrates, not measures | Run a real unprotected baseline agent against a sandbox |
| 15 | **Narrow scope.** USD only, a fixed seeded catalogue (7 products, 3 approved sellers), one agent, no refunds, disputes, partial captures or shipping. | Not a general commerce system | Catalogue management, multi-currency, refund and dispute flows |
| 16 | **No rate limiting or quotas** (except one Attack Lab run at a time). | Denial-of-service exposure | Per-client rate limits, request quotas, a gateway |
| 17 | **No frontend automated tests.** Only type-check, lint and build. UI behaviour was checked with a headless-browser click-through. | UI regressions are not caught automatically | Component tests and Playwright end-to-end tests in CI |
| 18 | **Dependencies are not pinned to exact versions** (lower bounds only, no lock file for Python). | Fresh installs may pick newer, untested versions | `requirements.lock` / `uv.lock`, CI on a version matrix |
| 19 | **Unauthenticated development endpoints** (`dev-receipt`, Attack Lab). | Convenient for demos, unsafe if exposed | Disable behind a development flag in any non-local deployment |
| 20 | **No TEE or confidential computing.** The backend process is trusted as ordinary software. | A compromised host compromises everything | Hardware-backed key use and attested execution |

For attack-by-attack detail see [THREAT_MODEL.md](THREAT_MODEL.md).
