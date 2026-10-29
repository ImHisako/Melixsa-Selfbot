import english from './commands-en.json';
import type { Language } from './core';

const suffixes = [
  ['. Usa il prefisso corrente. Testo: argomento oppure messaggio in risposta.', '. Use the current prefix. Supply text as an argument or reply to a message.'],
  ['. Testo o codice: argomento oppure messaggio in risposta; massimo 1500 caratteri.', '. Text or code: an argument or a reply; maximum 1500 characters.'],
  ['. Report da AbelXeon/OSINT-BOT, con link e allegati quando disponibili.', '. Report from AbelXeon/OSINT-BOT, with links and attachments when available.'],
] as const;

export function hasCommandTranslation(text: string): boolean {
  if (Object.hasOwn(english, text) || text.startsWith('Blocco di codice ')) return true;
  return suffixes.some(([suffix]) => text.endsWith(suffix) && hasCommandTranslation(text.slice(0, -suffix.length)));
}

export function commandText(language: Language, text: string): string {
  if (language === 'it') return text;
  if (Object.hasOwn(english, text)) return english[text as keyof typeof english];
  if (text.startsWith('Blocco di codice ')) return `Code block: ${text.slice('Blocco di codice '.length)}`;
  for (const [suffix, translated] of suffixes) {
    if (text.endsWith(suffix)) return commandText(language, text.slice(0, -suffix.length)) + translated;
  }
  return text;
}
