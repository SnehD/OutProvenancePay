import { useEffect, useState } from 'react';
import { api } from '../services/api';
import type { Intent } from '../types/api';
import { Badge, Banner, Card, Empty, PageTitle, Spinner, stateTone } from '../components/ui';
import { useWorkflow } from '../state/workflow';

export default function Overview() {
  const { health, healthError, reloadHealth, intent, go, setIntent } = useWorkflow();
  const [recent, setRecent] = useState<Intent[] | null>(null);

  useEffect(() => {
    api.listIntents().then(setRecent).catch(() => setRecent([]));
  }, [intent]);

  return (
    <>
      <PageTitle title="OutProvenance Pay" lead="Safer payments for AI agents: every decision is made by the backend, never by the browser or the AI." />
      <section className="hero">
        <div>
          <h3>Let your AI agent shop. Keep your money safe.</h3>
          <p><strong>AI suggests. Policy decides. Humans approve when required. PayPal confirms payment.</strong></p>
          <p>Try a purchase in under a minute: describe what you need, review the decision, approve, and get a receipt anyone can verify.</p>
          <div className="row">
            <button className="primary" onClick={() => go('request')}>Start a purchase</button>
            <button onClick={() => go('attack')}>Watch attacks get blocked</button>
          </div>
        </div>
        <ul className="chips" aria-label="Safeguards">
          <li>🔒 Private data redacted</li>
          <li>✍️ Signed agents</li>
          <li>🛡️ Server-side rules</li>
          <li>🧾 Verifiable receipts</li>
        </ul>
      </section>
      {healthError && (
        <Banner tone="bad" title="Backend unreachable">
          {healthError.message} Start it with <code>uvicorn app.main:create_app --factory --port 8000</code> inside the backend folder.
        </Banner>
      )}
      {!health && !healthError && <Spinner label="Contacting backend…" />}
      {health && (
        <div className="grid3">
          <Card title="Backend">
            <Badge tone={health.status === 'ok' ? 'ok' : 'bad'}>{health.status}</Badge>
            <p className="muted">Database: {health.database}</p>
          </Card>
          <Card title="PayPal">
            <Badge tone={health.paypal_configured ? 'info' : 'warn'}>{health.paypal_configured ? 'SANDBOX credentials set' : 'Setup required'}</Badge>
            <p className="muted">{health.paypal_configured
              ? 'Payments count only when PayPal Sandbox confirms capture.'
              : 'No payment can be attempted until PAYPAL_CLIENT_ID / SECRET are set in backend/.env. Everything else works.'}</p>
          </Card>
          <Card title="AI assistant">
            <Badge tone={health.ai_configured ? 'info' : 'mock'}>{health.ai_configured ? 'External provider (advisory)' : 'Local fallback (not an LLM)'}</Badge>
            <p className="muted">AI can only suggest a product. It never sets prices or decides policy.</p>
          </Card>
        </div>
      )}
      <div className="row"><button onClick={() => void reloadHealth()}>Refresh status</button></div>

      <Card title="How a purchase flows" subtitle="Follow the steps in the sidebar, in order.">
        <ol className="steps flow">
          <li><button className="link" onClick={() => go('request')}>Describe the purchase</button> — personal data is redacted first.</li>
          <li><button className="link" onClick={() => go('agent')}>Verify the agent manifest</button> — Ed25519 signature checked by the backend.</li>
          <li><button className="link" onClick={() => go('policy')}>Policy decision</button> — ALLOW / REQUIRE_APPROVAL / DENY from fixed rules.</li>
          <li><button className="link" onClick={() => go('approval')}>Internal human approval</button> — only when required, bound to exact details.</li>
          <li><button className="link" onClick={() => go('checkout')}>PayPal Sandbox checkout</button> — buyer approval is separate and happens at PayPal.</li>
          <li><button className="link" onClick={() => go('receipt')}>Signed receipt</button> — verify it independently.</li>
          <li><button className="link" onClick={() => go('attack')}>Attack Lab</button> — watch the defenses hold against real attacks.</li>
        </ol>
      </Card>

      <Card title="Recent transactions">
        {recent === null && <Spinner />}
        {recent && recent.length === 0 && <Empty title="No transactions yet">Create one from the Policy Decision page.</Empty>}
        {recent && recent.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead><tr><th>ID</th><th>Product</th><th>Amount</th><th>State</th><th><span className="sr-only">Action</span></th></tr></thead>
              <tbody>
                {recent.map((r) => (
                  <tr key={r.id}>
                    <td><code>{r.id}</code></td>
                    <td>{r.product_name}</td>
                    <td>{r.amount} {r.currency}</td>
                    <td><Badge tone={stateTone(r.state)}>{r.state}</Badge></td>
                    <td><button onClick={() => { setIntent(r); go('checkout'); }}>Open</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
