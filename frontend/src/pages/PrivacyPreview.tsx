import { useState } from 'react';
import { api } from '../services/api';
import type { PrivacyPreview as Preview } from '../types/api';
import { Badge, Banner, Card, Empty, ErrorNote, Kv, PageTitle, Spinner } from '../components/ui';
import { useAction } from '../state/useAction';
import { useWorkflow } from '../state/workflow';

export default function PrivacyPreview() {
  const { requestText, setRequestText, go } = useWorkflow();
  const [preview, setPreview] = useState<Preview | null>(null);
  const act = useAction(api.privacyPreview);
  const empty = requestText.trim().length === 0;

  return (
    <>
      <PageTitle title="Privacy Preview" lead="Exactly what would be sent to an external AI provider, after redaction." />
      <Card>
        <label htmlFor="ptext">Text to check</label>
        <textarea id="ptext" rows={4} value={requestText} onChange={(e) => setRequestText(e.target.value)} />
        <div className="row">
          <button className="primary" disabled={empty || act.loading} onClick={async () => setPreview((await act.run(requestText)) ?? null)}>
            Preview redaction
          </button>
          <button onClick={() => go('request')}>Back to request</button>
        </div>
        {act.loading && <Spinner />}
        <ErrorNote error={act.error} />
      </Card>
      {!preview && !act.loading && <Empty title="Nothing previewed yet">Enter text above and press “Preview redaction”.</Empty>}
      {preview && (
        <Card title="What would be sent" actions={<Badge tone={preview.will_be_sent_externally ? 'warn' : 'ok'}>{preview.will_be_sent_externally ? 'Sent to external AI' : 'Stays on this server'}</Badge>}>
          <pre className="json" aria-label="Redacted text">{preview.redacted_text}</pre>
          <Kv items={[
            ['Destination', preview.destination],
            ['Emails redacted', preview.redaction_counts.email ?? 0],
            ['Phone numbers redacted', preview.redaction_counts.phone ?? 0],
            ['Card-like numbers redacted', preview.redaction_counts.card ?? 0],
          ]} />
          <Banner tone="warn" title="Limitation">{preview.limitation}</Banner>
        </Card>
      )}
    </>
  );
}
