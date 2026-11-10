import { api } from '../services/api';
import type { Intent } from '../types/api';
import { Badge, Banner, Card, Empty, ErrorNote, Kv, PageTitle, Spinner, stateTone } from '../components/ui';
import { useAction } from '../state/useAction';
import { useWorkflow } from '../state/workflow';

export default function PayPalCheckout() {
  const { intent, setIntent, health, go } = useWorkflow();
  const order = useAction(api.createOrder);
  const status = useAction(api.paypalStatus);
  const capture = useAction(api.capture);
  const reconcile = useAction(api.reconcile);
  const dev = useAction(api.devReceipt);

  if (!intent) {
    return (
      <>
        <PageTitle title="PayPal Checkout" lead="Sandbox order creation and capture, done by the backend." />
        <Empty title="No transaction yet">Create one on the Policy Decision page.</Empty>
      </>
    );
  }

  const configured = health?.paypal_configured ?? false;
  const busy = order.loading || status.loading || capture.loading || reconcile.loading || dev.loading;
  async function step(fn: (id: string) => Promise<Intent | undefined>) {
    const updated = await fn(intent!.id);
    if (updated) setIntent(updated);
    else {
      // A failed step may still have changed server state (e.g. UNCERTAIN): re-read the truth.
      try { setIntent(await api.getIntent(intent!.id)); } catch { /* keep what we have */ }
    }
  }
  const s = intent.state;
  const errors = [order.error, status.error, capture.error, reconcile.error, dev.error];

  return (
    <>
      <PageTitle title="PayPal Checkout" lead="Sandbox only. A payment counts only when PayPal's server API confirms the capture." />
      {!configured && (
        <Banner tone="warn" title="PayPal Sandbox setup required">
          No credentials are configured on the backend, so no order can be created and no payment can happen. Add PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET to backend/.env and restart (see README).
        </Banner>
      )}
      <Card title="Transaction" actions={<Badge tone={stateTone(s)}>{s}</Badge>}>
        <Kv items={[
          ['Product', `${intent.product_name} (${intent.seller_name})`],
          ['Amount (from trusted intent)', `${intent.amount} ${intent.currency}`],
          ['PayPal order', intent.paypal.order_id ?? '—'],
          ['PayPal order status', intent.paypal.status ?? '—'],
          ['PayPal capture ID', intent.paypal.capture_id ?? '—'],
        ]} />
        <p className="muted">Next: {intent.next_step}</p>
        {intent.failure_reason && <Banner tone="warn" title="Note">{intent.failure_reason}</Banner>}
      </Card>

      {s === 'CAPTURED' && <Banner tone="ok" title="Payment confirmed by PayPal Sandbox">The backend read a COMPLETED capture from PayPal's API. A signed receipt was issued.</Banner>}
      {s === 'CAPTURE_UNCERTAIN' && (
        <Banner tone="warn" title="Payment status is UNCERTAIN">
          The capture result is unknown. Do not pay again. Use “Reconcile with PayPal” to learn what actually happened.
        </Banner>
      )}

      <Card title="Actions">
        <div className="row">
          <button className="primary" disabled={busy || !configured || s !== 'READY_FOR_PAYMENT'} onClick={() => step(order.run)}>
            1. Create PayPal Sandbox order
          </button>
          {intent.paypal.approval_url && (
            <a className="button" href={intent.paypal.approval_url} target="_blank" rel="noopener noreferrer">
              2. Buyer approves at PayPal ↗
            </a>
          )}
          <button disabled={busy || !configured || !intent.paypal.order_id} onClick={() => step(status.run)}>Check PayPal status</button>
          <button className="primary" disabled={busy || !configured || s !== 'ORDER_CREATED'} onClick={() => step(capture.run)}>
            3. Capture payment
          </button>
          <button disabled={busy || !configured || s !== 'CAPTURE_UNCERTAIN'} onClick={() => step(reconcile.run)}>Reconcile with PayPal</button>
        </div>
        {busy && <Spinner label="Working with the backend…" />}
        {errors.map((e, i) => <ErrorNote key={i} error={e} />)}
        <p className="muted">Buyer approval (step 2) happens on PayPal's site with a Sandbox buyer account. Returning to this page is not proof of payment; step 3 re-checks everything with PayPal.</p>
      </Card>

      <Card title="Development receipt (no payment)" subtitle="For demos without PayPal credentials. Clearly labelled; claims nothing was paid.">
        <div className="row">
          <button disabled={busy || !['READY_FOR_PAYMENT', 'ORDER_CREATED'].includes(s)} onClick={async () => { const r = await dev.run(intent.id); if (r) go('receipt'); }}>
            Issue development receipt
          </button>
          {intent.receipt_id && <button onClick={() => go('receipt')}>View payment receipt</button>}
        </div>
      </Card>
    </>
  );
}
