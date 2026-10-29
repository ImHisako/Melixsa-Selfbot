import { invoke, isTauri } from '@tauri-apps/api/core';
import type { Snapshot } from '../types';

export const desktop = isTauri();

export async function request<T = Snapshot>(method: string, params: object = {}): Promise<T> {
  if (!desktop) throw new Error('Apri l’app desktop per collegare Telegram e modificare Melixsa.');
  return invoke<T>('bridge_request', { method, params });
}

// Browser preview is explicitly disconnected and never stores pretend settings.
export const initialSnapshot: Snapshot = {
  settings: {
    prefix: '/', delete_after: 40, autoreact: false, autoreact_emojis: ['🖤', '🦇'],
    autoreact_count: 2, minimal_mode: false, anti_login_enabled: true, error_notify: false,
    log_max_bytes: 10000000, log_backups: 5, log_retention_days: 0,
    console: { timestamp: true, spacers: true, pgradient: true, lgradient: true, debug_mode: false },
  },
  afk: { enabled: false, message: 'Al momento sono AFK. Tornerò appena possibile.' },
  profile: null, connection: 'offline', last_error: '', session_available: false,
  credentials_available: false, uptime: 0, stats: { groups: 0, users: 0, commands: 0, jobs: 0 }, events: [],
};
