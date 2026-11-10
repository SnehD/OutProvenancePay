import type {
  AttackResult, Attempt, EvidenceDoc, EvidenceEvent, EvidenceVerification, Health, Intent, ManifestDoc, ManifestVerification, PolicyDecision, PolicyInfo, PrivacyPreview,
  Product, ProposeResponse, ReceiptDoc, ReceiptListItem, ReceiptVerification, RetryResponse, ScenarioMeta,
} from '../types/api';

export const API_BASE_URL: string = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '')
  ?? 'http://localhost:8000';

/** Error with the HTTP status and machine-readable code returned by the backend. */
export class ApiError extends Error {
  status: number;
  code: string;
  body: unknown;
  constructor(status: number, code: string, message: string, body: unknown) {
    super(message);
    this.status = status;
    this.code = code;
    this.body = body;
  }
}

async function request<T>(method: 'GET' | 'POST', path: string, body?: unknown, extraHeaders?: Record<string, string>): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: body === undefined && !extraHeaders ? undefined : { ...(body === undefined ? {} : { 'Content-Type': 'application/json' }), ...extraHeaders },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'NETWORK', `Cannot reach the backend at ${API_BASE_URL}. Is it running (and is CORS allowing this origin)?`, null);
  }
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!res.ok) {
    const d = (data ?? {}) as { error?: string; message?: string; detail?: unknown };
    const detail = typeof d.detail === 'string' ? d.detail : Array.isArray(d.detail) ? 'The request was not valid.' : undefined;
    throw new ApiError(res.status, d.error ?? `HTTP_${res.status}`, d.message ?? detail ?? `Request failed (HTTP ${res.status}).`, data);
  }
  return data as T;
}

const tx = (id: string) => `/api/transactions/${encodeURIComponent(id)}`;

export const api = {
  health: () => request<Health>('GET', '/api/health'),
  products: () => request<Product[]>('GET', '/api/products'),
  policies: () => request<PolicyInfo>('GET', '/api/policies'),
  evaluatePolicy: (product_id: string) => request<PolicyDecision>('POST', '/api/policies/evaluate', { product_id }),

  privacyPreview: (text: string) => request<PrivacyPreview>('POST', '/api/privacy/preview', { text }),
  propose: (text: string) => request<ProposeResponse>('POST', '/api/purchase/propose', { text }),

  manifest: (agentId: string) => request<ManifestDoc>('GET', `/api/agents/${encodeURIComponent(agentId)}/manifest`),
  verifyManifest: (agentId: string) => request<ManifestVerification>('POST', `/api/agents/${encodeURIComponent(agentId)}/verify`),

  createIntent: (agent_id: string, product_id: string) => request<Intent>('POST', '/api/transactions', { agent_id, product_id }),
  listIntents: () => request<Intent[]>('GET', '/api/transactions'),
  getIntent: (id: string) => request<Intent>('GET', tx(id)),
  approve: (id: string, approver: string, details_digest: string) =>
    request<Intent>('POST', `${tx(id)}/approve`, { approver, details_digest }),

  createOrder: (id: string) => request<Intent>('POST', `${tx(id)}/paypal/order`),
  paypalStatus: (id: string) => request<Intent>('GET', `${tx(id)}/paypal/status`),
  capture: (id: string) => request<Intent>('POST', `${tx(id)}/paypal/capture`),
  reconcile: (id: string) => request<Intent>('POST', `${tx(id)}/paypal/reconcile`),
  devReceipt: (id: string) => request<ReceiptDoc>('POST', `${tx(id)}/dev-receipt`),

  listReceipts: (intentId: string) => request<ReceiptListItem[]>('GET', `/api/receipts?intent_id=${encodeURIComponent(intentId)}`),
  getReceipt: (id: string) => request<ReceiptDoc>('GET', `/api/receipts/${encodeURIComponent(id)}`),
  verifyReceipt: (payload: Record<string, unknown>, signature_b64: string, key_id: string) =>
    request<ReceiptVerification>('POST', '/api/receipts/verify', { payload, signature_b64, key_id }),

  retry: (id: string, idempotencyKey: string) => request<RetryResponse>('POST', `${tx(id)}/paypal/retry`, undefined, { 'Idempotency-Key': idempotencyKey }),
  attempts: (id: string) => request<Attempt[]>('GET', `${tx(id)}/attempts`),
  evidence: (id: string) => request<EvidenceDoc>('GET', `${tx(id)}/evidence`),
  verifyEvidence: (events: EvidenceEvent[], expected_head_digest?: string) =>
    request<EvidenceVerification>('POST', '/api/evidence/verify', { events, ...(expected_head_digest ? { expected_head_digest } : {}) }),

  attackScenarios: () => request<{ scenarios: ScenarioMeta[]; sandbox_notice: string }>('GET', '/api/attack-lab/scenarios'),
  runScenario: (id: string) => request<AttackResult>('POST', `/api/attack-lab/run/${encodeURIComponent(id)}`),
};
