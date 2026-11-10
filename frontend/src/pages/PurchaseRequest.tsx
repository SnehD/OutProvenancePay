import { useState } from 'react';
import { api } from '../services/api';
import type { ProposeResponse } from '../types/api';
import { Badge, Banner, Card, ErrorNote, PageTitle, Spinner, decisionTone } from '../components/ui';
import { useAction } from '../state/useAction';
import { useWorkflow } from '../state/workflow';

const MAX = 2000;

export default function PurchaseRequest() {
  const { requestText, setRequestText, setSelectedProductId, go } = useWorkflow();
  const [result, setResult] = useState<ProposeResponse | null>(null);
  const propose = useAction(api.propose);
  const empty = requestText.trim().length === 0;
  const tooLong = requestText.length > MAX;

  return (
    <>
      <PageTitle title="Purchase Request" lead="Describe what the agent should buy. The assistant only suggests a catalogue product; the backend decides everything else." />
      <Card>
        <label htmlFor="req">Purchase request</label>
        <textarea id="req" rows={5} value={requestText} onChange={(e) => setRequestText(e.target.value)}
          placeholder="e.g. I need a mechanical keyboard. Reach me at jane@example.com" aria-describedby="req-help" />
        <p id="req-help" className="muted">{requestText.length}/{MAX} characters. Emails, phone numbers and card-like numbers are redacted before any external AI call.</p>
        {tooLong && <Banner tone="bad">Request is too long ({requestText.length}/{MAX}).</Banner>}
        <div className="row">
          <button className="primary" disabled={empty || tooLong || propose.loading} onClick={async () => setResult((await propose.run(requestText)) ?? null)}>
            Find product
          </button>
          <button onClick={() => go('privacy')} disabled={empty}>Preview what leaves this server</button>
        </div>
        {propose.loading && <Spinner label="Asking assistant…" />}
        <ErrorNote error={propose.error} />
      </Card>

      {result && (
        <Card title="Assistant suggestion" actions={<Badge tone={result.ai.source === 'local-fallback' ? 'mock' : 'info'}>{result.ai.source}</Badge>}>
          <p className="muted">{result.ai.label}</p>
          {result.ai.proposal ? (
            <>
              <p>Suggested product ID: <code>{result.ai.proposal.product_id}</code> — {result.ai.proposal.rationale}</p>
              {result.policy && (
                <p>Backend policy for it: <Badge tone={decisionTone(result.policy.decision)}>{result.policy.decision}</Badge> {result.policy.amount} {result.policy.currency} from {result.policy.seller_name}</p>
              )}
              <div className="row">
                <button className="primary" onClick={() => { setSelectedProductId(result.ai.proposal!.product_id); go('policy'); }}>
                  Use this product
                </button>
              </div>
            </>
          ) : (
            <Banner tone="warn" title="No usable suggestion">{result.ai.notes.join(' ') || 'Pick a product from the catalogue instead.'}</Banner>
          )}
          <p className="muted">{result.note}</p>
        </Card>
      )}
    </>
  );
}
