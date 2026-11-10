import type { ReactNode } from 'react';
import type { ApiError } from '../services/api';

export type Tone = 'ok' | 'warn' | 'bad' | 'info' | 'mock' | 'neutral';

export function Badge({ tone = 'neutral', children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function Banner({ tone = 'info', title, children }: { tone?: Tone; title?: string; children?: ReactNode }) {
  return (
    <div className={`banner banner-${tone}`} role={tone === 'bad' ? 'alert' : 'status'}>
      {title && <strong>{title}</strong>}
      {children && <div>{children}</div>}
    </div>
  );
}

export function ErrorNote({ error }: { error: ApiError | null }) {
  if (!error) return null;
  return (
    <Banner tone="bad" title={error.status ? `Error ${error.status}: ${error.code}` : 'Error'}>
      {error.message}
    </Banner>
  );
}

export function Card({ title, subtitle, children, actions }: { title?: string; subtitle?: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="card">
      {(title || actions) && (
        <header className="card-head">
          <div>
            {title && <h3>{title}</h3>}
            {subtitle && <p className="muted">{subtitle}</p>}
          </div>
          {actions && <div className="row">{actions}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

export function Spinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <span className="spinner-wrap" role="status">
      <span className="spinner" aria-hidden="true" />
      <span>{label}</span>
    </span>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      {children && <p className="muted">{children}</p>}
    </div>
  );
}

export function JsonBlock({ value, label }: { value: unknown; label: string }) {
  return (
    <pre className="json" tabIndex={0} aria-label={label}>
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

export function Kv({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="kv">
      {items.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function PageTitle({ title, lead }: { title: string; lead: string }) {
  return (
    <div className="page-title">
      <h2>{title}</h2>
      <p className="muted">{lead}</p>
    </div>
  );
}

export function decisionTone(d: string): Tone {
  return d === 'ALLOW' ? 'ok' : d === 'REQUIRE_APPROVAL' ? 'warn' : 'bad';
}

export function stateTone(s: string): Tone {
  if (s === 'CAPTURED') return 'ok';
  if (s === 'FAILED') return 'bad';
  if (s === 'CAPTURE_UNCERTAIN') return 'warn';
  return 'info';
}

export function downloadJson(filename: string, value: unknown) {
  const blob = new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
