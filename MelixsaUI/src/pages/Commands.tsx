import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { BookOpen, Check, CircleAlert, Copy, Keyboard, Search, Star, X } from 'lucide-react';
import { Button, PageIntro } from '../components/ui';
import bundledCatalog from '../catalog/commands.json';
import { useI18n } from '../i18n';
import { commandText } from '../i18n/commandText';
import { desktop, request } from '../lib/bridge';
import { commandSyntax, favoritesStorageKey, findCommands, parseFavorites } from '../lib/commands';
import type { CommandCatalog, SelfbotCommand } from '../types';
import './commands.css';

export function Commands({ prefix, focusRequest }: { prefix: string; focusRequest: number }) {
  const { t, language, locale } = useI18n();
  const [catalog, setCatalog] = useState<CommandCatalog>(bundledCatalog);
  const [catalogError, setCatalogError] = useState(false);
  const [query, setQuery] = useState('');
  const [category, setCategory] = useState('all');
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [favorites, setFavorites] = useState(() => {
    try { return parseFavorites(localStorage.getItem(favoritesStorageKey)); } catch { return new Set<string>(); }
  });
  const [copyNotice, setCopyNotice] = useState<{ command: string; error: boolean } | null>(null);
  const search = useRef<HTMLInputElement>(null);
  const localize = useCallback((text: string) => commandText(language, text), [language]);

  useEffect(() => { search.current?.focus(); search.current?.select(); }, [focusRequest]);
  useEffect(() => {
    try { localStorage.setItem(favoritesStorageKey, JSON.stringify([...favorites])); } catch { /* Session favourites still work. */ }
  }, [favorites]);
  useEffect(() => {
    if (!desktop) return;
    let cancelled = false;
    request<CommandCatalog>('command_catalog').then(next => {
      if (!cancelled) setCatalog(next);
    }).catch(() => { if (!cancelled) setCatalogError(true); });
    return () => { cancelled = true; };
  }, []);
  useEffect(() => {
    if (!copyNotice) return;
    const timer = setTimeout(() => setCopyNotice(null), 4500);
    return () => clearTimeout(timer);
  }, [copyNotice]);

  const sections = useMemo(() => findCommands(catalog, { query, prefix, category, favoritesOnly, favorites, localize: text => commandText('en', text) }), [catalog, query, prefix, category, favoritesOnly, favorites]);
  const total = catalog.categories.reduce((count, section) => count + section.commands.length, 0);
  const matches = sections.reduce((count, section) => count + section.commands.length, 0);
  const favoriteCount = catalog.categories.reduce((count, section) => count + section.commands.filter(command => favorites.has(command.name)).length, 0);
  const toggleFavorite = (name: string) => setFavorites(previous => {
    const next = new Set(previous);
    if (next.has(name)) next.delete(name); else next.add(name);
    return next;
  });
  const copy = async (syntax: string) => {
    try {
      await navigator.clipboard.writeText(syntax);
      setCopyNotice({ command: syntax, error: false });
    } catch {
      setCopyNotice({ command: syntax, error: true });
    }
  };
  const reset = () => { setQuery(''); setCategory('all'); setFavoritesOnly(false); search.current?.focus(); };

  return <>
    <PageIntro eyebrow={t('SCORCIATOIE E COMANDI')} title={t('Trova il comando giusto.')} description={t('Tutti i comandi del selfbot, organizzati per sezione e pronti da copiare.')}
      action={<span className="command-total"><BookOpen size={15} />{t('{count} comandi · {categories} sezioni', { count: total.toLocaleString(locale), categories: catalog.categories.length })}</span>} />
    <div className="command-toolbar panel">
      <div className="search-field"><Search size={18} /><input ref={search} aria-label={t('Cerca comandi')} placeholder={t('Cerca nome, alias, descrizione o categoria…')} value={query} maxLength={200} onChange={event => setQuery(event.target.value)} onKeyDown={event => { if (event.key === 'Escape') setQuery(''); }} />{query && <button className="icon-button" aria-label={t('Cancella ricerca')} onClick={() => { setQuery(''); search.current?.focus(); }}><X size={15} /></button>}<kbd>Ctrl K</kbd></div>
      <button type="button" className={`filter-button ${favoritesOnly ? 'active' : ''}`} aria-pressed={favoritesOnly} onClick={() => setFavoritesOnly(!favoritesOnly)}><Star size={15} />{t('Preferiti')}<span>{favoriteCount}</span></button>
    </div>
    <p className="command-hint"><Keyboard size={14} />{t('Copia un comando e incollalo nella chat Telegram in cui vuoi usarlo. Le stelle salvano le tue scorciatoie.')}</p>
    {catalogError && <div className="info-banner" role="status"><CircleAlert size={16} /><p>{t('Il motore non ha restituito il catalogo. Stai consultando la copia inclusa nell’app.')}</p></div>}
    {copyNotice && <div className={`command-copy-notice ${copyNotice.error ? 'error' : ''}`} role={copyNotice.error ? 'alert' : 'status'}>{copyNotice.error ? <CircleAlert size={15} /> : <Check size={15} />}<span>{copyNotice.error ? t('Copia non disponibile. Seleziona la sintassi e premi Ctrl+C.') : t('Copiato: {command}', { command: copyNotice.command })}</span></div>}
    <div className="command-layout">
      <nav className="command-categories" aria-label={t('Sezioni dei comandi')}>
        <button className={category === 'all' ? 'active' : ''} aria-pressed={category === 'all'} onClick={() => setCategory('all')}><BookOpen size={16} /><span>{t('Tutte le sezioni')}</span><small>{total}</small></button>
        {catalog.categories.map(section => <button key={section.id} className={category === section.id ? 'active' : ''} aria-pressed={category === section.id} onClick={() => setCategory(section.id)}><span>{localize(section.title)}</span><small>{section.commands.length}</small></button>)}
      </nav>
      <div className="command-results">
        <div className="command-results-heading"><span aria-live="polite">{t(matches === 1 ? '{count} comando trovato' : '{count} comandi trovati', { count: matches })}</span>{(query || category !== 'all' || favoritesOnly) && <button className="text-link" onClick={reset}>{t('Azzera filtri')}</button>}</div>
        {sections.length ? sections.map(section => <section className="command-section" key={section.id} aria-labelledby={`commands-${section.shortcut}`}>
          <div className="command-section-heading"><div><h2 id={`commands-${section.shortcut}`}>{localize(section.title)}</h2><span>{section.commands.length}</span></div><button className="text-link" title={t('Copia menu Telegram')} onClick={() => void copy(`${prefix}${section.shortcut}`)}><Copy size={13} /><code>{prefix}{section.shortcut}</code></button></div>
          <div className="command-grid">{section.commands.map(command => <CommandCard key={command.name} command={command} prefix={prefix} favorite={favorites.has(command.name)} toggleFavorite={() => toggleFavorite(command.name)} localize={localize} copy={copy} />)}</div>
        </section>) : <div className="panel empty-state"><div className="empty-state-icon">{favoritesOnly ? <Star size={28} /> : <Search size={28} />}</div><h2>{favoritesOnly && !favoriteCount ? t('Le tue scorciatoie iniziano qui.') : t('Nessun comando trovato.')}</h2><p>{favoritesOnly && !favoriteCount ? t('Premi la stella su un comando per ritrovarlo nei Preferiti.') : t('Prova un altro nome, alias o descrizione, oppure azzera i filtri.')}</p><Button variant="secondary" onClick={reset}>{t('Mostra tutti i comandi')}</Button></div>}
      </div>
    </div>
  </>;
}

function CommandCard({ command, prefix, favorite, toggleFavorite, localize, copy }: { command: SelfbotCommand; prefix: string; favorite: boolean; toggleFavorite: () => void; localize: (text: string) => string; copy: (syntax: string) => Promise<void> }) {
  const { t } = useI18n();
  const displayCommand = { ...command, usage: localize(command.usage) };
  const syntax = commandSyntax(displayCommand, prefix);
  return <article className="panel command-card">
    <div className="command-card-heading"><h3>{prefix}{command.name}</h3><button className={`icon-button command-star ${favorite ? 'selected' : ''}`} aria-label={t(favorite ? 'Rimuovi {command} dai preferiti' : 'Aggiungi {command} ai preferiti', { command: command.name })} aria-pressed={favorite} onClick={toggleFavorite}><Star size={16} fill={favorite ? 'currentColor' : 'none'} /></button></div>
    <p>{localize(command.description)}</p>
    <div className="command-syntax"><input readOnly aria-label={t('Sintassi di {command}', { command: command.name })} value={syntax} onFocus={event => event.currentTarget.select()} /><button className="icon-button" aria-label={t('Copia {command}', { command: command.name })} title={t('Copia comando')} onClick={() => void copy(syntax)}><Copy size={15} /></button></div>
    {command.aliases.length > 0 && <div className="command-aliases"><span>{t('Alias')}</span>{command.aliases.map(alias => <button key={alias} title={t('Copia alias {alias}', { alias })} aria-label={t('Copia alias {alias}', { alias })} onClick={() => void copy(commandSyntax(displayCommand, prefix, alias))}>{prefix}{alias}</button>)}</div>}
    <details className="command-details"><summary>{t('Dettagli e utilizzo')}</summary><p>{localize(command.details)}</p></details>
  </article>;
}
