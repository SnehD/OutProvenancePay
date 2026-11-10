import type { ReactElement } from 'react';
import { Badge } from './components/ui';
import AgentVerification from './pages/AgentVerification';
import Approval from './pages/Approval';
import AttackLab from './pages/AttackLab';
import Catalogue from './pages/Catalogue';
import Overview from './pages/Overview';
import PayPalCheckout from './pages/PayPalCheckout';
import PolicyDecision from './pages/PolicyDecision';
import PrivacyPreview from './pages/PrivacyPreview';
import Recovery from './pages/Recovery';
import RogueAgent from './pages/RogueAgent';
import PurchaseRequest from './pages/PurchaseRequest';
import ReceiptVerification from './pages/ReceiptVerification';
import { useWorkflow, type PageId } from './state/workflow';

const NAV: { id: PageId; label: string; el: () => ReactElement }[] = [
  { id: 'overview', label: 'Overview', el: Overview },
  { id: 'rogue', label: 'Rogue Agent', el: RogueAgent },
  { id: 'catalogue', label: 'Product Catalogue', el: Catalogue },
  { id: 'request', label: 'Purchase Request', el: PurchaseRequest },
  { id: 'privacy', label: 'Privacy Preview', el: PrivacyPreview },
  { id: 'agent', label: 'Agent Verification', el: AgentVerification },
  { id: 'policy', label: 'Policy Decision', el: PolicyDecision },
  { id: 'approval', label: 'Approval', el: Approval },
  { id: 'checkout', label: 'PayPal Checkout', el: PayPalCheckout },
  { id: 'recovery', label: 'Recovery & Evidence', el: Recovery },
  { id: 'receipt', label: 'Receipt Verification', el: ReceiptVerification },
  { id: 'attack', label: 'Attack Lab', el: AttackLab },
];

export default function App() {
  const { page, go, health } = useWorkflow();
  const Current = NAV.find((n) => n.id === page)!.el;
  return (
    <div className="shell">
      <a className="skip" href="#main">Skip to content</a>
      <aside className="sidebar">
        <div className="brand">
          <svg className="logo" viewBox="0 0 40 40" aria-hidden="true">
            <path d="M20 3 34 8v11c0 9-6 15.5-14 18C12 34.500 6 28 6 19V8z" fill="#003087" />
            <path d="M20 3 34 8v11c0 9-6 15.5-14 18z" fill="#009cde" opacity=".85" />
            <path d="m13 20 5 5 9-10" fill="none" stroke="#fff" strokeWidth="3.200" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <div>
            <strong className="wordmark"><span className="wm-a">OutProvenance</span><span className="wm-b">Pay</span></strong>
            <div className="muted small">Safer AI-agent payments</div>
          </div>
        </div>
        <nav aria-label="Sections">
          <ul>
            {NAV.map((n, i) => (
              <li key={n.id}>
                <button className={page === n.id ? 'nav active' : 'nav'} aria-current={page === n.id ? 'page' : undefined} onClick={() => go(n.id)}>
                  <span className="num">{i + 1}</span>{n.label}
                </button>
              </li>
            ))}
          </ul>
        </nav>
        <div className="modes" aria-label="Integration modes">
          <Badge tone={health?.paypal_configured ? 'info' : 'warn'}>PayPal: {health ? (health.paypal_configured ? 'Sandbox' : 'setup required') : '…'}</Badge>
          <Badge tone={health?.ai_configured ? 'info' : 'mock'}>AI: {health ? (health.ai_configured ? 'external' : 'local fallback') : '…'}</Badge>
        </div>
      </aside>
      <main id="main" className="main" tabIndex={-1}>
        <Current />
        <footer className="foot muted small">
          Prototype for a hackathon. Sandbox only; not a certified or guaranteed-secure payment product. Signatures prove integrity, not truth.
        </footer>
      </main>
    </div>
  );
}
