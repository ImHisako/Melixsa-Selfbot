import { useCallback, useEffect, useRef, useState } from 'react';
import { desktop, initialSnapshot, request } from '../lib/bridge';
import type { SettingsPatch } from '../types';

export function useMelixsa() {
  const [data, setData] = useState(initialSnapshot);
  const [loading, setLoading] = useState(desktop);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ text: string; error: boolean } | null>(null);
  const working = useRef(false);
  const mounted = useRef(true);
  const dismiss = useCallback(() => setNotice(null), []);

  const act = useCallback(async (method: string, params: object = {}, success?: string) => {
    if (working.current) return false;
    working.current = true;
    setBusy(true);
    try {
      const next = await request(method, params);
      if (mounted.current) {
        setData(next);
        if (success) setNotice({ text: success, error: false });
      }
      return true;
    } catch (error) {
      if (mounted.current) setNotice({ text: String(error instanceof Error ? error.message : error), error: true });
      return false;
    } finally {
      working.current = false;
      if (mounted.current) setBusy(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      if (!working.current && desktop) {
        try {
          const next = await request('snapshot');
          if (!stopped) setData(next);
        } catch (error) {
          if (!stopped) setNotice({ text: String(error), error: true });
        } finally {
          if (!stopped) setLoading(false);
        }
      }
      if (!stopped) timer = setTimeout(poll, 3000);
    }
    void poll();
    return () => { stopped = true; mounted.current = false; clearTimeout(timer); };
  }, []);

  useEffect(() => {
    if (!notice || notice.error) return;
    const timer = setTimeout(dismiss, 4500);
    return () => clearTimeout(timer);
  }, [notice, dismiss]);

  const save = useCallback((patch: SettingsPatch) => act('update_settings', patch, 'Modifiche salvate. Tutto aggiornato.'), [act]);
  return { data, loading, busy, notice, dismiss, act, save };
}
