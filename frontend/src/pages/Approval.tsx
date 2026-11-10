import { useState } from 'react';
import { api } from '../services/api';
import { Badge, Banner, Card, Empty, ErrorNote, Kv, PageTitle, Spinner, decisionTone } from '../components/ui';
import { useAction } from '../state/useAction';
import { useWorkflow } from '../state/workflow';

export default function Approval() {
  const { intent, setIntent, go } = useWorkflow();
  const [approver, setApprover] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const approve = useAction(api.approve);

  if (!intent) {
    return (
      <>
        <PageTitle title="Internal Approval" lead="A human explicitly approves the exact transaction." />
        <Empty title="No transaction yet">Create a transaction intent on the Policy Decision page first.</Empty>
      </>
    );
  }

  const needs = intent.policy_decision === 'REQUIRE_APPROVAL';
  const awaiting = intent.state === 'AWAITING_INTERNAL_APPROVAL';
  const a = intent.internal_approval;

  async function submit() {
    if (!intent) return;
    const updated = await approve.run(intent.id, approver.trim(), intent.details_digest);
    if (updated) setIntent(updated);
  }

  return (
    <>
      <PageTitle title="Internal Approval" lead="This is OUR human approval. PayPal's buyer approval is a separate step at PayPal." />
      <Card title="Transaction to approve" actions={<Badge tone={decisionTone(intent.policy_decision)}>{intent.policy_decision}</Badge>}>
        <Kv items={[
          ['Transaction ID', <code key="i">{intent.id}</code>],
          ['Product', intent.product_name], ['Seller', intent.seller_name],
          ['Amount', `${intent.amount} ${intent.currency}`], ['Policy version', intent.policy_version],
          ['Bound details digest', <code key="d" className="wrap">{intent.details_digest}</code>],
        ]} />
      </Card>

      {!needs && <Banner tone="ok" title="No internal approval required">This purchase is within the auto-allow limit. Continue to PayPal Checkout.</Banner>}
      {needs && awaiting && (
        <Card title="Approve this exact transaction">
          <p className="muted">Approval is bound to the digest above, expires, and works once. If the product, seller, amount or policy changes, it becomes invalid.</p>
          <label htmlFor="who">Approver name</label>
          <input id="who" value={approver} maxLength={120} onChange={(e) => setApprover(e.target.value)} />
          <label className="check">
            <input type="checkbox" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
            I have reviewed the product, seller and amount above and approve this purchase.
          </label>
          <div className="row">
            <button className="primary" disabled={!approver.trim() || !confirmed || approve.loading} onClick={submit}>Approve transaction</button>
          </div>
          {approve.loading && <Spinner />}
          <ErrorNote error={approve.error} />
        </Card>
      )}
      {needs && !awaiting && a && (
        <Banner tone={a.used ? 'info' : 'ok'} title={a.used ? 'Approval already used' : 'Approved'}>
          By {a.approver}. Expires {new Date(a.expires_at).toLocaleString()}. {a.used ? 'It has been consumed by a PayPal order (one-time use).' : 'Not yet used.'}
        </Banner>
      )}
      <div className="row"><button onClick={() => go('checkout')} disabled={needs && awaiting}>Continue to PayPal Checkout</button></div>
    </>
  );
}
