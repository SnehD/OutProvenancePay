export type Decision = 'ALLOW' | 'REQUIRE_APPROVAL' | 'DENY';

export interface Health {
  status: string;
  database: string;
  paypal: string;
  ai: string;
  paypal_configured: boolean;
  ai_configured: boolean;
  mode_notes: string[];
}

export interface Product {
  id: string;
  name: string;
  seller_name: string;
  category: string;
  price: string;
  currency: string;
  seller_approved: boolean;
}

export interface PolicyDecision {
  decision: Decision;
  reasons: string[];
  codes: string[];
  policy_version: string;
  product_id: string | null;
  product_name: string | null;
  seller_name: string | null;
  amount: string | null;
  currency: string | null;
}

export interface PolicyInfo {
  policy_version: string;
  rules: string[];
  approval_threshold: string;
  max_purchase: string;
  approved_sellers: string[];
}

export interface PrivacyPreview {
  redacted_text: string;
  redaction_counts: Record<string, number>;
  total_redactions: number;
  external_ai_configured: boolean;
  will_be_sent_externally: boolean;
  destination: string;
  limitation: string;
}

export interface AiSuggestion {
  source: 'local-fallback' | 'external-llm';
  label: string;
  proposal: { product_id: string; rationale: string } | null;
  accepted: boolean;
  notes: string[];
}

export interface ProposeResponse {
  privacy: PrivacyPreview;
  ai: AiSuggestion;
  policy: PolicyDecision | null;
  note: string;
}

export interface ManifestDoc {
  payload: {
    schema_version: string;
    agent_id: string;
    agent_version: string;
    capabilities: string[];
    allowed_transaction_categories: string[];
    issuer: string;
    key_id: string;
    issued_at: string;
  };
  signature_b64: string;
  key_id: string;
  algorithm: string;
  digest_sha256: string;
  issuer_public_key_b64: string;
}

export interface ManifestVerification {
  valid: boolean;
  reason: string;
  digest_sha256: string | null;
  key_id: string | null;
  agent_id: string;
  note: string;
}

export interface Intent {
  id: string;
  agent_id: string;
  state: string;
  product_id: string;
  product_name: string;
  seller_name: string;
  category: string;
  amount: string;
  currency: string;
  policy_version: string;
  policy_decision: Decision;
  details_digest: string;
  manifest_digest: string;
  internal_approval: { id: string; approver: string; expires_at: string; used: boolean } | null;
  paypal: { order_id: string | null; capture_id: string | null; status: string | null; approval_url: string | null };
  recovery_status?: string | null;
  failure_reason: string | null;
  receipt_id: string | null;
  created_at: string;
  updated_at: string;
  next_step: string;
}

export interface ReceiptDoc {
  payload: Record<string, unknown>;
  signature_b64: string;
  key_id: string;
  algorithm: string;
  digest_sha256: string;
  signer_public_key_b64: string;
  canonicalization: string;
}

export interface ReceiptVerification {
  valid: boolean;
  signature_valid: boolean;
  signature_reason: string;
  consistency_issues: string[];
  recomputed_digest_sha256: string | null;
  key_id: string;
  receipt_type: string | null;
  note: string;
}

export interface ReceiptListItem {
  id: string;
  intent_id: string;
  receipt_type: string;
  created_at: string;
}

export interface ScenarioMeta {
  id: string;
  title: string;
  mocked_paypal: boolean;
  defense: string;
}

export interface AttackCheck {
  check: string;
  ok: boolean;
  detail: string;
}

export interface AttackResult extends ScenarioMeta {
  result: 'PASS' | 'FAIL';
  reason: string;
  observed: Record<string, unknown>;
  checks: AttackCheck[];
  label: string;
  sandbox_notice: string;
}

export interface Attempt {
  id: string;
  operation: string;
  idempotency_key: string;
  client_key: string | null;
  paypal_order_id: string | null;
  paypal_capture_id: string | null;
  outcome: string;
  observed_status: string | null;
  detail: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface EvidencePayload {
  schema: string;
  event_id: string;
  intent_id: string;
  seq: number;
  event_type: string;
  source: 'PAYPAL_OBSERVED' | 'INTERNAL';
  recorded_at: string;
  prev_event_digest: string | null;
  refs: Record<string, string | null>;
  status_from: string | null;
  status_to: string | null;
  paypal_observation: { order_status: string | null; capture_status: string | null } | null;
  claim_basis: string;
  note: string | null;
}

export interface EvidenceEvent {
  payload: EvidencePayload;
  signature_b64: string;
  key_id: string;
  digest_sha256: string;
}

export interface EvidenceDoc {
  schema: string;
  profile_note: string;
  intent_id: string;
  head_digest: string | null;
  events: EvidenceEvent[];
}

export interface EvidenceVerification {
  valid: boolean;
  event_count: number;
  head_digest: string | null;
  events: { index: number; event_id: string | null; event_type: string | null; signature_valid: boolean; issues: string[] }[];
  issues: string[];
  note: string;
}

export interface RetryInfo { outcome: string; message: string; attempt_id: string; replay: boolean }
export type RetryResponse = Intent & { retry: RetryInfo };
