import { useCallback, useEffect, useRef, useState } from 'react';
import { desktop, request } from '../lib/bridge';
import type { ChatPhotos, Connection, ProfilePhoto } from '../types';

export function useChatPhotos(connection: Connection) {
  const connected = desktop && connection === 'connected';
  const [photos, setPhotos] = useState<Record<string, ProfilePhoto>>({});
  const cache = useRef(new Map<string, ProfilePhoto>());
  const counts = useRef(new Map<string, number>());
  const [targets, setTargets] = useState<string[]>([]);
  const [refreshKey, setRefreshKey] = useState(0);
  const key = [...targets].sort().join(',');

  const observe = useCallback((id: string, visible: boolean) => {
    if (!id) return;
    const previous = counts.current.get(id) ?? 0;
    const next = Math.max(0, previous + (visible ? 1 : -1));
    if (next) counts.current.set(id, next);
    else counts.current.delete(id);
    if (!!previous !== !!next) setTargets([...counts.current.keys()]);
  }, []);

  useEffect(() => {
    cache.current.clear();
    setPhotos({});
  }, [connected]);

  useEffect(() => {
    if (!connected || !key) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const ids = key.split(',');
    const active = new Set(ids);
    async function poll() {
      let pending = false;
      let changed = false;
      try {
        for (let offset = 0; offset < ids.length && !stopped; offset += 60) {
          const batch = ids.slice(offset, offset + 60);
          const known = Object.fromEntries(batch.flatMap(id => {
            const item = cache.current.get(id);
            return item ? [[id, item.version]] : [];
          }));
          const result = await request<ChatPhotos>('chat_photos', { ids: batch, known });
          if (stopped) return;
          pending ||= result.pending;
          for (const [id, item] of Object.entries(result.photos)) {
            cache.current.delete(id);
            cache.current.set(id, item);
            changed = true;
          }
        }
        // Bound image memory while keeping every avatar currently on screen.
        for (const id of cache.current.keys()) {
          if (cache.current.size <= 512) break;
          if (!active.has(id)) cache.current.delete(id);
        }
        if (changed && !stopped) setPhotos(Object.fromEntries(cache.current));
      } catch {
        // Thumbnails use initials if unavailable; messaging stays fully usable.
        pending = false;
      }
      if (!stopped) timer = setTimeout(poll, pending ? 1000 : 60_000);
    }
    timer = setTimeout(poll, 100);
    return () => { stopped = true; clearTimeout(timer); };
  }, [connected, key, refreshKey]);

  const refresh = useCallback(() => setRefreshKey(value => value + 1), []);
  return { photos, observe, refresh };
}
