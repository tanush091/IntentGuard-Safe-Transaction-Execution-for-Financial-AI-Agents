import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Load data with `fn` immediately and every `intervalMs` (0 = no polling). Returns
 * { data, error, loading, reload }. Errors stay inline; a stale response never overwrites a newer one.
 */
export function usePoll(fn, deps = [], intervalMs = 0) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const seq = useRef(0);

  const reload = useCallback(async () => {
    const mine = ++seq.current;
    try {
      const d = await fnRef.current();
      if (mine === seq.current) {
        setData(d);
        setError(null);
      }
    } catch (e) {
      if (mine === seq.current) setError(e);
    } finally {
      if (mine === seq.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    reload();
    if (!intervalMs) return undefined;
    const t = setInterval(() => {
      if (document.visibilityState !== 'hidden') reload();
    }, intervalMs);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, intervalMs]);

  return { data, error, loading, reload };
}
