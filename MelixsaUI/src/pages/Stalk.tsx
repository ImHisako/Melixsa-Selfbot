import { useMemo, useState } from 'react';
import { ArrowDownToLine, CheckCircle2, CircleAlert, Clock3, FileText, FolderArchive, Hash, Info, ListFilter, LoaderCircle, MessageSquareText, PencilLine, Plus, RefreshCw, Search, UserRoundSearch, Users } from 'lucide-react';
import { Button, PageIntro, SectionTitle, Toggle } from '../components/ui';
import { useStalk } from '../hooks/useStalk';
import { useI18n } from '../i18n';
import type { Connection, StalkLogs, StalkUser } from '../types';
import './surveillance.css';
import './stalk.css';

export function Stalk({ connection, disabled }: { connection: Connection; disabled: boolean }) {
  const { t, locale, localize } = useI18n();
  const state = useStalk(connection);
  const [query, setQuery] = useState('');
  const [search, setSearch] = useState('');
  const [onlyActive, setOnlyActive] = useState(false);
  const connected = connection === 'connected';
  const blocked = disabled || state.pending;
  const users = useMemo(() => state.overview.users.filter(user =>
    (!onlyActive || user.enabled) && `${user.name} ${user.username} ${user.id}`.toLocaleLowerCase().includes(search.toLocaleLowerCase())
  ), [state.overview.users, search, onlyActive]);
  const selected = state.overview.users.find(user => user.id === state.selected);
  const logs = state.logs?.user_id === state.selected ? state.logs : null;

  return <>
    <PageIntro eyebrow={t('MONITORAGGIO DEGLI UTENTI')} title="Stalk." description={t('Gestisci gli utenti seguiti e consulta i messaggi raccolti nei gruppi visibili al tuo account.')}
      action={<Button variant="secondary" loading={state.pending} disabled={blocked} onClick={() => void state.refresh()}><RefreshCw size={15} />{t('Aggiorna')}</Button>} />
    <div className="surveillance-stats">
      <div className="panel surveillance-status">
        <div className={`surveillance-radar ${connected && state.overview.active_count ? 'listening' : ''}`}><UserRoundSearch size={25} /></div>
        <div><span className="overline">{t('STATO DEL MONITORAGGIO')}</span><strong>{connected ? state.overview.active_count ? t('In ascolto.') : t('Pronta a iniziare.') : t('In pausa.')}</strong><p>{t('Stesso elenco dei comandi stalk e unstalk.')}</p></div>
        <span className={`status-dot ${connected ? '' : 'offline'}`} />
      </div>
      <div className="panel surveillance-stat"><span className="stat-icon purple"><Users size={19} /></span><div><strong>{state.overview.active_count}</strong><span>{t('Utenti seguiti')}</span></div></div>
      <div className="panel surveillance-stat"><span className="stat-icon blue"><FolderArchive size={19} /></span><div><strong>{size(state.overview.log_bytes, locale)}</strong><span>{t('Registri sul dispositivo')}</span></div></div>
    </div>
    {state.error && <div className="error-banner" role="alert"><CircleAlert size={17} /><p>{localize(state.error)}</p></div>}
    {state.notice && <div className="surveillance-notice" role="status"><CheckCircle2 size={16} />{localize(state.notice)}</div>}
    <section className="panel surveillance-add">
      <div className="surveillance-add-heading"><div className="module-icon purple"><Plus size={21} /></div><div><h2>{t('Aggiungi un utente a Stalk.')}</h2><p>{t('Inserisci uno username Telegram oppure un ID utente positivo.')}</p></div></div>
      <form onSubmit={async event => { event.preventDefault(); if (await state.setMonitoring(query.trim(), true)) setQuery(''); }}>
        <label className="surveillance-target"><Hash size={17} /><input aria-label={t('Utente da seguire')} placeholder={t('@username oppure 123456789')} maxLength={64} value={query} onChange={event => setQuery(event.target.value)} required /></label>
        <Button type="submit" disabled={blocked || !connected || !query.trim()} loading={state.pending}><Plus size={15} />{t('Attiva Stalk')}</Button>
      </form>
      <div className="surveillance-hint"><Info size={13} /><span>{connected ? t('Registra solo i nuovi messaggi e le modifiche nei gruppi visibili. Non scarica lo storico.') : t('Collega Telegram per attivare Stalk. Puoi leggere i registri e fermare gli utenti anche offline.')}</span></div>
    </section>
    <div className="surveillance-workspace">
      <section className="panel surveillance-groups">
        <div className="surveillance-group-heading">
          <SectionTitle title={t('I tuoi utenti')} aside={<span className="subtle-badge">{state.overview.users.length}</span>} />
          <div className="search-field"><Search size={15} /><input aria-label={t('Cerca utenti Stalk')} placeholder={t('Cerca nome, username o ID…')} value={search} onChange={event => setSearch(event.target.value)} /></div>
          <button type="button" className={`filter-button ${onlyActive ? 'active' : ''}`} aria-pressed={onlyActive} onClick={() => setOnlyActive(!onlyActive)}><ListFilter size={13} />{t('Solo attivati')}</button>
        </div>
        {state.loading ? <Loading text={t('Caricamento degli utenti…')} /> : users.length ? <div className="surveillance-group-list">{users.map(user => <div className={`surveillance-group-row ${state.selected === user.id ? 'selected' : ''}`} key={user.id}>
          <button type="button" className="surveillance-group-select" aria-pressed={state.selected === user.id} onClick={() => state.select(user.id)}><span className="surveillance-group-icon"><UserRoundSearch size={17} /></span><span><strong>{user.name || t('Utente {id}', { id: user.id })}</strong><span>{user.username ? `@${user.username} · ${user.id}` : user.id}</span><small>{user.log_files ? t('{size} di registri', { size: size(user.log_bytes, locale) }) : t('Nessun evento salvato')}</small></span></button>
          <div className="surveillance-group-control"><Toggle label={t('Monitoraggio {name}', { name: user.name || user.id })} checked={user.enabled} disabled={blocked || (!connected && !user.enabled)} onChange={value => void state.setMonitoring(user.id, value)} /><span>{user.enabled ? connected ? t('Attivo') : t('In pausa') : t('Fermato')}</span></div>
        </div>)}</div> : <div className="surveillance-group-empty"><UserRoundSearch size={27} /><h3>{search || onlyActive ? t('Nessun utente trovato.') : t('Il primo utente parte da qui.')}</h3><p>{search || onlyActive ? t('Modifica la ricerca o rimuovi il filtro.') : t('Aggiungi uno username o un ID per iniziare.')}</p></div>}
        <div className="surveillance-group-footer"><Info size={13} />{t('Fermare un utente conserva i suoi registri.')}</div>
      </section>
      <StalkLogViewer key={state.selected} user={selected} logs={logs} connected={connected} />
    </div>
  </>;
}

function StalkLogViewer({ user, logs, connected }: { user?: StalkUser; logs: StalkLogs | null; connected: boolean }) {
  const { t, locale } = useI18n();
  const [search, setSearch] = useState('');
  const [onlyEdits, setOnlyEdits] = useState(false);
  const records = useMemo(() => (logs?.records || []).filter(record =>
    (!onlyEdits || record.event === 'edited') && `${record.sender} ${record.username} ${record.text} ${record.media} ${record.chat_title} ${record.chat_id}`.toLocaleLowerCase().includes(search.toLocaleLowerCase())
  ), [logs, search, onlyEdits]);
  return <section className="panel surveillance-viewer">
    <div className="surveillance-viewer-heading">
      <div><span className="overline">{t('REGISTRO DELL’UTENTE')}</span><h2>{user ? user.name || t('Utente {id}', { id: user.id }) : t('I messaggi, gruppo per gruppo.')}</h2><p>{user ? <><span className={`status-dot ${user.enabled && connected ? '' : 'offline'}`} />{user.enabled ? connected ? t('Monitoraggio attivo') : t('Attivato · Telegram scollegato') : t('Monitoraggio fermato')}<span className="viewer-id">{user.id}</span></> : t('Seleziona un utente per leggere il suo registro locale.')}</p></div>
      <button className="icon-button" aria-label={t('Esporta registro Stalk')} title={t('Esporta gli eventi visualizzati')} disabled={!records.length} onClick={() => logs && exportLogs({ ...logs, records })}><ArrowDownToLine size={18} /></button>
    </div>
    {user && <div className="surveillance-log-toolbar"><div className="search-field"><Search size={15} /><input aria-label={t('Cerca nei messaggi Stalk')} placeholder={t('Cerca testo o gruppo…')} value={search} onChange={event => setSearch(event.target.value)} /></div><button type="button" className={`filter-button ${onlyEdits ? 'active' : ''}`} aria-pressed={onlyEdits} onClick={() => setOnlyEdits(!onlyEdits)}><PencilLine size={13} />{t('Modifiche')}</button></div>}
    {!user ? <div className="surveillance-viewer-empty"><div className="surveillance-empty-art"><UserRoundSearch size={42} strokeWidth={1.2} /><span /><span /></div><h3>{t('Un registro per ogni utente.')}</h3><p>{t('Qui trovi i messaggi raccolti da Stalk, con il gruppo di provenienza e le modifiche.')}</p></div>
      : !logs ? <Loading text={t('Caricamento del registro…')} />
        : records.length ? <div className="surveillance-records">{records.map((record, index) => {
          const parsed = new Date(record.date);
          return <article className={`surveillance-record ${record.event === 'edited' ? 'edited' : ''}`} key={`${record.chat_id}-${record.message_id}-${record.date}-${index}`}>
            <div className="surveillance-record-top"><div className="surveillance-sender-avatar">{record.sender.slice(0, 1).toLocaleUpperCase()}</div><div><strong>{record.sender}</strong><span>{record.username ? `@${record.username}` : user.id}</span></div><span className={`record-kind ${record.event === 'edited' ? 'edited' : ''}`}>{record.event === 'edited' ? <PencilLine size={11} /> : <MessageSquareText size={11} />}{record.event === 'edited' ? t('Modificato') : t('Nuovo')}</span><time dateTime={record.date}>{Number.isNaN(parsed.getTime()) ? t('Orario non disponibile') : parsed.toLocaleString(locale, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })}</time></div>
            <div className="stalk-record-context"><Users size={12} /><span>{record.chat_title || t('Gruppo {id}', { id: record.chat_id })}</span><span>{record.chat_id}</span></div>
            <p>{record.text || (record.media ? t('Messaggio con allegato.') : t('Messaggio senza testo.'))}</p><div className="surveillance-record-bottom">{record.media && <span><FileText size={11} />{record.media}</span>}{record.message_id && <span>#{record.message_id}</span>}</div>
          </article>;
        })}</div> : <div className="surveillance-viewer-empty compact"><div className="empty-state-icon"><MessageSquareText size={27} /></div><h3>{search || onlyEdits ? t('Nessun evento corrispondente.') : t('Il registro è ancora vuoto.')}</h3><p>{search || onlyEdits ? t('Prova a cambiare ricerca o rimuovere il filtro.') : t('I nuovi messaggi appariranno quando l’utente scrive in un gruppo visibile e Melixsa è connessa.')}</p></div>}
    {logs?.skipped ? <div className="surveillance-log-note"><Info size={13} />{t('Alcune righe incomplete o non valide sono state ignorate.')}</div> : null}
    {logs?.limited && <div className="surveillance-log-note"><Info size={13} />{t('Vista limitata agli ultimi 100 eventi e a 2 MB di lettura.')}</div>}
    <div className="surveillance-viewer-footer"><span><Clock3 size={12} />{t('Aggiornamento ogni 5 secondi')}</span><span>{user ? t(records.length === 1 ? '{count} evento visualizzato' : '{count} eventi visualizzati', { count: records.length }) : t('Registri locali')}</span></div>
  </section>;
}

function Loading({ text }: { text: string }) {
  return <div className="surveillance-loading"><LoaderCircle size={21} className="spin" /><span>{text}</span></div>;
}

function size(bytes: number, locale: string) {
  const divisor = bytes < 1024 ? 1 : bytes < 1024 * 1024 ? 1024 : 1024 * 1024;
  const unit = bytes < 1024 ? 'B' : bytes < 1024 * 1024 ? 'KB' : 'MB';
  return `${(bytes / divisor).toLocaleString(locale, { maximumFractionDigits: 1 })} ${unit}`;
}

function exportLogs(logs: StalkLogs) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(logs, null, 2)], { type: 'application/json' }));
  const link = document.createElement('a'); link.href = url; link.download = `stalk-${logs.user_id}.json`; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
