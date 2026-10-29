import { useI18n } from '../i18n';
import { Activity, ArrowRight, ArrowUpRight, ChevronRight, CircleUserRound, Clock3, Layers2, MessageCircle, Moon, Radio, RefreshCw, ShieldCheck, Smile, Sparkles, Zap } from 'lucide-react';
import type { Page, SettingsPatch, Snapshot } from '../types';
import { Avatar, Button, PageIntro, SectionTitle, TextLink, Toggle } from '../components/ui';

interface Props { data: Snapshot; disabled: boolean; busy: boolean; navigate: (page: Page) => void; save: (patch: SettingsPatch) => Promise<boolean>; connect: () => void; refresh: () => void }
export function Home({ data, disabled, busy, navigate, save, connect, refresh }: Props) {
  const { t, locale } = useI18n();
  const connected = data.connection === 'connected';
  const name = data.profile?.name.split(' ')[0];
  const hour = new Date().getHours();
  const greeting = hour < 13 ? t("Buongiorno") : hour < 18 ? t("Buon pomeriggio") : t("Buonasera");
  const active = [data.settings.autoreact, data.afk.enabled, data.settings.anti_login_enabled, data.settings.error_notify].filter(Boolean).length;
  return <>
    <PageIntro eyebrow={t("IL TUO CENTRO DI CONTROLLO")} title={name ? `${greeting}, ${name}` : t("Benvenuto nel tuo spazio")} description={t("Un po’ di ordine. Più possibilità. Tutto il tuo Melixsa, qui.")} action={<span className="date-label">{new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'long', year: 'numeric' }).format(new Date())}</span>} />
    <section className="hero-card">
      <div className="hero-grain" /><div className="hero-copy"><div className="hero-kicker"><span /> {t("IL TUO TELEGRAM. A MODO TUO.")}</div><h2>{t("Il tuo mondo,")}<br /><span>{t("connesso meglio.")}</span></h2><p>{t("Automazioni intelligenti, piccoli dettagli e un unico spazio per avere tutto sotto controllo.")}</p><Button loading={busy || data.connection === 'connecting'} disabled={!connected && disabled} onClick={connected ? () => navigate('modules') : connect}>{connected ? t("Esplora le automazioni") : t("Collega Telegram")}<ArrowRight size={16} /></Button><div className="hero-caption"><ShieldCheck size={13} /> {t("La tua sessione. Il tuo dispositivo. Il tuo controllo.")}</div></div>
      <div className="orbit-art" aria-hidden="true"><div className="orbit orbit-one" /><div className="orbit orbit-two" /><div className="orbit orbit-three" /><div className="orb"><Moon size={67} strokeWidth={1.25} fill="currentColor" /><Sparkles className="orb-star" size={28} /></div><div className="floating-chip chip-one"><span className="chip-symbol"><Zap size={17} /></span><div><strong>{t("Meno passaggi.")}</strong><span>{t("Più spazio per te.")}</span></div></div><div className="floating-chip chip-two"><ShieldCheck size={16} /><span>{t("Nel tuo spazio.")}</span><span className="status-dot" /></div><span className="art-spark spark-one">✦</span><span className="art-spark spark-two">+</span><span className="art-dot dot-one" /><span className="art-dot dot-two" /></div>
    </section>
    <div className="home-grid">
      <section className="panel profile-panel"><div className="panel-heading"><span className="overline">{t("PROFILO TELEGRAM")}</span><button className="icon-button" aria-label={t("Aggiorna il profilo Telegram")} disabled={!connected || disabled} onClick={refresh}><RefreshCw size={15} className={busy ? 'spin' : ''} /></button></div><div className="profile-main"><div className="profile-avatar"><Avatar profile={data.profile} size="large" /><span className={`avatar-status ${connected ? 'online' : ''}`} /></div><h2>{data.profile?.name || t("Il tuo account Telegram")}</h2><p>{data.profile?.username ? `@${data.profile.username}` : t("Un collegamento e sei a casa.")}</p><span className={`badge ${connected ? 'green' : ''}`}><span className={`status-dot ${connected ? '' : 'offline'}`} />{connected ? t("Account collegato") : data.profile ? t("Profilo salvato · offline") : t("In attesa di collegamento")}</span></div><div className="profile-detail"><span><CircleUserRound size={14} /> {t("ID Telegram")}</span><strong>{data.profile?.id || '—'}</strong></div><div className="profile-detail"><span><Clock3 size={14} /> {t("Sessione attiva")}</span><strong>{connected ? duration(data.uptime) : '—'}</strong></div><div className="profile-bottom"><ShieldCheck size={14} /><span>{data.profile?.premium ? 'Telegram Premium' : data.profile ? t("Profilo sincronizzato con Telegram") : t("I dati arrivano dal tuo account Telegram")}</span></div></section>
      <section className="quick-modules"><SectionTitle title={t("Le tue automazioni")} aside={<TextLink onClick={() => navigate('modules')}>{t("Gestisci tutte")}</TextLink>} /><div className="quick-module-grid">
        <QuickModule icon={Smile} color="purple" title="Auto React" description={t("Un tocco tuo, in ogni messaggio.")} enabled={data.settings.autoreact} disabled={disabled} onChange={value => void save({ autoreact: value })} detail={data.settings.autoreact_emojis.join('  ')} onOpen={() => navigate('modules')} />
        <QuickModule icon={Moon} color="blue" title={t("Modalità AFK")} description={t("Fai una pausa. Risponde Melixsa.")} enabled={data.afk.enabled} disabled={disabled || !connected} onChange={value => void save({ afk: { enabled: value } })} detail={t("Risposte automatiche")} onOpen={() => navigate('modules')} />
        <QuickModule icon={ShieldCheck} color="green" title={t("Protezione accessi")} description={t("Tieni d’occhio le nuove sessioni.")} enabled={data.settings.anti_login_enabled} disabled={disabled} onChange={value => void save({ anti_login_enabled: value })} detail="Anti-login" onOpen={() => navigate('modules')} />
        <QuickModule icon={Zap} color="peach" title={t("Modalità minimale")} description={t("Solo le funzioni essenziali.")} enabled={data.settings.minimal_mode} disabled={disabled} onChange={value => void save({ minimal_mode: value })} detail={t("Un’esperienza più semplice")} onOpen={() => navigate('settings')} />
      </div></section>
    </div>
    <div className="stats-strip"><div><div className="stat-icon purple"><Layers2 size={18} /></div><div><strong>{active}<span> / 4</span></strong><p>{t("Moduli configurati attivi")}</p></div></div><div><div className="stat-icon blue"><MessageCircle size={18} /></div><div><strong>{data.stats.groups}</strong><p>{t("Gruppi monitorati")}</p></div></div><div><div className="stat-icon green"><Radio size={18} /></div><div><strong>{data.stats.jobs}</strong><p>{t("Ricerche in corso")}</p></div></div><button onClick={() => navigate('activity')}><div className="stat-icon peach"><Activity size={18} /></div><div><strong>{t("Il tuo registro")}</strong><p>{t("Le ultime attività di Melixsa")}</p></div><ArrowUpRight size={19} /></button></div>
    <div className="home-bottom"><div><span className="soft-spark">✦</span><p><strong>{t("I dettagli fanno la differenza.")}</strong> {t("Personalizza prefisso, notifiche e comportamento di Melixsa.")}</p></div><button onClick={() => navigate('settings')}>{t("Apri impostazioni")} <ChevronRight size={15} /></button></div>
  </>;
}

function QuickModule({ icon: Icon, color, title, description, enabled, disabled, onChange, detail, onOpen }: { icon: typeof Smile; color: string; title: string; description: string; enabled: boolean; disabled: boolean; onChange: (value: boolean) => void; detail: string; onOpen: () => void }) {
  const { t } = useI18n();
  return <article className={`quick-module ${enabled ? 'module-active' : ''}`}><div className="quick-module-top"><div className={`module-icon ${color}`}><Icon size={20} /></div><Toggle checked={enabled} disabled={disabled} onChange={onChange} label={title} /></div><button className="module-title-button" onClick={onOpen}><h3>{title}</h3><ArrowUpRight size={14} /></button><p>{description}</p><div className="quick-module-bottom"><span>{detail}</span><span className={`module-state ${enabled ? 'on' : ''}`}>{enabled ? t("Attiva") : t("Disattiva")}</span></div></article>;
}

function duration(seconds: number) {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
}
