import { useEffect, useRef, useState } from 'react';
import { Archive, ArrowDown, Check, CircleAlert, LoaderCircle, MessageCircle, MessageSquareText, RefreshCw, Search, Send, Type } from 'lucide-react';
import { Button, PageIntro } from '../components/ui';
import { ChatAvatar, ProfilePhotoDialog } from '../components/ChatAvatar';
import { useChats } from '../hooks/useChats';
import { useChatPhotos } from '../hooks/useChatPhotos';
import { useI18n } from '../i18n';
import { desktop } from '../lib/bridge';
import { messageLimit, textStyles, transformText } from '../lib/textStyles';
import type { Connection, TelegramChat } from '../types';
import './chats.css';

type Draft = { text: string; style: string };
const emptyDraft: Draft = { text: '', style: 'plain' };
type ChatFilter = 'all' | 'groups' | 'private' | 'channels';
const group = (chat: TelegramChat) => ['group', 'supergroup'].includes(chat.kind);

export function Chats({ connection, disabled }: { connection: Connection; disabled: boolean }) {
  const { t, localize, locale } = useI18n();
  const state = useChats(connection);
  const avatars = useChatPhotos(connection);
  const [photoPreview, setPhotoPreview] = useState<{ id: string; name: string } | null>(null);
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<ChatFilter>('all');
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [atBottom, setAtBottom] = useState(true);
  const listRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<{ height: number; top: number } | null>(null);
  const chat = state.chats.find(item => item.id === state.selected);
  const draft = drafts[state.selected] ?? emptyDraft;
  const preview = transformText(draft.text, draft.style);
  const style = textStyles.find(item => item.id === draft.style)!;
  const connected = desktop && connection === 'connected';
  const canSend = connected && !disabled && !state.sending && !!draft.text.trim() && preview.length <= messageLimit;
  const search = query.trim().toLocaleLowerCase().replace(/^@/, '');
  const chats = state.chats.filter(item =>
    (filter === 'all' || (filter === 'groups' && group(item)) || (filter === 'private' && ['private', 'bot'].includes(item.kind)) || (filter === 'channels' && item.kind === 'channel')) &&
    `${item.title} ${item.username} ${item.id}`.toLocaleLowerCase().includes(search));
  const chatKind = (item: TelegramChat) => group(item) ? t('Gruppo') : item.kind === 'channel' ? t('Canale') : item.kind === 'bot' ? 'Bot' : t('Chat privata');
  const formatDate = (value: string | null) => value ? new Date(value).toLocaleString(locale, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';
  const updateDraft = (patch: Partial<Draft>) => setDrafts(previous => ({ ...previous, [state.selected]: { ...(previous[state.selected] ?? emptyDraft), ...patch } }));
  const openPhoto = (id: string, name: string) => setPhotoPreview({ id, name });
  const avatar = (id: string, name: string, kind = 'private', small = false) => <ChatAvatar id={id} name={name} kind={kind} small={small} photo={avatars.photos[id]?.photo ?? null} observe={avatars.observe} open={openPhoto} />;

  useEffect(() => { setAtBottom(true); scrollRef.current = null; }, [state.selected]);
  useEffect(() => { if (state.readError) scrollRef.current = null; }, [state.readError]);
  useEffect(() => { if (!connected) setPhotoPreview(null); }, [connected]);
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    if (scrollRef.current) {
      list.scrollTop = scrollRef.current.top + list.scrollHeight - scrollRef.current.height;
      scrollRef.current = null;
    } else if (atBottom) list.scrollTop = list.scrollHeight;
  }, [state.messages, atBottom]);

  async function submit() {
    if (!canSend || !chat) return;
    const target = chat.id;
    const submitted = draft.text;
    const sent = await state.send(target, submitted, draft.style);
    if (sent) {
      setDrafts(previous => previous[target]?.text === submitted ? { ...previous, [target]: { ...previous[target], text: '' } } : previous);
      setAtBottom(true);
    }
  }

  return <div className="chats-page">
    <PageIntro eyebrow={t('IL TUO SPAZIO')} title={t('Chat')} description={t('Le tue conversazioni, con il tuo stile. Leggi e scrivi direttamente da Melixsa.')} action={<Button variant="secondary" disabled={!connected || disabled} loading={state.listing} onClick={() => void state.refreshDialogs().then(avatars.refresh)}><RefreshCw size={14} />{t('Aggiorna chat')}</Button>} />
    {!connected && <div className="chat-connection-note"><MessageCircle size={18} /><span>{t('Collega Telegram dalla Home per vedere gruppi, canali e chat private.')}</span></div>}
    <div className="chat-workspace panel">
      <aside className="chat-sidebar" aria-label={t('Conversazioni')}>
        <div className="chat-sidebar-heading"><h2>{t('Conversazioni')}</h2><span>{state.chats.length.toLocaleString(locale)}{state.dialogsMore ? '+' : ''}</span></div>
        <label className="chat-search"><Search size={15} /><input aria-label={t('Cerca una chat')} placeholder={t('Cerca nome, username o ID…')} value={query} onChange={event => setQuery(event.target.value)} /></label>
        <div className="chat-filters" aria-label={t('Filtra conversazioni')}>{([
          ['all', t('Tutte')], ['groups', t('Gruppi')], ['private', t('Private')], ['channels', t('Canali')],
        ] as const).map(([value, label]) => <button key={value} aria-pressed={filter === value} className={filter === value ? 'active' : ''} onClick={() => setFilter(value)}>{label}</button>)}</div>
        {state.listError && <div className="chat-inline-error" role="alert">{localize(state.listError)}</div>}
        <div className="chat-dialog-list">
          {chats.map(item => <div key={item.id} className={`chat-dialog ${item.id === state.selected ? 'selected' : ''}`}>
            {avatar(item.id, item.title, item.kind)}
            <button className="chat-dialog-select" aria-current={item.id === state.selected ? 'true' : undefined} onClick={() => state.select(item.id)}>
            <span className="chat-dialog-copy"><strong>{item.title}</strong><span>{item.preview || (item.username ? `@${item.username}` : chatKind(item))}</span><small>{chatKind(item)}{item.archived && <> · <Archive size={10} /> {t('Archiviata')}</>}</small></span>
            {item.unread > 0 && <span className="chat-unread" title={t('Messaggi non letti')}>{item.unread > 99 ? '99+' : item.unread}</span>}
            </button>
          </div>)}
          {!chats.length && <div className="chat-list-empty">{state.listing ? <LoaderCircle className="spin" size={21} /> : <MessageSquareText size={25} />}<p>{state.listing ? t('Caricamento conversazioni…') : !connected ? t('Le tue chat appariranno qui.') : t('Nessuna conversazione trovata.')}</p>{search && state.dialogsMore && <p>{t('Carica altre chat per estendere la ricerca.')}</p>}</div>}
          {state.dialogsMore && <Button variant="ghost" className="chat-more" loading={state.listing} disabled={disabled || !connected} onClick={() => void state.loadMoreDialogs()}>{t('Carica altre chat')}</Button>}
        </div>
        <div className="chat-sidebar-footer">{t('Chat principali e archiviate. Lo storico si carica da Telegram.')}</div>
      </aside>
      <section className="chat-conversation" aria-label={t('Messaggi')}>
        {!chat ? <div className="chat-welcome"><div className="chat-welcome-icon"><MessageSquareText size={36} /><Type size={18} /></div><h2>{t('Ogni chat, il tuo carattere.')}</h2><p>{t('Scegli una conversazione per leggere i messaggi e scrivere con uno stile Unicode personalizzato.')}</p><span><span className={`status-dot ${connected ? '' : 'offline'}`} />{connected ? t('Telegram connesso') : t('Telegram scollegato')}</span></div> : <>
          <header className="chat-heading">{avatar(chat.id, chat.title, chat.kind)}<div><h2>{chat.title}</h2><p>{chatKind(chat)} · {chat.username ? `@${chat.username} · ` : ''}{chat.id}</p></div><Button variant="ghost" aria-label={t('Aggiorna messaggi')} title={t('Aggiorna messaggi')} disabled={!connected || disabled || state.reading || state.sending} onClick={() => { state.refreshMessages(); avatars.refresh(); }}><RefreshCw size={15} className={state.reading ? 'spin' : ''} /></Button></header>
          {state.readError && <div className="chat-inline-error" role="alert"><CircleAlert size={15} />{localize(state.readError)}<Button variant="ghost" disabled={state.reading || !connected} onClick={state.refreshMessages}>{t('Riprova')}</Button></div>}
          <div className="chat-messages" ref={listRef} onScroll={event => { const element = event.currentTarget; setAtBottom(element.scrollHeight - element.scrollTop - element.clientHeight < 90); }}>
            {state.historyMore && <Button variant="ghost" className="chat-older" disabled={state.reading || state.sending || disabled || !connected} onClick={() => { if (listRef.current) scrollRef.current = { height: listRef.current.scrollHeight, top: listRef.current.scrollTop }; void state.loadOlder(); }}>{t('Messaggi precedenti')}</Button>}
            {state.reading && !state.messages.length && <div className="chat-list-empty"><LoaderCircle className="spin" size={24} /><p>{t('Caricamento messaggi…')}</p></div>}
            {!state.reading && !state.messages.length && !state.readError && <div className="chat-list-empty"><MessageCircle size={27} /><p>{t('Nessun messaggio in questa chat. Scrivi il primo.')}</p></div>}
            {state.messages.map(message => <article key={message.id} className={`chat-bubble ${message.outgoing ? 'outgoing' : ''} ${message.service ? 'service' : ''}`}>
              <div className="chat-message-sender">{!message.service && avatar(message.sender_id, message.sender || t('Utente senza nome'), message.sender_id.startsWith('-') ? 'channel' : 'private', true)}<strong>{message.outgoing ? t('Tu') : message.sender || t('Utente senza nome')}</strong>{message.reply_to_id && <span className="chat-reply-id">↩ #{message.reply_to_id}</span>}</div>
              {message.media && <span className="chat-media-label">{t('Allegato')}: {message.media}</span>}
              {message.text ? <p>{message.text}</p> : <p className="chat-message-placeholder">{message.service ? t('Messaggio di servizio') : t('Contenuto non testuale')}</p>}
              <div className="chat-message-meta">{message.edited && <span>{t('modificato')}</span>}<time dateTime={message.date ?? undefined}>{formatDate(message.date)}</time>{message.outgoing && <Check size={12} />}</div>
            </article>)}
          </div>
          {!atBottom && <button className="chat-to-bottom" aria-label={t('Vai agli ultimi messaggi')} onClick={() => setAtBottom(true)}><ArrowDown size={16} />{t('Ultimi messaggi')}</button>}
          <form className="chat-composer" onSubmit={event => { event.preventDefault(); void submit(); }}>
            <div className="chat-style-row"><label htmlFor="chat-text-style"><Type size={15} />{t('Stile del testo')}</label><select id="chat-text-style" value={draft.style} onChange={event => updateDraft({ style: event.target.value })}>{textStyles.map(item => <option key={item.id} value={item.id}>{item.id === 'plain' ? t('Normale') : item.label}</option>)}</select><span>{t('Anteprima dal vivo')}</span></div>
            {style.invisible && <p className="chat-style-note">{t('Questo stile aggiunge caratteri poco visibili e può cambiare ricerca e copia del testo.')}</p>}
            <label className="sr-only" htmlFor="chat-message">{t('Scrivi un messaggio')}</label><textarea id="chat-message" placeholder={t('Scrivi un messaggio…')} value={draft.text} maxLength={messageLimit} disabled={!connected || disabled} onChange={event => updateDraft({ text: event.target.value })} onKeyDown={event => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter' && !event.nativeEvent.isComposing) { event.preventDefault(); void submit(); } }} />
            {draft.text && <div className={`chat-style-preview ${preview.length > messageLimit ? 'over-limit' : ''}`}><span>{t('Testo che verrà inviato')}</span><p>{preview}</p></div>}
            {state.sendError && <div className="chat-inline-error" role="alert">{localize(state.sendError)}</div>}
            <div className="chat-composer-bottom"><div><span className={preview.length > messageLimit ? 'over-limit' : ''}>{preview.length.toLocaleString(locale)} / {messageLimit.toLocaleString(locale)}</span><small>{preview.length > messageLimit ? t('Riduci il testo o scegli uno stile più breve.') : t('Ctrl+Invio per inviare · Invio per andare a capo')}</small></div><Button type="submit" disabled={!canSend} loading={state.sending}><Send size={14} />{t('Invia messaggio')}</Button></div>
            <p className="chat-send-note">{t('Invii dal tuo account Telegram. La bozza resta disponibile se l’invio non riesce.')}</p>
          </form>
        </>}
      </section>
    </div>
    {photoPreview && <ProfilePhotoDialog key={photoPreview.id} id={photoPreview.id} name={photoPreview.name} thumbnail={avatars.photos[photoPreview.id]?.photo ?? null} close={() => setPhotoPreview(null)} />}
  </div>;
}
