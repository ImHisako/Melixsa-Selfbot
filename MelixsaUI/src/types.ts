export type Connection = 'offline' | 'connecting' | 'connected' | 'error' | 'login_phone' | 'login_code' | 'login_password';
export type Page = 'home' | 'modules' | 'surveillance' | 'settings' | 'activity';
export interface Settings {
  prefix: string;
  delete_after: number;
  autoreact: boolean;
  autoreact_emojis: string[];
  autoreact_count: number;
  minimal_mode: boolean;
  anti_login_enabled: boolean;
  error_notify: boolean;
  log_max_bytes: number;
  log_backups: number;
  log_retention_days: number;
  console: Record<string, boolean>;
}
export interface Profile {
  id: number;
  name: string;
  username: string;
  photo: string | null;
  premium: boolean;
}
export interface Activity {
  id: number;
  time: string;
  category: string;
  message: string;
  level: 'info' | 'error';
}
export interface Snapshot {
  settings: Settings;
  afk: { enabled: boolean; message: string };
  profile: Profile | null;
  connection: Connection;
  last_error: string;
  session_available: boolean;
  credentials_available: boolean;
  uptime: number;
  stats: { groups: number; users: number; commands: number; jobs: number };
  events: Activity[];
}
export type SettingsPatch = Partial<Settings> & { afk?: { enabled: boolean; message?: string } };

export interface SurveillanceGroup {
  id: string;
  title: string;
  username: string;
  enabled: boolean;
  log_bytes: number;
  log_files: number;
  last_update: string | null;
}
export interface SurveillanceOverview {
  groups: SurveillanceGroup[];
  active_count: number;
  log_bytes: number;
}
export interface SurveillanceRecord {
  event: 'new' | 'edited';
  date: string;
  message_id: string;
  sender: string;
  username: string;
  text: string;
  media: string;
  chat_title: string;
}
export interface SurveillanceLogs {
  chat_id: string;
  limit: number;
  records: SurveillanceRecord[];
  limited: boolean;
  skipped: number;
}
export interface SurveillanceChat { id: string; title: string; username: string }
