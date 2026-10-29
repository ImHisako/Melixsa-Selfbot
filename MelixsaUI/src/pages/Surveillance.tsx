import { useI18n } from '../i18n';
import { useMemo, useState } from 'react';
import { ArrowDownToLine, ArrowRight, CheckCircle2, CircleAlert, Clock3, FileText, FolderArchive, Hash, Info, ListFilter, LoaderCircle, MessageSquareText, PencilLine, Plus, Radar, RefreshCw, Search, ShieldCheck, Users } from 'lucide-react';
import { Button, PageIntro, SectionTitle, Toggle } from '../components/ui';
import { useSurveillance } from '../hooks/useSurveillance';
import type { Connection, SurveillanceGroup, SurveillanceLogs } from '../types';
import './surveillance.css';

export function Surveillance({ connection, disabled }: { connection: Connection; disabled: boolean }) {
  const { t, locale, localize } = useI18n();
  const state = useSurveillance(connection);
  const [query, setQuery] = useState('');
  const [groupSearch, setGroupSearch] = useState('');
  const [onlyActive, setOnlyActive] = useState(false);
  const connected = connection === 'connected';
  const blocked = disabled || state.pending;
  const groups = useMemo(() => state.overview.groups.filter(group =>
    (!onlyActive || group.enabled) && `${group.title} ${group.username} ${group.id}`.toLocaleLowerCase().includes(groupSearch.toLocaleLowerCase())
  ), [state.overview.groups, groupSearch, onlyActive]);
  const selected = state.overview.groups.find(group => group.id === state.selected);
  const logs = state.logs?.chat_id === state.selected ? state.logs : null;
  const available = state.chats.filter(chat => `${chat.title} ${chat.username} ${chat.id}`.toLocaleLowerCase().includes(query.toLocaleLowerCase().replace(/^@/, ''))).slice(0, 12);

  return <>
    <PageIntro eyebrow={t("MONITORAGGIO DEI GRUPPI")} title="Surveillance." description={t("I gruppi che scegli. Gli eventi che contano. Un registro da consultare.")}
      action={<Button variant="secondary" loading={state.pending} disabled={blocked} onClick={() => void state.refresh()}><RefreshCw size={15} /> {t("Aggiorna")}</Button>} />
    <div className="surveillance-stats">
      <div className="panel surveillance-status">
        <div className={`surveillance-radar ${connected && state.overview.active_count ? 'listening' : ''}`}><Radar size={25} /></div>
        <div><span className="overline">{t("STATO DEL MONITORAGGIO")}</span><strong>{connected ? state.overview.active_count ? t("In ascolto.") : t("Pronta a iniziare.") : t("In pausa.")}</strong><p>{connected ? t("Registra nuovi messaggi e modifiche.") : t("Collega Telegram per raccogliere nuovi eventi.")}</p></div>
        <span className={`status-dot ${connected ? '' : 'offline'}`} />
      </div>
      <div className="panel surveillance-stat"><span className="stat-icon purple"><Users size={19} /></span><div><strong>{state.overview.active_count}</strong><span>{t("Gruppi attivati")}</span></div></div>
      <div className="panel surveillance-stat"><span className="stat-icon blue"><FolderArchive size={19} /></span><div><strong>{size(state.overview.log_bytes, locale)}</strong><span>{t("Registri sul dispositivo")}</span></div></div>
    </div>
    {state.error && <div className="error-banner" role="alert"><CircleAlert size={17} /><p>{localize(state.error)}</p></div>}
    {state.notice && <div className="surveillance-notice" role="status"><CheckCircle2 size={16} />{localize(state.notice)}</div>}
    <section className="panel surveillance-add">
      <div className="surveillance-add-heading"><div className="module-icon purple"><Plus size={21} /></div><div><h2>{t("Aggiungi un gruppo al tuo spazio.")}</h2><p>{t("Scegli una chat Telegram oppure inserisci il suo username o ID.")}</p></div><Button variant="ghost" disabled={blocked || !connected} onClick={() => void state.loadChats()}><Users size={15} /> {t("Carica i miei gruppi")}</Button></div>
      <form onSubmit={async event => { event.preventDefault(); if (await state.setMonitoring(query.trim(), true)) setQuery(''); }}>
        <label className="surveillance-target"><Hash size={17} /><input aria-label={t("Gruppo da monitorare")} placeholder={t("@nomegruppo oppure -1001234567890")} value={query} maxLength={64} onChange={event => setQuery(event.target.value)} required /></label>
        <Button type="submit" disabled={blocked || !connected || !query.trim()} loading={state.pending}><Plus size={15} /> {t("Attiva Surveillance")}</Button>
      </form>
      {state.chatsLoaded && <div className="surveillance-choices"><span className="field-label">{t("Gruppi dalle ultime 200 chat · seleziona per compilare il campo")}</span>{available.length ? <div>{available.map(chat => <button type="button" key={chat.id} className={query === chat.id ? 'chosen' : ''} onClick={() => setQuery(chat.id)}><Users size={13} /><span>{chat.title}</span><ArrowRight size={12} /></button>)}</div> : <p>{t("Nessun gruppo corrisponde alla ricerca.")}</p>}</div>}
      <div className="surveillance-hint"><ShieldCheck size={13} /><span>{connected ? t("Puoi monitorare i gruppi di cui il tuo account è membro.") : t("Collega Telegram dalla Home. I registri già salvati restano consultabili.")}</span></div>
    </section>
    <div className="surveillance-workspace">
      <section className="panel surveillance-groups">
        <div className="surveillance-group-heading">
          <SectionTitle title={t("I tuoi gruppi")} aside={<span className="subtle-badge">{state.overview.groups.length}</span>} />
          <div className="search-field"><Search size={15} /><input aria-label={t("Cerca gruppi Surveillance")} placeholder={t("Cerca nome, username o ID…")} value={groupSearch} onChange={event => setGroupSearch(event.target.value)} /></div>
          <button type="button" className={`filter-button ${onlyActive ? 'active' : ''}`} aria-pressed={onlyActive} onClick={() => setOnlyActive(!onlyActive)}><ListFilter size={13} /> {t("Solo attivati")}</button>
        </div>
        {state.loading ? <Loading text={t("Caricamento dei gruppi…")} /> : groups.length ? <div className="surveillance-group-list">{groups.map(group => <GroupRow key={group.id} group={group} selected={state.selected === group.id} connected={connected} disabled={blocked} onSelect={() => state.select(group.id)} onToggle={value => void state.setMonitoring(group.id, value)} />)}</div> : <div className="surveillance-group-empty"><Users size={27} /><h3>{groupSearch || onlyActive ? t("Nessun gruppo trovato.") : t("Il primo gruppo parte da qui.")}</h3><p>{groupSearch || onlyActive ? t("Modifica la ricerca o rimuovi il filtro.") : t("Aggiungi un gruppo per iniziare a raccogliere i suoi eventi.")}</p></div>}
        <div className="surveillance-group-footer"><Info size={13} /> {t("Fermare un gruppo conserva i suoi registri.")}</div>
      </section>
      <LogViewer key={state.selected} group={selected} logs={logs} connected={connected} />
    </div>
  </>;
}

function GroupRow({ group, selected, connected, disabled, onSelect, onToggle }: { group: SurveillanceGroup; selected: boolean; connected: boolean; disabled: boolean; onSelect: () => void; onToggle: (value: boolean) => void }) {
  const { t, locale } = useI18n();
  return <div className={`surveillance-group-row ${selected ? 'selected' : ''}`}>
    <button type="button" className="surveillance-group-select" onClick={onSelect} aria-pressed={selected}><span className="surveillance-group-icon"><Users size={17} /></span><span><strong>{group.title}</strong><span>{group.username ? `@${group.username}` : group.id}</span><small>{group.log_files ? t("{size} di registri", { size: size(group.log_bytes, locale) }) : t("Nessun evento salvato")}</small></span></button>
    <div className="surveillance-group-control"><Toggle label={t("Monitoraggio {name}", { name: group.title })} checked={group.enabled} disabled={disabled || (!connected && !group.enabled)} onChange={onToggle} /><span>{group.enabled ? connected ? t("Attivo") : t("In pausa") : t("Fermato")}</span></div>
  </div>;
}

function LogViewer({ group, logs, connected }: { group?: SurveillanceGroup; logs: SurveillanceLogs | null; connected: boolean }) {
  const { t, locale } = useI18n();
  const [search, setSearch] = useState('');
  const [onlyEdits, setOnlyEdits] = useState(false);
  const records = useMemo(() => (logs?.records || []).filter(record =>
    (!onlyEdits || record.event === 'edited') && `${record.sender} ${record.username} ${record.text} ${record.media}`.toLocaleLowerCase().includes(search.toLocaleLowerCase())
  ), [logs, search, onlyEdits]);

  return <section className="panel surveillance-viewer">
    <div className="surveillance-viewer-heading">
      <div><span className="overline">{t("REGISTRO DEL GRUPPO")}</span><h2>{group?.title || t("Una finestra sulle tue chat.")}</h2><p>{group ? <><span className={`status-dot ${group.enabled && connected ? '' : 'offline'}`} />{group.enabled ? connected ? t("Monitoraggio attivo") : t("Attivato · Telegram scollegato") : t("Monitoraggio fermato")}<span className="viewer-id">{group.id}</span></> : t("Seleziona un gruppo per leggere i messaggi registrati.")}</p></div>
      <button className="icon-button" aria-label={t("Esporta registro Surveillance")} title={t("Esporta gli eventi visualizzati")} disabled={!records.length} onClick={() => logs && exportLogs({ ...logs, records })}><ArrowDownToLine size={18} /></button>
    </div>
    {group && <div className="surveillance-log-toolbar"><div className="search-field"><Search size={15} /><input aria-label={t("Cerca nei messaggi Surveillance")} placeholder={t("Cerca un messaggio o una persona…")} value={search} onChange={event => setSearch(event.target.value)} /></div><button type="button" className={`filter-button ${onlyEdits ? 'active' : ''}`} aria-pressed={onlyEdits} onClick={() => setOnlyEdits(!onlyEdits)}><PencilLine size={13} /> {t("Modifiche")}</button></div>}
    {!group ? <div className="surveillance-viewer-empty"><div className="surveillance-empty-art"><Radar size={42} strokeWidth={1.2} /><span /><span /></div><h3>{t("Ogni evento, al suo posto.")}</h3><p>{t("I messaggi e le modifiche appariranno qui dopo l’attivazione del monitoraggio.")}</p><div><MessageSquareText size={13} /> {t("Nuovi messaggi")} <span>·</span> <PencilLine size={13} /> {t("Modifiche")}</div></div>
      : !logs ? <Loading text={t("Caricamento del registro…")} />
        : records.length ? <div className="surveillance-records">{records.map((record, index) => <article className={`surveillance-record ${record.event === 'edited' ? 'edited' : ''}`} key={`${record.message_id}-${record.date}-${index}`}>
          <div className="surveillance-record-top"><div className="surveillance-sender-avatar">{record.sender.slice(0, 1).toLocaleUpperCase()}</div><div><strong>{record.sender}</strong><span>{record.username ? `@${record.username}` : t("Messaggio del gruppo")}</span></div><span className={`record-kind ${record.event === 'edited' ? 'edited' : ''}`}>{record.event === 'edited' ? <PencilLine size={11} /> : <MessageSquareText size={11} />}{record.event === 'edited' ? t("Modificato") : t("Nuovo")}</span><time dateTime={record.date}>{date(record.date, locale, t("Orario non disponibile"))}</time></div>
          <p>{record.text || (record.media ? t("Messaggio con allegato.") : t("Messaggio senza testo."))}</p><div className="surveillance-record-bottom">{record.media && <span><FileText size={11} />{record.media}</span>}{record.message_id && <span>#{record.message_id}</span>}</div>
        </article>)}</div>
          : <div className="surveillance-viewer-empty compact"><div className="empty-state-icon"><MessageSquareText size={27} /></div><h3>{search || onlyEdits ? t("Nessun evento corrispondente.") : t("Il registro è ancora vuoto.")}</h3><p>{search || onlyEdits ? t("Prova a cambiare ricerca o rimuovere il filtro.") : t("Surveillance raccoglie i nuovi messaggi e le modifiche mentre Melixsa è connessa.")}</p></div>}
    {logs?.skipped ? <div className="surveillance-log-note"><Info size={13} /> {t("Alcune righe incomplete o non valide sono state ignorate.")}</div> : null}
    {logs?.limited && <div className="surveillance-log-note"><Info size={13} /> {t("Vista limitata agli ultimi 100 eventi e a 2 MB di lettura.")}</div>}
    <div className="surveillance-viewer-footer"><span><Clock3 size={12} /> {t("Aggiornamento ogni 5 secondi")}</span><span>{group ? t("{count} eventi visualizzati", { count: records.length }) : t("Registri locali")}</span></div>
  </section>;
}

function Loading({ text }: { text: string }) {
  return <div className="surveillance-loading"><LoaderCircle size={21} className="spin" /><span>{text}</span></div>;
}

function size(bytes: number, locale: string) {
  if (bytes === 0) return '0 KB';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toLocaleString(locale, { maximumFractionDigits: 1 })} KB`;
  return `${(bytes / (1024 * 1024)).toLocaleString(locale, { maximumFractionDigits: 1 })} MB`;
}

function date(value: string, locale: string, unavailable: string) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? unavailable : parsed.toLocaleString(locale, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function exportLogs(logs: SurveillanceLogs) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(logs, null, 2)], { type: 'application/json' }));
  const link = document.createElement('a'); link.href = url; link.download = `surveillance-${logs.chat_id}.json`; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
