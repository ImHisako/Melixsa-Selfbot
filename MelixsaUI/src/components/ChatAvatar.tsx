import { useEffect, useRef, useState } from 'react';
import { CircleAlert, LoaderCircle, X } from 'lucide-react';
import { useI18n } from '../i18n';
import { request } from '../lib/bridge';
import { Button } from './ui';

export function ChatAvatar({ id, name, photo, kind = 'private', small = false, observe, open }: {
  id: string; name: string; photo: string | null; kind?: string; small?: boolean;
  observe: (id: string, visible: boolean) => void; open: (id: string, name: string) => void;
}) {
  const { t } = useI18n();
  const target = useRef<HTMLSpanElement>(null);
  const [failed, setFailed] = useState<string | null>(null);
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map(part => Array.from(part)[0]).join('').toLocaleUpperCase() || '?';
  const available = photo && photo !== failed;

  useEffect(() => {
    const element = target.current;
    if (!element || !id) return;
    let visible = false;
    const update = (next: boolean) => {
      if (next !== visible) { visible = next; observe(id, visible); }
    };
    if (!('IntersectionObserver' in window)) {
      update(true);
      return () => update(false);
    }
    const observer = new IntersectionObserver(entries => update(entries[0].isIntersecting), { rootMargin: '100px' });
    observer.observe(element);
    return () => { observer.disconnect(); update(false); };
  }, [id, observe]);

  const avatar = <span className={`chat-avatar ${small ? 'chat-avatar-small' : ''}`} data-kind={kind} role="img" aria-label={name}>
    {available ? <img src={photo} alt="" decoding="async" onError={() => setFailed(photo)} /> : <span aria-hidden="true">{initials}</span>}
  </span>;
  return <span className="chat-photo-target" ref={target}>
    {available ? <button type="button" className="chat-photo-button" aria-label={t('Apri foto profilo di {name}', { name })} title={t('Apri foto profilo di {name}', { name })} onClick={() => open(id, name)}>{avatar}</button> : avatar}
  </span>;
}

export function ProfilePhotoDialog({ id, name, thumbnail, close }: { id: string; name: string; thumbnail: string | null; close: () => void }) {
  const { t, localize } = useI18n();
  const dialog = useRef<HTMLDialogElement>(null);
  const [photo, setPhoto] = useState(thumbnail);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);

  useEffect(() => {
    let stopped = false;
    setLoading(true); setError('');
    void request<{ photo: string | null }>('chat_photo', { chat_id: id }).then(result => {
      if (!stopped) setPhoto(result.photo);
    }).catch(reason => {
      if (!stopped) { setPhoto(null); setError(String(reason instanceof Error ? reason.message : reason)); }
    }).finally(() => { if (!stopped) setLoading(false); });
    return () => { stopped = true; };
  }, [id, attempt]);

  return <dialog className="chat-photo-dialog" ref={dialog} onClose={close} aria-labelledby="profile-photo-title" onClick={event => { if (event.target === event.currentTarget) dialog.current?.close(); }}>
    <div className="chat-photo-dialog-header"><h2 id="profile-photo-title">{t('Foto profilo di {name}', { name })}</h2><button type="button" className="icon-button" aria-label={t('Chiudi')} onClick={() => dialog.current?.close()}><X size={19} /></button></div>
    <div className="chat-photo-stage">
      {photo && <img src={photo} alt={t('Foto profilo di {name}', { name })} onError={() => { setPhoto(null); setError('Foto profilo non disponibile.'); }} />}
      {loading && <span className="chat-photo-loading" role="status"><LoaderCircle className="spin" size={24} />{t('Caricamento foto…')}</span>}
      {!loading && !photo && !error && <p>{t('Nessuna foto visibile')}</p>}
    </div>
    {error && <div className="chat-photo-error" role="alert"><CircleAlert size={16} /><span>{localize(error)}</span><Button variant="ghost" onClick={() => setAttempt(value => value + 1)}>{t('Riprova')}</Button></div>}
  </dialog>;
}
