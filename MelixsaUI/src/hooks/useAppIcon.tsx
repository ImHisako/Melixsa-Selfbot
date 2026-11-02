import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { invoke, isTauri } from '@tauri-apps/api/core';
import { appIconAssets, appIconStorageKey, readAppIcon, type AppIcon } from '../lib/appIcon';

interface AppIconPreference {
  icon: AppIcon;
  busy: boolean;
  error: boolean;
  persisted: boolean;
  changeIcon: (icon: AppIcon) => Promise<boolean>;
  retry: () => Promise<boolean>;
}

const AppIconContext = createContext<AppIconPreference | null>(null);

export function AppIconProvider({ children }: { children: ReactNode }) {
  const [icon, setIcon] = useState<AppIcon>(() => {
    try { return readAppIcon(window.localStorage); } catch { return 'default'; }
  });
  const [busy, setBusy] = useState(isTauri());
  const [error, setError] = useState(false);
  const [persisted, setPersisted] = useState(true);
  const working = useRef(false);
  const mounted = useRef(true);
  const attempted = useRef(icon);

  const changeIcon = useCallback(async (next: AppIcon) => {
    if (working.current) return false;
    working.current = true;
    attempted.current = next;
    setBusy(true); setError(false);
    try {
      // This native command is independent of the Telegram/Python bridge.
      if (isTauri()) await invoke('set_app_icon', { icon: next });
      if (!mounted.current) return false;
      setIcon(next);
      try {
        window.localStorage.setItem(appIconStorageKey, next);
        setPersisted(true);
      } catch {
        setPersisted(false);
      }
      return true;
    } catch {
      if (mounted.current) setError(true);
      return false;
    } finally {
      working.current = false;
      if (mounted.current) setBusy(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void changeIcon(attempted.current);
    return () => { mounted.current = false; };
  }, [changeIcon]);

  useEffect(() => {
    const asset = appIconAssets[icon];
    const link = document.querySelector<HTMLLinkElement>('link[rel="icon"]') ?? document.createElement('link');
    link.rel = 'icon'; link.type = asset.type; link.href = asset.src;
    if (!link.isConnected) document.head.append(link);
  }, [icon]);

  const retry = useCallback(() => changeIcon(attempted.current), [changeIcon]);
  const value = useMemo(() => ({ icon, busy, error, persisted, changeIcon, retry }), [icon, busy, error, persisted, changeIcon, retry]);
  return <AppIconContext.Provider value={value}>{children}</AppIconContext.Provider>;
}

export function useAppIcon() {
  const value = useContext(AppIconContext);
  if (!value) throw new Error('useAppIcon requires AppIconProvider');
  return value;
}
