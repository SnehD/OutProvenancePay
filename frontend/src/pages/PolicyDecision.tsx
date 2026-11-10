import { useEffect, useState } from 'react';
import { api, ApiError } from '../services/api';
import type { PolicyDecision as Decision, PolicyInfo } from '../types/api';
import { Badge, Banner, Card, Empty, ErrorNote, Kv, PageTitle, Spinner, decisionTone } from '../components/ui';
import { useAction } from '../state/useAction';
import { AGENT_ID, useWorkflow } from '../state/workflow';

export default function PolicyDecision() {
  const { products, selectedProductId, setSelectedProductId, setIntent, go } = useWorkflow();
  const [info, setInfo] = useState<PolicyInfo | null>(null);
  const [decision, setDecision] = useState<Decision | null>(null);
  const [denied, setDenied] = useState<Decision | null>(null);
  const evaluate = useAction(api.evaluatePolicy);
  const create = useAction(api.createIntent);

  useEffect(() => {
    api.policies().then(setInfo).catch(() => setInfo(null));
  }, []);
  useEffect(() => {
    setDecision(null);
    setDenied(null);
  }, [selectedProductId]);

  const product = products?.find((p) => p.id === selectedProductId);

  async function createIntent() {
    if (!selectedProductId) return;
    setDenied(null);
    const intent = await create.run(AGENT_ID, selectedProductId);
    if (intent) {
      setIntent(intent);
      go(intent.state === 'AWAITING_INTERNAL_APPROVAL' ? 'approval' : 'checkout');
    }
  }
  const deniedBody = create.error instanceof ApiError ? (create.error.body as { policy?: Decision } | null)?.policy : undefined;

  return (
    <>
      <PageTitle title="Policy Decision" lead="Deterministic server-side rules. The decision is never computed in the browser." />
      {info && (
        <Card title={`Policy ${info.policy_version}`}>
          <ul>{info.rules.map((r) => <li key={r}>{r}</li>)}</ul>
        </Card>
      )}
      <Card title="Selected product">
        <label htmlFor="prod">Product</label>
        <select id="prod" value={selectedProductId ?? ''} onChange={(e) => setSelectedProductId(e.target.value || null)}>
          <option value="">— choose a product —</option>
          {products?.map((p) => <option key={p.id} value={p.id}>{p.name} — {p.price} {p.currency}</option>)}
        </select>
        {!product && <Empty title="No product selected">Pick one here or from the Catalogue.</Empty>}
        {product && (
          <>
            <Kv items={[['Seller', product.seller_name], ['Trusted price', `${product.price} ${product.currency}`], ['Category', product.category]]} />
            <div className="row">
              <button disabled={evaluate.loading} onClick={async () => setDecision((await evaluate.run(product.id)) ?? null)}>Evaluate policy</button>
              <button className="primary" disabled={create.loading} onClick={createIntent}>Create transaction intent</button>
            </div>
          </>
        )}
        {(evaluate.loading || create.loading) && <Spinner />}
        <ErrorNote error={evaluate.error} />
        {create.error && !deniedBody && <ErrorNote error={create.error} />}
      </Card>
      {(decision ?? deniedBody ?? denied) && (() => {
        const d = (deniedBody ?? decision ?? denied)!;
        return (
          <Card title="Decision" actions={<Badge tone={decisionTone(d.decision)}>{d.decision}</Badge>}>
            {deniedBody && <Banner tone="bad" title="Transaction refused by the backend">{create.error?.message}</Banner>}
            <ul>{d.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            <Kv items={[['Amount (trusted)', `${d.amount ?? '—'} ${d.currency ?? ''}`], ['Seller (trusted)', d.seller_name ?? '—'], ['Policy version', d.policy_version], ['Codes', d.codes.join(', ')]]} />
          </Card>
        );
      })()}
    </>
  );
}
