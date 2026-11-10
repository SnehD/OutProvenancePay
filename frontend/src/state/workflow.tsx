import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { api, ApiError } from '../services/api';
import type { Health, Intent, Product } from '../types/api';

export const AGENT_ID = 'agent-shopper-001';

export type PageId =
  | 'overview' | 'rogue' | 'catalogue' | 'request' | 'privacy' | 'agent' | 'policy' | 'approval' | 'checkout' | 'recovery' | 'receipt' | 'attack';

interface Workflow {
  health: Health | null;
  healthError: ApiError | null;
  reloadHealth: () => Promise<void>;
  products: Product[] | null;
  productsError: ApiError | null;
  selectedProductId: string | null;
  setSelectedProductId: (id: string | null) => void;
  requestText: string;
  setRequestText: (t: string) => void;
  intent: Intent | null;
  setIntent: (i: Intent | null) => void;
  refreshIntent: () => Promise<void>;
  sharedReceiptId: string | null;
  page: PageId;
  go: (p: PageId) => void;
}

const Ctx = createContext<Workflow | null>(null);

function safeGet(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}
function safeSet(key: string, value: string | null) {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* storage unavailable: the app still works, it just will not remember the last transaction */
  }
}

export function WorkflowProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState<ApiError | null>(null);
  const [products, setProducts] = useState<Product[] | null>(null);
  const [productsError, setProductsError] = useState<ApiError | null>(null);
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null);
  const [requestText, setRequestText] = useState('');
  const [intent, setIntentState] = useState<Intent | null>(null);
  const [page, setPage] = useState<PageId>('overview');
  const [sharedReceiptId, setSharedReceiptId] = useState<string | null>(null);

  const reloadHealth = useCallback(async () => {
    try {
      setHealth(await api.health());
      setHealthError(null);
    } catch (e) {
      setHealth(null);
      setHealthError(e instanceof ApiError ? e : new ApiError(0, 'UNKNOWN', String(e), null));
    }
  }, []);

  const setIntent = useCallback((i: Intent | null) => {
    setIntentState(i);
    safeSet('opp.intentId', i ? i.id : null);
  }, []);

  const intentIdRef = useRef<string | null>(null);
  useEffect(() => {
    intentIdRef.current = intent?.id ?? null;
  }, [intent]);

  const refreshIntent = useCallback(async () => {
    const id = intentIdRef.current;
    if (!id) return;
    setIntentState(await api.getIntent(id));
  }, []);

  useEffect(() => {
    void reloadHealth();
    api.products().then(setProducts).catch((e) => setProductsError(e instanceof ApiError ? e : new ApiError(0, 'UNKNOWN', String(e), null)));
    // Restore the last transaction. A PayPal redirect carries ?intent=... but that is only a pointer:
    // the status shown always comes from the backend, which asks PayPal's server API.
    const params = new URLSearchParams(window.location.search);
    const fromUrl = params.get('intent');
    const sharedReceipt = params.get('receipt');
    if (sharedReceipt) {
      // A scanned QR link: open the verifier. The receipt is fetched and verified by the backend, never trusted from the URL.
      setSharedReceiptId(sharedReceipt);
      setPage('receipt');
      window.history.replaceState({}, '', window.location.pathname);
    }
    const id = fromUrl ?? safeGet('opp.intentId');
    if (fromUrl) {
      setPage('checkout');
      window.history.replaceState({}, '', window.location.pathname);
    }
    if (id) api.getIntent(id).then(setIntentState).catch(() => safeSet('opp.intentId', null));
  }, [reloadHealth]);

  const value = useMemo<Workflow>(() => ({
    health, healthError, reloadHealth, products, productsError, selectedProductId, setSelectedProductId,
    requestText, setRequestText, intent, setIntent, refreshIntent, sharedReceiptId, page, go: setPage,
  }), [health, healthError, reloadHealth, products, productsError, selectedProductId, requestText, intent, setIntent, refreshIntent, sharedReceiptId, page]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useWorkflow(): Workflow {
  const v = useContext(Ctx);
  if (!v) throw new Error('useWorkflow must be used inside WorkflowProvider');
  return v;
}
