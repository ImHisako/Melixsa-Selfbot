import { Activity, ArrowUpRight, ChevronRight, CircleHelp, Command, House, Layers2, LockKeyhole, PanelLeftClose, Radar, Settings2, ShieldCheck, Sparkles } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { desktop } from '../lib/bridge';
import type { Page, Snapshot } from '../types';
import { Avatar, Brand, Button } from './ui';

const navigation: { id: Page; label: string; icon: typeof House; group: string }[] = [
  { id: 'home', label: 'Home', icon: House, group: 'IL TUO SPAZIO' },
  { id: 'modules', label: 'Automazioni', icon: Layers2, group: 'IL TUO SPAZIO' },
  { id: 'surveillance', label: 'Surveillance', icon: Radar, group: 'IL TUO SPAZIO' },
  { id: 'settings', label: 'Impostazioni', icon: Settings2, group: 'SISTEMA' },
  { id: 'activity', label: 'Attività', icon: Activity, group: 'SISTEMA' },
];

export function Layout({ page, navigate, data, busy, onConnect, children }: { page: Page; navigate: (page: Page) => void; data: Snapshot; busy: boolean; onConnect: () => void; children: ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [help, setHelp] = useState(false);
  const connected = data.connection === 'connected';
  const connecting = data.connection === 'connecting';
  return <div className={`app-shell ${collapsed ? 'sidebar-collapsed' : ''}`}>
    <aside className="sidebar">
      <div className="sidebar-brand"><Brand compact={collapsed} /><button className="icon-button collapse-button" aria-label="Riduci o espandi menu" onClick={() => setCollapsed(!collapsed)}><PanelLeftClose size={17} /></button></div>
      <div className="workspace"><div className="workspace-icon"><Sparkles size={17} /></div><div><strong>Personal workspace</strong><span>Il tuo universo, in ordine.</span></div><LockKeyhole size={13} className="muted" /></div>
      <nav aria-label="Navigazione principale">{navigation.map((item, index) => <div key={item.id}>{(index === 0 || item.group !== navigation[index - 1].group) && <div className="nav-group">{item.group}</div>}<button className={`nav-item ${page === item.id ? 'active' : ''}`} title={item.label} aria-current={page === item.id ? 'page' : undefined} onClick={() => navigate(item.id)}><item.icon size={19} /><span>{item.label}</span>{item.id === 'modules' && <span className="nav-count">4</span>}{page === item.id && <span className="nav-indicator" />}</button></div>)}</nav>
      <div className="sidebar-bottom"><div className="local-card"><div className="local-icon"><ShieldCheck size={18} /></div><strong>Il controllo resta tuo.</strong><p>Sessione e preferenze rimangono su questo dispositivo.</p><span><span className="status-dot" /> Spazio locale</span></div>
      <button className="sidebar-help" onClick={() => setHelp(true)}><CircleHelp size={17} /><span>Piccola guida</span><ArrowUpRight size={14} /></button>
      <button className="account-button" onClick={() => navigate('home')}><Avatar profile={data.profile} size="small" /><div><strong>{data.profile?.name || 'Il tuo account'}</strong><span>{data.profile?.username ? `@${data.profile.username}` : 'Collega il tuo Telegram'}</span></div><ChevronRight size={15} /></button></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div className="breadcrumb">Workspace <ChevronRight size={13} /><strong>{navigation.find(item => item.id === page)?.label}</strong></div><div className="topbar-right"><span className={`connection-label ${connected ? 'connected' : ''}`}><span className={`status-dot ${connected ? '' : 'offline'}`} />{connected ? 'Telegram connesso' : connecting ? 'Connessione in corso' : 'Telegram scollegato'}</span><span className="topbar-divider" /><button className="icon-button" aria-label="Apri la guida" onClick={() => setHelp(true)}><Command size={17} /></button><Avatar profile={data.profile} size="small" /></div></header>
      {!desktop && <div className="preview-banner"><Sparkles size={14} /> Anteprima dell’interfaccia · Apri Melixsa Desktop per usare i dati reali.</div>}
      <main id="main-content" className="main-content" key={page}>{children}</main>
      <footer className="app-footer"><span><span className="tiny-orbit" /> Fatto per il tuo spazio.</span><span>Melixsa Desktop <span className="footer-dot">·</span> v0.1.0</span></footer>
    </div>
    {help && <div className="modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) setHelp(false); }}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="help-title"><div className="module-icon purple"><Sparkles size={23} /></div><h2 id="help-title">Benvenuto nel tuo spazio.</h2><p>Collega Telegram dalla Home: Melixsa userà la sessione già salvata. Al primo accesso potrai inserire numero, codice e password direttamente nell’app.</p><p>In Automazioni trovi autoreact e AFK. Le Impostazioni vengono salvate e sono condivise con i comandi Telegram. AFK vale per la sessione corrente.</p><p className="help-note">Avvia una sola istanza di Melixsa alla volta. Prima di collegare l’app, chiudi un eventuale avvio da run.cmd.</p><div className="modal-actions"><Button variant="secondary" onClick={() => setHelp(false)}>Ho capito</Button>{!connected && <Button loading={busy} onClick={() => { setHelp(false); onConnect(); }}>Collega Telegram</Button>}</div></section></div>}
  </div>;
}
