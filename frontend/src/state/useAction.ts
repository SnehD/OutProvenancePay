import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../services/api';

/** Wraps an async API call with loading + error state. `run` is stable across renders. */
export function useAction<A extends unknown[], R>(fn: (...args: A) => Promise<R>) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const fnRef = useRef(fn);
  useEffect(() => {
    fnRef.current = fn;
  });

  const run = useCallback(async (...args: A): Promise<R | undefined> => {
    setLoading(true);
    setError(null);
    try {
      return await fnRef.current(...args);
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, 'UNKNOWN', e instanceof Error ? e.message : String(e), null));
      return undefined;
    } finally {
      setLoading(false);
    }
  }, []);

  const reset = useCallback(() => setError(null), []);
  return { run, loading, error, reset };
}
