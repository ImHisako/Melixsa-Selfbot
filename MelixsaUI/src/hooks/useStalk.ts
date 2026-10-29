import { useCallback, useEffect, useRef, useState } from 'react';
import { desktop, request } from '../lib/bridge';
import type { Connection, StalkLogs, StalkOverview } from '../types';

const empty: StalkOverview = { users: [], active_count: 0, log_bytes: 0 };
const message = (error: unknown) => String(error instanceof Error ? error.message : error);

export function useStalk(connection: Connection) {
  const [overview, setOverview] = useState(empty);
  const [selected, setSelected] = useState('');
  const [logs, setLogs] = useState<StalkLogs | null>(null);
  const [loading, setLoading] = useState(desktop);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const mounted = useRef(true);
  const working = useRef(false);
  const revision = useRef(0);

  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      const version = revision.current;
      if (desktop && !working.current) {
        try {
          const next = await request<StalkOverview>('stalk_overview');
          const nextLogs = selected ? await request<StalkLogs>('stalk_logs', { user_id: selected }) : null;
          if (!cancelled && version === revision.current && !working.current) {
            setOverview(next); setLogs(nextLogs);
          }
        } catch (error) {
          if (!cancelled && version === revision.current && !working.current) setError(message(error));
        } finally {
          if (!cancelled) setLoading(false);
        }
      }
      if (!cancelled) timer = setTimeout(poll, 5000);
    }
    void poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [connection, selected, pending]);

  const select = useCallback((id: string) => {
    if (id !== selected) { revision.current++; setLogs(null); setSelected(id); }
  }, [selected]);
  const perform = useCallback(async (action: () => Promise<void>) => {
    if (working.current) return false;
    working.current = true; revision.current++;
    setPending(true); setError(''); setNotice('');
    try {
      await action();
      return true;
    } catch (error) {
      if (mounted.current) setError(message(error));
      return false;
    } finally {
      working.current = false;
      if (mounted.current) { setPending(false); setLoading(false); }
    }
  }, []);
  const refresh = useCallback(() => perform(async () => {
    const next = await request<StalkOverview>('stalk_overview');
    const nextLogs = selected ? await request<StalkLogs>('stalk_logs', { user_id: selected }) : null;
    if (mounted.current) { setOverview(next); setLogs(nextLogs); setNotice('Stalk aggiornato.'); }
  }), [perform, selected]);
  const setMonitoring = useCallback((user: string, enabled: boolean) => perform(async () => {
    const next = await request<StalkOverview & { changed_id: string }>('stalk_set', { user, enabled });
    if (mounted.current) {
      setOverview(next);
      setLogs(previous => previous?.user_id === next.changed_id ? previous : null);
      setSelected(next.changed_id);
      setNotice(enabled ? 'Stalk attivato nei gruppi visibili al tuo account.' : 'Stalk fermato. I registri raccolti restano disponibili.');
    }
  }), [perform]);

  return { overview, selected, select, logs, loading, pending, error, notice, refresh, setMonitoring };
}
