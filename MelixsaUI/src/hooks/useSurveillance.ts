import { useCallback, useEffect, useRef, useState } from 'react';
import { desktop, request } from '../lib/bridge';
import type { Connection, SurveillanceChat, SurveillanceLogs, SurveillanceOverview } from '../types';

const empty: SurveillanceOverview = { groups: [], active_count: 0, log_bytes: 0 };
const message = (error: unknown) => String(error instanceof Error ? error.message : error);

export function useSurveillance(connection: Connection) {
  const [overview, setOverview] = useState(empty);
  const [logs, setLogs] = useState<SurveillanceLogs | null>(null);
  const [selected, setSelected] = useState('');
  const [chats, setChats] = useState<SurveillanceChat[]>([]);
  const [chatsLoaded, setChatsLoaded] = useState(false);
  const [loading, setLoading] = useState(desktop);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const mounted = useRef(true);
  const working = useRef(false);

  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      if (desktop && !working.current) {
        try {
          const next = await request<SurveillanceOverview>('surveillance_overview');
          if (cancelled) return;
          setOverview(next);
          if (selected) {
            const nextLogs = await request<SurveillanceLogs>('surveillance_logs', { chat_id: selected });
            if (cancelled) return;
            setLogs(nextLogs);
          }
        } catch (error) {
          if (!cancelled) setError(message(error));
        } finally {
          if (!cancelled) setLoading(false);
        }
      }
      if (!cancelled) timer = setTimeout(poll, 5000);
    }
    void poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [connection, selected]);

  const select = useCallback((id: string) => { if (id !== selected) { setLogs(null); setSelected(id); } }, [selected]);
  const perform = useCallback(async (action: () => Promise<void>) => {
    if (working.current) return false;
    working.current = true; setPending(true); setError(''); setNotice('');
    try {
      await action();
      return true;
    } catch (error) {
      if (mounted.current) setError(message(error));
      return false;
    } finally {
      working.current = false;
      if (mounted.current) setPending(false);
    }
  }, []);
  const refresh = useCallback(() => perform(async () => {
    const next = await request<SurveillanceOverview>('surveillance_overview');
    const nextLogs = selected ? await request<SurveillanceLogs>('surveillance_logs', { chat_id: selected }) : null;
    if (mounted.current) { setOverview(next); setLogs(nextLogs); setNotice('Surveillance aggiornata.'); }
  }), [perform, selected]);
  const loadChats = useCallback(() => perform(async () => {
    const response = await request<{ chats: SurveillanceChat[] }>('surveillance_chats');
    const next = await request<SurveillanceOverview>('surveillance_overview');
    if (mounted.current) { setChats(response.chats); setChatsLoaded(true); setOverview(next); }
  }), [perform]);
  const setMonitoring = useCallback((chat: string, enabled: boolean) => perform(async () => {
    const next = await request<SurveillanceOverview & { changed_id: string }>('surveillance_set', { chat, enabled });
    if (mounted.current) {
      setOverview(next); setLogs(previous => previous?.chat_id === next.changed_id ? previous : null); setSelected(next.changed_id);
      setNotice(enabled ? 'Monitoraggio attivato. I nuovi eventi verranno registrati.' : 'Monitoraggio fermato. I registri raccolti restano disponibili.');
    }
  }), [perform]);
  return { overview, logs, selected, select, chats, chatsLoaded, loading, pending, error, notice, refresh, loadChats, setMonitoring };
}
