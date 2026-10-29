import { Activity, ArrowRight, ArrowUpRight, ChevronRight, CircleUserRound, Clock3, Layers2, MessageCircle, Moon, Radio, RefreshCw, ShieldCheck, Smile, Sparkles, Zap } from 'lucide-react';
import type { Page, SettingsPatch, Snapshot } from '../types';
import { Avatar, Button, PageIntro, SectionTitle, TextLink, Toggle } from '../components/ui';

interface Props { data: Snapshot; disabled: boolean; busy: boolean; navigate: (page: Page) => void; save: (patch: SettingsPatch) => Promise<boolean>; connect: () => void; refresh: () => void }
export function Home({ data, disabled, busy, navigate, save, connect, refresh }: Props) {
  const connected = data.connection === 'connected';
  const name = data.profile?.name.split(' ')[0];
  const hour = new Date().getHours();
  const greeting = hour < 13 ? 'Buongiorno' : hour < 18 ? 'Buon pomeriggio' : 'Buonasera';
  const active = [data.settings.autoreact, data.afk.enabled, data.settings.anti_login_enabled, data.settings.error_notify].filter(Boolean).length;
  return <>
    <PageIntro eyebrow="IL TUO CENTRO DI CONTROLLO" title={name ? `${greeting}, ${name}` : 'Benvenuto nel tuo spazio'} description="Un po’ di ordine. Più possibilità. Tutto il tuo Melixsa, qui." action={<span className="date-label">{new Intl.DateTimeFormat('it-IT', { day: 'numeric', month: 'long', year: 'numeric' }).format(new Date())}</span>} />
    <section className="hero-card">
      <div className="hero-grain" /><div className="hero-copy"><div className="hero-kicker"><span /> IL TUO TELEGRAM. A MODO TUO.</div><h2>Il tuo mondo,<br /><span>connesso meglio.</span></h2><p>Automazioni intelligenti, piccoli dettagli e un unico spazio per avere tutto sotto controllo.</p><Button loading={busy || data.connection === 'connecting'} disabled={!connected && disabled} onClick={connected ? () => navigate('modules') : connect}>{connected ? 'Esplora le automazioni' : 'Collega Telegram'}<ArrowRight size={16} /></Button><div className="hero-caption"><ShieldCheck size={13} /> La tua sessione. Il tuo dispositivo. Il tuo controllo.</div></div>
      <div className="orbit-art" aria-hidden="true"><div className="orbit orbit-one" /><div className="orbit orbit-two" /><div className="orbit orbit-three" /><div className="orb"><Moon size={67} strokeWidth={1.25} fill="currentColor" /><Sparkles className="orb-star" size={28} /></div><div className="floating-chip chip-one"><span className="chip-symbol"><Zap size={17} /></span><div><strong>Meno passaggi.</strong><span>Più spazio per te.</span></div></div><div className="floating-chip chip-two"><ShieldCheck size={16} /><span>Nel tuo spazio.</span><span className="status-dot" /></div><span className="art-spark spark-one">✦</span><span className="art-spark spark-two">+</span><span className="art-dot dot-one" /><span className="art-dot dot-two" /></div>
    </section>
    <div className="home-grid">
      <section className="panel profile-panel"><div className="panel-heading"><span className="overline">PROFILO TELEGRAM</span><button className="icon-button" aria-label="Aggiorna il profilo Telegram" disabled={!connected || disabled} onClick={refresh}><RefreshCw size={15} className={busy ? 'spin' : ''} /></button></div><div className="profile-main"><div className="profile-avatar"><Avatar profile={data.profile} size="large" /><span className={`avatar-status ${connected ? 'online' : ''}`} /></div><h2>{data.profile?.name || 'Il tuo account Telegram'}</h2><p>{data.profile?.username ? `@${data.profile.username}` : 'Un collegamento e sei a casa.'}</p><span className={`badge ${connected ? 'green' : ''}`}><span className={`status-dot ${connected ? '' : 'offline'}`} />{connected ? 'Account collegato' : data.profile ? 'Profilo salvato · offline' : 'In attesa di collegamento'}</span></div><div className="profile-detail"><span><CircleUserRound size={14} /> ID Telegram</span><strong>{data.profile?.id || '—'}</strong></div><div className="profile-detail"><span><Clock3 size={14} /> Sessione attiva</span><strong>{connected ? duration(data.uptime) : '—'}</strong></div><div className="profile-bottom"><ShieldCheck size={14} /><span>{data.profile?.premium ? 'Telegram Premium' : data.profile ? 'Profilo sincronizzato con Telegram' : 'I dati arrivano dal tuo account Telegram'}</span></div></section>
      <section className="quick-modules"><SectionTitle title="Le tue automazioni" aside={<TextLink onClick={() => navigate('modules')}>Gestisci tutte</TextLink>} /><div className="quick-module-grid">
        <QuickModule icon={Smile} color="purple" title="Auto React" description="Un tocco tuo, in ogni messaggio." enabled={data.settings.autoreact} disabled={disabled} onChange={value => void save({ autoreact: value })} detail={data.settings.autoreact_emojis.join('  ')} onOpen={() => navigate('modules')} />
        <QuickModule icon={Moon} color="blue" title="Modalità AFK" description="Fai una pausa. Risponde Melixsa." enabled={data.afk.enabled} disabled={disabled || !connected} onChange={value => void save({ afk: { enabled: value } })} detail="Risposte automatiche" onOpen={() => navigate('modules')} />
        <QuickModule icon={ShieldCheck} color="green" title="Protezione accessi" description="Tieni d’occhio le nuove sessioni." enabled={data.settings.anti_login_enabled} disabled={disabled} onChange={value => void save({ anti_login_enabled: value })} detail="Anti-login" onOpen={() => navigate('modules')} />
        <QuickModule icon={Zap} color="peach" title="Modalità minimale" description="Solo le funzioni essenziali." enabled={data.settings.minimal_mode} disabled={disabled} onChange={value => void save({ minimal_mode: value })} detail="Un’esperienza più semplice" onOpen={() => navigate('settings')} />
      </div></section>
    </div>
    <div className="stats-strip"><div><div className="stat-icon purple"><Layers2 size={18} /></div><div><strong>{active}<span> / 4</span></strong><p>Moduli configurati attivi</p></div></div><div><div className="stat-icon blue"><MessageCircle size={18} /></div><div><strong>{data.stats.groups}</strong><p>Gruppi monitorati</p></div></div><div><div className="stat-icon green"><Radio size={18} /></div><div><strong>{data.stats.jobs}</strong><p>Ricerche in corso</p></div></div><button onClick={() => navigate('activity')}><div className="stat-icon peach"><Activity size={18} /></div><div><strong>Il tuo registro</strong><p>Le ultime attività di Melixsa</p></div><ArrowUpRight size={19} /></button></div>
    <div className="home-bottom"><div><span className="soft-spark">✦</span><p><strong>I dettagli fanno la differenza.</strong> Personalizza prefisso, notifiche e comportamento di Melixsa.</p></div><button onClick={() => navigate('settings')}>Apri impostazioni <ChevronRight size={15} /></button></div>
  </>;
}

function QuickModule({ icon: Icon, color, title, description, enabled, disabled, onChange, detail, onOpen }: { icon: typeof Smile; color: string; title: string; description: string; enabled: boolean; disabled: boolean; onChange: (value: boolean) => void; detail: string; onOpen: () => void }) {
  return <article className={`quick-module ${enabled ? 'module-active' : ''}`}><div className="quick-module-top"><div className={`module-icon ${color}`}><Icon size={20} /></div><Toggle checked={enabled} disabled={disabled} onChange={onChange} label={title} /></div><button className="module-title-button" onClick={onOpen}><h3>{title}</h3><ArrowUpRight size={14} /></button><p>{description}</p><div className="quick-module-bottom"><span>{detail}</span><span className={`module-state ${enabled ? 'on' : ''}`}>{enabled ? 'Attiva' : 'Disattiva'}</span></div></article>;
}

function duration(seconds: number) {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}
