import { useEffect, useState } from 'react';
import { api, ApiError } from '../services/api';
import type { AttackResult, ScenarioMeta } from '../types/api';
import { Badge, Banner, Card, ErrorNote, PageTitle, Spinner } from '../components/ui';

export default function AttackLab() {
  const [scenarios, setScenarios] = useState<ScenarioMeta[] | null>(null);
  const [notice, setNotice] = useState('');
  const [loadError, setLoadError] = useState<ApiError | null>(null);
  const [results, setResults] = useState<Record<string, AttackResult>>({});
  const [running, setRunning] = useState<string | null>(null);
  const [runError, setRunError] = useState<ApiError | null>(null);

  useEffect(() => {
    api.attackScenarios().then((r) => { setScenarios(r.scenarios); setNotice(r.sandbox_notice); })
      .catch((e) => setLoadError(e instanceof ApiError ? e : new ApiError(0, 'UNKNOWN', String(e), null)));
  }, []);

  async function run(id: string) {
    setRunning(id);
    setRunError(null);
    try {
      const r = await api.runScenario(id);
      setResults((prev) => ({ ...prev, [id]: r }));
    } catch (e) {
      setRunError(e instanceof ApiError ? e : new ApiError(0, 'UNKNOWN', String(e), null));
    } finally {
      setRunning(null);
    }
  }
  async function runAll() {
    for (const s of scenarios ?? []) await run(s.id);
  }
  const done = Object.values(results);
  const passed = done.filter((r) => r.result === 'PASS').length;

  return (
    <>
      <PageTitle title="Attack Lab" lead="Real attacks executed against the real backend code. PASS appears only when the defense actually held." />
      {notice && <Banner tone="mock" title="Safe sandbox">{notice}</Banner>}
      <ErrorNote error={loadError} />
      <ErrorNote error={runError} />
      {!scenarios && !loadError && <Spinner />}
      {scenarios && (
        <div className="row">
          <button className="primary" disabled={running !== null} onClick={runAll}>Run all scenarios</button>
          {done.length > 0 && <Badge tone={passed === done.length ? 'ok' : 'bad'}>{passed}/{done.length} defenses held</Badge>}
        </div>
      )}
      {scenarios?.map((s, idx) => {
        const r = results[s.id];
        return (
          <Card key={s.id} title={`${idx + 1}. ${s.title}`} subtitle={s.defense}
            actions={
              <>
                {s.mocked_paypal && <Badge tone="mock">MOCKED PayPal</Badge>}
                {r && <Badge tone={r.result === 'PASS' ? 'ok' : 'bad'}>{r.result}</Badge>}
                <button disabled={running !== null} onClick={() => run(s.id)}>{running === s.id ? 'Running…' : 'Run'}</button>
              </>
            }>
            {running === s.id && <Spinner label="Executing attack…" />}
            {r && (
              <>
                <p>{r.reason}</p>
                <p className="muted">{r.label}</p>
                <ul className="checks">
                  {r.checks.map((c) => (
                    <li key={c.check}><Badge tone={c.ok ? 'ok' : 'bad'}>{c.ok ? 'ok' : 'FAILED'}</Badge> {c.check} <span className="muted">— {c.detail}</span></li>
                  ))}
                </ul>
                <details>
                  <summary>Observed result</summary>
                  <pre className="json">{JSON.stringify(r.observed, null, 2)}</pre>
                </details>
              </>
            )}
          </Card>
        );
      })}
    </>
  );
}
