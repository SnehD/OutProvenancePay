# Judging alignment

How OutProvenance Pay maps to the hackathon requirements, with where to look and how to check each one.
Items that are **not yet done** are marked plainly.

| Requirement | OutProvenance Pay implementation | Evidence in repository (file or route) | Demo step / how a judge verifies |
|-------------|----------------------------------|----------------------------------------|-----------------------------------|
| **Meaningful PayPal use** | PayPal Orders v2 is the payment engine. The backend creates the order from a trusted intent, the buyer approves at PayPal, the backend fetches the order and captures. `CAPTURED` is set only when PayPal's API reports a COMPLETED capture. Idempotency keys (`PayPal-Request-Id`) on create and capture; reconciliation against PayPal's order status after uncertain outcomes; PayPal observations are recorded as signed evidence. | `backend/app/services/paypal.py`, `services/payments.py`, `services/recovery.py`; routes `POST /api/transactions/{id}/paypal/order`, `/capture`, `/retry`, `/reconcile`, `GET .../status`; [PAYPAL_INTEGRATION.md](PAYPAL_INTEGRATION.md) | [DEMO_GUIDE.md](DEMO_GUIDE.md) section 10 (live Sandbox, needs credentials) and section 7 (mocked failure injection). `pytest tests/test_paypal_mocked.py tests/test_recovery.py`. **Live Sandbox run not yet performed by the authors.** |
| **Meaningful AI use** | AI turns free-text requests into a suggested catalogue product, behind redaction and a strict output schema; it has no authority. A labelled keyword fallback runs when no provider is configured. | `backend/app/services/ai.py`, `services/privacy.py`, `api/purchase.py`; [AI_USAGE.md](AI_USAGE.md) | Purchase Request -> Find product; Privacy Preview; Rogue Agent page. `pytest tests/test_privacy_ai.py`. **Only the fallback has run live; no external model was called.** Set `AI_API_KEY`, `AI_BASE_URL`, `AI_MODEL` to use a provider. |
| **Working prototype** | Full flow: redact -> suggest -> verify agent -> policy -> approval -> PayPal -> recovery -> signed receipt -> evidence. FastAPI backend, React frontend, SQLite. | `backend/`, `frontend/`; [README.md](../README.md) | Start both servers, then follow [DEMO_GUIDE.md](DEMO_GUIDE.md) sections 2-3 (purchase and approval) and 8 (evidence). |
| **Sufficient documentation** | README plus architecture, threat model, PayPal and AI pages, demo guide, limitations, FAQ, audit and verification report. | `README.md`, `docs/*.md` | Open [README.md](../README.md); every doc is linked from its "Documentation" section. |
| **Functional demonstration** | Rogue Agent comparison, guided purchase and approval flow, 14-scenario Attack Lab, evidence and receipt verification with tamper demos. | `frontend/src/pages/RogueAgent.tsx`, `PurchaseRequest.tsx`, `AttackLab.tsx`, `Recovery.tsx`, `ReceiptVerification.tsx` | [DEMO_GUIDE.md](DEMO_GUIDE.md): about five minutes, no credentials needed for sections 1-9. |
| **Setup and run instructions** | Exact Windows/PowerShell commands, environment variables, troubleshooting. A hosted demo does not exist yet. | README "Install and run", [DEMO_GUIDE.md](DEMO_GUIDE.md) | Follow "Start (two terminals)". |
| **Tests** | 141 backend tests; 14 Attack Lab scenarios; frontend type-check, lint and build. | `backend/tests/`, `backend/app/services/attack_lab.py` | `python -m pytest -q` in `backend/` -> `141 passed`; Attack Lab -> 14/14. Results and commands: [VERIFICATION_REPORT.md](VERIFICATION_REPORT.md). |
| **Tools disclosure (AI and developer tools)** | Table of AI services and developer tools and how each was used. | [AI_USAGE.md](AI_USAGE.md) "Tools used to build the project" | Read the table. **The author must confirm it (for example whether Copilot was used) before submission.** |
| **Open-source repository readiness** | MIT license, `.gitignore` excluding secrets/keys/databases, `.env.example` files with empty values, `SECURITY.md`, no hardcoded secrets (audited). | `LICENSE`, `.gitignore`, `backend/.env.example`, `frontend/.env.example`, [REPOSITORY_AUDIT.md](REPOSITORY_AUDIT.md) | Check `LICENSE` is visible at the repository root. **The repository has no commits yet and is not yet public.** |
| **Visible license file** | `LICENSE` (MIT) at the repository root | `LICENSE` | Open it. |
| **No unlicensed assets** | No third-party music, images, fonts or copied PayPal logos. The logo is an original SVG; screenshots are captures of this app. | `frontend/src/App.tsx` (SVG logo), `docs/images/` | Inspect the repository tree. |
| **Public YouTube video under 3 minutes** | Script prepared in [FINAL_VIDEO_SCRIPT.md](FINAL_VIDEO_SCRIPT.md). **Not yet recorded or uploaded.** | [FINAL_VIDEO_SCRIPT.md](FINAL_VIDEO_SCRIPT.md) | Link goes in the README "Links" section once uploaded. |
| **Honesty about limits** | Prototype status, mocked-versus-live table, known limitations, TRACE-inspired (not conformant) wording. | [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md), [THREAT_MODEL.md](THREAT_MODEL.md) | Read the limitations page. |

## Video readiness checklist

- [x] Script drafted ([FINAL_VIDEO_SCRIPT.md](FINAL_VIDEO_SCRIPT.md)), timed to fit under 3 minutes.
- [x] Every screen in the script exists and was exercised.
- [x] No credentials, secrets or personal data appear on screen in the default run.
- [ ] Narration recorded (author's own voice or a text-to-speech voice they are licensed to use).
- [ ] Video uploaded to YouTube as public, under 3:00.
- [ ] Link added to README and the submission form.

## Submission checklist

- [ ] Push the repository to a **public** GitHub repository.
- [ ] Add the repository, hosted-demo (if any) and YouTube links to [README.md](../README.md) "Links".
- [ ] Confirm the tools table in [AI_USAGE.md](AI_USAGE.md).
- [ ] (Recommended) Run the live Sandbox payment once and record the result in [VERIFICATION_REPORT.md](VERIFICATION_REPORT.md).
