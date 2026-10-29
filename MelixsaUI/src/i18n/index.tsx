import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { languageStorageKey, locales, localizeMessage, readLanguage, resolveLanguage, translate, type Language, type Message, type Params } from './core';

interface I18n {
  language: Language;
  locale: string;
  setLanguage: (language: Language) => void;
  t: (message: Message, params?: Params) => string;
  localize: (message: string) => string;
}

const I18nContext = createContext<I18n | null>(null);

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [language, setLanguage] = useState<Language>(() => {
    try {
      return readLanguage(window.localStorage, navigator.language);
    } catch {
      return resolveLanguage(null, navigator.language);
    }
  });
  const t = useCallback((message: Message, params?: Params) => translate(language, message, params), [language]);
  const localize = useCallback((message: string) => localizeMessage(language, message), [language]);

  useEffect(() => {
    document.documentElement.lang = language;
    document.title = `Melixsa — ${t('Il tuo spazio')}`;
    document.querySelector('meta[name="description"]')?.setAttribute('content', t('Il tuo spazio personale per Melixsa.'));
    try {
      window.localStorage.setItem(languageStorageKey, language);
    } catch {
      // The selection still works for this session when storage is unavailable.
    }
  }, [language, t]);

  const value = useMemo(() => ({ language, locale: locales[language], setLanguage, t, localize }), [language, t, localize]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) throw new Error('useI18n requires LanguageProvider');
  return context;
}
