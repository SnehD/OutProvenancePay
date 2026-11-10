import { useCallback, useEffect, useState } from 'react';
import { api } from '../services/api';
import type { Attempt, EvidenceDoc, EvidenceEvent, EvidenceVerification, RetryResponse } from '../types/api';
import { Badge, Banner, Card, Empty, ErrorNote, PageTitle, Spinner, downloadJson, stateTone } from '../components/ui';
import type { Tone } from '../components/ui';
import { useAction } from '../state/useAction';
import { useWorkflow } from '../state/workflow';

const outcomeTone = (o: string): Tone =>
  o === 'SUCCEEDED' || o === 'RECONCILED' ? 'ok' : o === 'REUSED' ? 'info' : o === 'OUTCOME_UNKNOWN' ? 'warn' : o === 'REJECTED' ? 'bad' : 'neutral';

function newKey(): string {
  return `agent-retry-${Math.random().toString(36).slice(2, 10)}${Date.now().toString(36)}`;
}

export default function Recovery() {
  const { intent, refreshIntent } = useWorkflow();
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [doc, setDoc] = useState<EvidenceDoc | null>(null);
  const [shown, setShown] = useState<EvidenceEvent[]>([]);
  const [tampered, setTampered] = useState(false);
  const [result, setResult] = useState<EvidenceVerification | null>(null);
  const [retryResult, setRetryResult] = useState<RetryResponse | null>(null);
  const [retryKey, setRetryKey] = useState(newKey);
  const load = useAction(async (id: string) => {
    const [a, d] = await Promise.all([api.attempts(id), api.evidence(id)]);
    setAttempts(a);
    setDoc(d);
    setShown(d.events);
    setTampered(false);
    setResult(null);
  });
  const verify = useAction(api.verifyEvidence);
  const retry = useAction(api.retry);
  const intentId = intent?.id;
  const { run: runLoad } = load;

  const reload = useCallback(() => { if (intentId) void runLoad(intentId); }, [intentId, runLoad]);
  useEffect(() => { reload(); }, [reload, intent?.state]);

  async function doRetry() {
    if (!intent) return;
    const r = await retry.run(intent.id, retryKey);
    if (r) setRetryResult(r);
    await refreshIntent();
    reload();
  }
  function tamper() {
    if (shown.length < 2) return;
    const copy: EvidenceEvent[] = JSON.parse(JSON.stringify(shown));
    copy[1].payload.status_to = 'FAILED';
    setShown(copy);
    setTampered(true);
    setResult(null);
  }

  if (!intent) {
    return (
      <>
        <PageTitle title="Recovery & Evidence" lead="What happens when a payment response is lost, and the signed trail that shows it." />
        <Empty title="No transaction yet">Run the demo or create a transaction first.</Empty>
      </>
    );
  }

  const pending = intent.recovery_status === 'PENDING_RECONCILIATION';
  return (
    <>
      <PageTitle title="Recovery & Evidence" lead="If a payment response is lost, the agent can retry safely: the backend finds the original payment and never pays twice." />

      {pending && (
        <Banner tone="warn" title="PENDING RECONCILIATION: not confirmed, not failed">
          PayPal may or may not have taken the payment. No receipt exists and none will until PayPal's own data confirms it. Use the agent retry below or Reconcile on the PayPal Checkout page.
        </Banner>
      )}
      {intent.state === 'CAPTURED' && <Banner tone="ok" title="Confirmed by PayPal">A COMPLETED capture was reported by PayPal's server API.</Banner>}

      <Card title="Transaction" actions={<Badge tone={stateTone(intent.state)}>{intent.state}</Badge>}>
        <p className="muted small"><code>{intent.id}</code> · {intent.product_name} · {intent.amount} {intent.currency}</p>
        <div className="row">
          <label htmlFor="rk" className="sr-only">Idempotency-Key</label>
          <input id="rk" value={retryKey} onChange={(e) => setRetryKey(e.target.value)} maxLength={100} aria-label="Idempotency-Key" style={{ maxWidth: 340 }} />
          <button className="primary" onClick={() => void doRetry()} disabled={retry.loading || retryKey.length < 8}>Agent retry</button>
          <button onClick={() => setRetryKey(newKey())}>New key</button>
        </div>
        <p className="muted small">Same key = a replay of the same request. The retry always works from the original approved transaction, never from what the retry claims.</p>
        {retry.loading && <Spinner label="Asking the backend…" />}
        <ErrorNote error={retry.error} />
        {retryResult && (
          <Banner tone={retryResult.retry.outcome === 'PENDING_RECONCILIATION' ? 'warn' : 'ok'} title={`Retry result: ${retryResult.retry.outcome}${retryResult.retry.replay ? ' (replay)' : ''}`}>
            {retryResult.retry.message}
          </Banner>
        )}
      </Card>

      <Card title="Execution attempts" subtitle="Each attempt with the idempotency key that was sent to PayPal." actions={<button onClick={reload}>Refresh</button>}>
        {load.loading && <Spinner />}
        <ErrorNote error={load.error} />
        {attempts.length === 0 && !load.loading && <Empty title="No attempts yet">Attempts appear once an order or capture is tried.</Empty>}
        {attempts.length > 0 && (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Operation</th><th>Outcome</th><th>Idempotency key</th><th>PayPal refs</th><th>Started</th></tr></thead>
              <tbody>
                {attempts.map((a) => (
                  <tr key={a.id}>
                    <td>{a.operation}</td>
                    <td><Badge tone={outcomeTone(a.outcome)}>{a.outcome}</Badge></td>
                    <td><code className="wrap">{a.idempotency_key}</code></td>
                    <td className="small">{a.paypal_order_id ?? '—'}{a.paypal_capture_id ? ` / ${a.paypal_capture_id}` : ''}</td>
                    <td className="small">{new Date(a.started_at).toLocaleTimeString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Evidence trail" subtitle="TRACE-inspired, signed and hash-linked. Not a conformant TRACE or SCITT implementation."
        actions={
          <>
            <button className="primary" disabled={shown.length === 0 || verify.loading}
              onClick={async () => setResult((await verify.run(shown)) ?? null)}>Verify chain</button>
            <button onClick={tamper} disabled={shown.length < 2 || tampered}>Demo: tamper with an event</button>
            <button onClick={() => doc && downloadJson('evidence.json', doc)} disabled={!doc}>Download JSON</button>
          </>
        }>
        {tampered && <Banner tone="mock" title="Local copy edited">Event 2 now says status FAILED. Verify to see the backend reject it. Reload to restore.</Banner>}
        {result && (
          <Banner tone={result.valid ? 'ok' : 'bad'} title={result.valid ? `VALID: ${result.event_count} events verified` : 'INVALID: this evidence cannot be trusted'}>
            {result.valid ? 'Signatures, order and hash links all check out.' : (
              <ul>{[...result.issues, ...result.events.flatMap((e) => e.issues.map((i) => `#${e.index} ${e.event_type ?? ''}: ${i}`))].slice(0, 6).map((i) => <li key={i}>{i}</li>)}</ul>
            )}
          </Banner>
        )}
        <ErrorNote error={verify.error} />
        <ol className="timeline">
          {shown.map((e, i) => {
            const p = e.payload;
            const bad = result?.events[i]?.issues.length;
            return (
              <li key={p.event_id} className={bad ? 'tl-bad' : result?.valid ? 'tl-ok' : ''}>
                <span className="tl-dot" aria-hidden="true">{p.seq}</span>
                <div>
                  <strong>{p.event_type}</strong>{' '}
                  <Badge tone={p.source === 'PAYPAL_OBSERVED' ? 'info' : 'neutral'}>{p.source === 'PAYPAL_OBSERVED' ? 'OBSERVED AT PAYPAL' : 'INTERNAL'}</Badge>
                  {p.status_to && <span className="muted small"> {p.status_from ? `${p.status_from} → ` : ''}{p.status_to}</span>}
                  {p.paypal_observation && <div className="small">PayPal said: order <code>{p.paypal_observation.order_status}</code>{p.paypal_observation.capture_status ? <>, capture <code>{p.paypal_observation.capture_status}</code></> : null}</div>}
                  {p.note && <div className="muted small">{p.note}</div>}
                  <div className="muted small">{new Date(p.recorded_at).toLocaleTimeString()} · <code>{e.digest_sha256.slice(0, 12)}…</code></div>
                </div>
              </li>
            );
          })}
        </ol>
        <p className="muted small">{doc?.profile_note}</p>
      </Card>
    </>
  );
}
