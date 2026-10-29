import english from './en.json';

// Italian source messages are the catalog keys, so both languages share one contract.
export type Message = keyof typeof english;
export type Language = 'it' | 'en';
export type Params = Record<string, string | number>;
export const languageStorageKey = 'melixsa.language';
export const locales = { it: 'it-IT', en: 'en-GB' } as const;

export function resolveLanguage(saved: string | null, browserLanguage: string): Language {
  if (saved === 'it' || saved === 'en') return saved;
  return /^en(?:[-_]|$)/i.test(browserLanguage) ? 'en' : 'it';
}

export function readLanguage(storage: Pick<Storage, 'getItem'>, browserLanguage: string): Language {
  try {
    return resolveLanguage(storage.getItem(languageStorageKey), browserLanguage);
  } catch {
    return resolveLanguage(null, browserLanguage);
  }
}

export function translate(language: Language, message: Message, params: Params = {}): string {
  const template = language === 'en' ? english[message] : message;
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    Object.hasOwn(params, key) ? String(params[key]) : match);
}

// Translate only recognised bridge messages. User text and unknown diagnostics stay intact.
export function localizeMessage(language: Language, message: string): string {
  if (Object.hasOwn(english, message)) return translate(language, message as Message);
  const bounds = /^(\w+): scegli un numero da (\d+) a (\d+)\.$/.exec(message);
  if (bounds) return translate(language, '{setting}: scegli un numero da {min} a {max}.', { setting: bounds[1], min: bounds[2], max: bounds[3] });
  const telegram = /^Telegram: (\w+)\. Controlla i dati e riprova\.$/.exec(message);
  if (telegram) return translate(language, 'Telegram: {error}. Controlla i dati e riprova.', { error: telegram[1] });
  const monitoring = /^Monitoraggio del gruppo (-\d+) (attivato|fermato)\.$/.exec(message);
  if (monitoring) return translate(language, monitoring[2] === 'attivato' ? 'Monitoraggio del gruppo {id} attivato.' : 'Monitoraggio del gruppo {id} fermato.', { id: monitoring[1] });
  const stalk = /^Monitoraggio Stalk dell’utente (\d+) (attivato|fermato)\.$/.exec(message);
  if (stalk) return translate(language, stalk[2] === 'attivato' ? 'Monitoraggio Stalk dell’utente {id} attivato.' : 'Monitoraggio Stalk dell’utente {id} fermato.', { id: stalk[1] });
  const config = /^Formato non valido per (\w+) nel file \.env\.$/.exec(message);
  if (config) return translate(language, 'Formato non valido per {setting} nel file .env.', { setting: config[1] });
  return message;
}
