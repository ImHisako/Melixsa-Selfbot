import { CheckCircle2, Image, LoaderCircle } from 'lucide-react';
import { useAppIcon } from '../hooks/useAppIcon';
import { useI18n } from '../i18n';
import { appIconAssets } from '../lib/appIcon';
import { Button } from './ui';

export function AppIconPicker() {
  const { t } = useI18n();
  const { icon, busy, error, persisted, changeIcon, retry } = useAppIcon();
  const options = [
    { value: 'default', label: 'Melixsa', description: t('L’icona originale con luna e stelle.') },
    { value: 'egirl', label: 'E-Girl', description: t('La tua immagine E-Girl per Melixsa.') },
  ] as const;

  return <section className="panel settings-panel app-icon-panel">
    <div className="settings-panel-title"><Image size={18} /><h2>{t('Icona dell’app')}</h2></div>
    <p className="panel-description">{t('Scegli l’icona di Melixsa. La modifica si applica subito e resta salvata sul dispositivo.')}</p>
    <div className="app-icon-options" role="radiogroup" aria-label={t('Icona dell’app')}>
      {options.map(option => <label key={option.value} className={`app-icon-option ${icon === option.value ? 'is-selected' : ''}`}>
        <input type="radio" name="app-icon" value={option.value} checked={icon === option.value} disabled={busy} onChange={() => void changeIcon(option.value)} />
        <span className="app-icon-preview"><img src={appIconAssets[option.value].src} alt="" /></span>
        <span className="app-icon-copy"><strong>{option.label}</strong><span>{option.description}</span></span>
        {icon === option.value && <CheckCircle2 className="app-icon-check" size={17} aria-hidden="true" />}
      </label>)}
    </div>
    <p className="app-icon-status" role="status">{busy ? <><LoaderCircle className="spin" size={13} />{t('Aggiornamento dell’icona…')}</> : !persisted ? t('Il salvataggio locale non è disponibile. La scelta vale per questa apertura.') : t('Disponibile anche senza collegare Telegram.')}</p>
    {error && <div className="app-icon-error" role="alert"><span>{t('Impossibile aggiornare l’icona. Riprova.')}</span><Button variant="ghost" disabled={busy} onClick={() => void retry()}>{t('Riprova')}</Button></div>}
  </section>;
}
