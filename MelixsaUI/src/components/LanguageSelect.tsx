import { Languages } from 'lucide-react';
import { useI18n } from '../i18n';

export function LanguageSelect({ id }: { id?: string }) {
  const { language, setLanguage, t } = useI18n();
  return <label className="language-select" title={t('Lingua dell’interfaccia')}>
    <Languages size={15} aria-hidden="true" />
    <select id={id} aria-label={t('Lingua dell’interfaccia')} value={language} onChange={event => setLanguage(event.target.value === 'en' ? 'en' : 'it')}>
      <option value="it" lang="it">Italiano</option>
      <option value="en" lang="en">English</option>
    </select>
  </label>;
}
