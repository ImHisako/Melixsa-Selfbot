import { ArrowUpRight, ChevronRight, ContactRound, RefreshCw, Save } from 'lucide-react';
import { useEffect, useState, type FormEvent } from 'react';
import { Avatar, Button, PageIntro, SectionTitle } from '../components/ui';
import { useI18n } from '../i18n';
import { desktop, request } from '../lib/bridge';
import type { Connection, Profile } from '../types';
import './profiles.css';

interface SavedProfile {
  name: string;
  first_name: string;
  last_name: string;
  bio: string;
  photo: string | null;
}

export function Profiles({ profile, connection, disabled, load }: {
  profile: Profile | null;
  connection: Connection;
  disabled: boolean;
  load: (name: string) => Promise<boolean>;
}) {
  const { t, localize } = useI18n();
  const [names, setNames] = useState<string[]>([]);
  const [selection, setSelection] = useState('');
  const [revision, setRevision] = useState(0);
  const [listing, setListing] = useState(desktop);
  const [listError, setListError] = useState('');
  const [preview, setPreview] = useState<SavedProfile | null>(null);
  const [previewError, setPreviewError] = useState('');
  const [label, setLabel] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [saved, setSaved] = useState('');
  const selected = names.includes(selection) ? selection : names[0] ?? '';
  const visible = preview?.name === selected ? preview : null;
  const connected = connection === 'connected';
  const canApply = connected && !disabled && !saving;

  useEffect(() => {
    if (!desktop) return;
    let active = true;
    setListing(true);
    setListError('');
    request<string[]>('saved_profiles').then(result => {
      if (active) setNames(result);
    }, error => {
      if (active) setListError(error instanceof Error ? error.message : String(error));
    }).finally(() => { if (active) setListing(false); });
    return () => { active = false; };
  }, [connection, revision]);

  useEffect(() => {
    setPreviewError('');
    if (!selected) return;
    let active = true;
    request<SavedProfile>('saved_profile_preview', { name: selected }).then(result => {
      if (active) setPreview(result);
    }, error => {
      if (active) setPreviewError(error instanceof Error ? error.message : String(error));
    });
    return () => { active = false; };
  }, [selected, revision]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canApply || !label.trim()) return;
    setSaving(true);
    setSaveError('');
    setSaved('');
    try {
      const result = await request<{ name: string }>('save_profile', { name: label });
      setNames(current => current.includes(result.name) ? current : [...current, result.name]);
      setSelection(result.name);
      setLabel('');
      setSaved(result.name);
      setRevision(current => current + 1);
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : String(error));
    } finally {
      setSaving(false);
    }
  }

  const previewName = visible ? [visible.first_name, visible.last_name].filter(Boolean).join(' ') : '';
  return <>
    <PageIntro eyebrow={t('IL TUO SPAZIO')} title={t('Profili')} description={t('Salva il tuo profilo Telegram con un nome e rivedi le copie prima di applicarle.')} />
    <section className="panel profiles-save">
      <div className="profiles-current"><Avatar profile={profile} /><div><h2>{t('Profilo attuale')}</h2><p>{profile?.name || t('Collega il tuo Telegram')}</p></div></div>
      <form onSubmit={save}>
        <label className="field"><span>{t('Nome del profilo da salvare')}</span><input required maxLength={64} value={label} disabled={!canApply} onChange={event => setLabel(event.target.value)} placeholder={t('Es. Profilo lavoro')} /></label>
        <Button type="submit" loading={saving} disabled={!canApply || !label.trim()}><Save size={15} />{t('Salva profilo')}</Button>
      </form>
      {saveError && <p className="profiles-feedback" role="alert">{localize(saveError)}</p>}
      {saved && !saveError && <p className="profiles-feedback" role="status">{t('Profilo salvato: {name}', { name: saved })}</p>}
      {!connected && <p className="profiles-feedback">{t('Collega Telegram per salvare o caricare un profilo.')}</p>}
    </section>
    <div className="profiles-grid">
      <section className="panel profiles-library" aria-busy={listing}>
        <SectionTitle title={t('Profili salvati')} aside={<button type="button" className="icon-button" title={t('Aggiorna elenco')} aria-label={t('Aggiorna elenco')} disabled={!desktop || listing || saving} onClick={() => setRevision(current => current + 1)}><RefreshCw size={15} className={listing ? 'spin' : ''} /></button>} />
        {listError && <p role="alert">{localize(listError)}</p>}
        {names.length ? <ul>{names.map(name => <li key={name}><button type="button" aria-pressed={name === selected} onClick={() => setSelection(name)}><ContactRound size={16} /><span>{name}</span><ChevronRight size={15} /></button></li>)}</ul>
          : <p>{listing ? t('Caricamento dei profili…') : t('Nessun profilo salvato.')}</p>}
      </section>
      <section className="panel profiles-preview">
        <SectionTitle title={t('Anteprima profilo')} />
        {previewError ? <p role="alert">{localize(previewError)}</p> : visible ? <>
          <div className="profiles-preview-card"><Avatar profile={{ name: previewName, photo: visible.photo }} size="large" /><div><span className="overline">{visible.name}</span><h3>{previewName}</h3><p>{visible.bio || t('Nessuna bio salvata.')}</p></div></div>
          <div className="profiles-preview-actions">{!visible.photo && <p>{t('Questa copia applica solo nome e bio.')}</p>}<Button disabled={!canApply} onClick={() => void load(visible.name)}><ArrowUpRight size={16} />{t('Carica su Telegram')}</Button></div>
        </> : <div className="profiles-preview-empty"><ContactRound size={30} strokeWidth={1.4} /><p>{selected ? t('Caricamento dell’anteprima…') : t('Seleziona un profilo salvato per vedere l’anteprima.')}</p></div>}
      </section>
    </div>
  </>;
}
