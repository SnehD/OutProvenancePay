import { useEffect, useState } from 'react';
import { api } from '../services/api';
import type { ManifestDoc, ManifestVerification } from '../types/api';
import { Badge, Banner, Card, ErrorNote, JsonBlock, Kv, PageTitle, Spinner } from '../components/ui';
import { useAction } from '../state/useAction';
import { AGENT_ID } from '../state/workflow';

export default function AgentVerification() {
  const [doc, setDoc] = useState<ManifestDoc | null>(null);
  const [result, setResult] = useState<ManifestVerification | null>(null);
  const load = useAction(api.manifest);
  const verify = useAction(api.verifyManifest);

  useEffect(() => {
    void load.run(AGENT_ID).then((d) => d && setDoc(d));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <>
      <PageTitle title="Agent Verification" lead="The backend re-checks the manifest's Ed25519 signature every time. Nothing is cached as 'valid'." />
      {load.loading && <Spinner />}
      <ErrorNote error={load.error} />
      {doc && (
        <Card title={`Manifest for ${doc.payload.agent_id}`} actions={<button className="primary" disabled={verify.loading} onClick={async () => setResult((await verify.run(AGENT_ID)) ?? null)}>Verify signature now</button>}>
          <JsonBlock value={doc.payload} label="Manifest payload" />
          <Kv items={[
            ['Algorithm', doc.algorithm],
            ['Key ID', <code key="k">{doc.key_id}</code>],
            ['SHA-256 of canonical payload', <code key="d">{doc.digest_sha256}</code>],
            ['Signature (base64)', <code key="s" className="wrap">{doc.signature_b64}</code>],
          ]} />
          {verify.loading && <Spinner label="Verifying…" />}
          <ErrorNote error={verify.error} />
          {result && (
            <Banner tone={result.valid ? 'ok' : 'bad'} title={result.valid ? 'Signature VALID' : 'Signature INVALID'}>
              {result.reason}
            </Banner>
          )}
        </Card>
      )}
      <Banner tone="info" title="What this proves">
        A valid signature proves the manifest is unchanged since it was signed by the trusted key. It does <Badge tone="warn">not</Badge> prove the claims are true or who the agent is in the real world. Purchases are blocked if verification fails (see Attack Lab).
      </Banner>
    </>
  );
}
