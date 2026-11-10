import { useEffect, useRef, useState } from 'react';
import QRCode from 'qrcode';
import { api } from '../services/api';
import type { ReceiptDoc, ReceiptVerification as Result } from '../types/api';
import { Badge, Banner, Card, ErrorNote, Kv, PageTitle, Spinner, downloadJson } from '../components/ui';
import { useAction } from '../state/useAction';
import { useWorkflow } from '../state/workflow';

function parseDoc(text: string): { doc?: { payload: Record<string, unknown>; signature_b64: string; key_id: string }; error?: string } {
  try {
    const v = JSON.parse(text) as Partial<ReceiptDoc>;
    if (!v || typeof v !== 'object' || typeof v.payload !== 'object' || v.payload === null || typeof v.signature_b64 !== 'string' || typeof v.key_id !== 'string') {
      return { error: 'Expected JSON with "payload" (object), "signature_b64" and "key_id".' };
    }
    return { doc: { payload: v.payload, signature_b64: v.signature_b64, key_id: v.key_id } };
  } catch {
    return { error: 'That is not valid JSON.' };
  }
}

export default function ReceiptVerification() {
  const { intent, sharedReceiptId } = useWorkflow();
  const [receiptId, setReceiptId] = useState<string | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const autoRan = useRef(false);
  const [text, setText] = useState('');
  const [result, setResult] = useState<Result | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const load = useAction(async (intentId: string) => {
    const list = await api.listReceipts(intentId);
    if (list.length === 0) throw new Error('This transaction has no receipt yet.');
    setReceiptId(list[0].id);
    return api.getReceipt(list[0].id);
  });
  const verify = useAction(api.verifyReceipt);

  async function loadCurrent() {
    if (!intent) return;
    const doc = await load.run(intent.id);
    if (doc) { setText(JSON.stringify(doc, null, 2)); setResult(null); setLocalError(null); }
  }
  async function runVerify() {
    const { doc, error } = parseDoc(text);
    if (!doc) { setLocalError(error ?? 'Invalid input.'); return; }
    setLocalError(null);
    setResult((await verify.run(doc.payload, doc.signature_b64, doc.key_id)) ?? null);
  }
  function demoTamper() {
    const { doc } = parseDoc(text);
    if (!doc) { setLocalError('Load a receipt first.'); return; }
    const full = JSON.parse(text) as Record<string, unknown>;
    (full.payload as Record<string, unknown>).amount = '0.01';
    setText(JSON.stringify(full, null, 2));
    setResult(null);
  }
  useEffect(() => {
    if (!receiptId) { setQr(null); return; }
    const link = `${window.location.origin}/?receipt=${encodeURIComponent(receiptId)}`;
    QRCode.toDataURL(link, { width: 220, margin: 1, color: { dark: '#003087', light: '#ffffff' } }).then(setQr).catch(() => setQr(null));
  }, [receiptId]);

  useEffect(() => {
    // Opened from a scanned QR: load that receipt and verify it straight away.
    if (!sharedReceiptId || autoRan.current) return;
    autoRan.current = true;
    (async () => {
      try {
        const doc = await api.getReceipt(sharedReceiptId);
        setReceiptId(sharedReceiptId);
        setText(JSON.stringify(doc, null, 2));
        setResult(await api.verifyReceipt(doc.payload, doc.signature_b64, doc.key_id));
      } catch {
        setLocalError('That receipt link could not be loaded or does not exist.');
      }
    })();
  }, [sharedReceiptId]);

  const parsed = text.trim() ? parseDoc(text) : null;

  return (
    <>
      <PageTitle title="Receipt Verification" lead="The backend recomputes the digest and checks the signature from exactly what you submit. No stored 'valid' flag is trusted." />
      <Card title="Receipt JSON" actions={
        <>
          <button onClick={loadCurrent} disabled={!intent || load.loading}>Load receipt for current transaction</button>
          <button onClick={() => parsed?.doc && downloadJson('receipt.json', JSON.parse(text))} disabled={!parsed?.doc}>Download JSON</button>
        </>
      }>
        {!intent && <p className="muted">No current transaction. You can still paste any receipt JSON below.</p>}
        <label htmlFor="rj">Paste or edit receipt (payload, signature_b64, key_id)</label>
        <textarea id="rj" rows={14} className="mono" value={text} onChange={(e) => { setText(e.target.value); setResult(null); }} spellCheck={false} />
        <div className="row">
          <button className="primary" disabled={!text.trim() || verify.loading} onClick={runVerify}>Verify receipt</button>
          <button onClick={demoTamper} disabled={!text.trim()}>Demo: change amount to 0.01</button>
        </div>
        {(load.loading || verify.loading) && <Spinner />}
        <ErrorNote error={load.error} />
        <ErrorNote error={verify.error} />
        {localError && <Banner tone="bad">{localError}</Banner>}
      </Card>
      {result && (
        <div className={`verdict ${result.valid ? 'verdict-ok' : 'verdict-bad'}`} role="status">
          <span aria-hidden="true">{result.valid ? '✓' : '✕'}</span> {result.valid ? 'Receipt is authentic' : 'Receipt is NOT valid'}
        </div>
      )}
      {qr && (
        <Card title="Share this receipt" subtitle="Scan to open the verifier on another device. The backend re-checks it; the link itself proves nothing.">
          <div className="qr-row">
            <img src={qr} alt="QR code linking to this receipt's verification page" width={220} height={220} />
            <p className="muted small">Same Wi-Fi only for the demo: the link points at this page's address. To scan from a phone, open this app via your computer's network address instead of localhost (start Vite with <code>--host</code> and add that origin to <code>OPP_CORS_ORIGINS</code>).</p>
          </div>
        </Card>
      )}
      {result && (
        <Card title="Verification result" actions={<Badge tone={result.valid ? 'ok' : 'bad'}>{result.valid ? 'VALID' : 'INVALID'}</Badge>}>
          <Kv items={[
            ['Signature', result.signature_valid ? 'valid' : 'INVALID'],
            ['Reason', result.signature_reason],
            ['Receipt type', result.receipt_type ?? '—'],
            ['Recomputed SHA-256', <code key="h" className="wrap">{result.recomputed_digest_sha256 ?? '—'}</code>],
            ['Key ID', <code key="k">{result.key_id}</code>],
          ]} />
          {result.consistency_issues.length > 0 && <Banner tone="bad" title="Consistency problems"><ul>{result.consistency_issues.map((i) => <li key={i}>{i}</li>)}</ul></Banner>}
          {result.receipt_type === 'DEV_TEST_NO_PAYMENT' && <Banner tone="mock" title="Development receipt">This receipt claims no payment occurred.</Banner>}
          <p className="muted">{result.note}</p>
        </Card>
      )}
    </>
  );
}
