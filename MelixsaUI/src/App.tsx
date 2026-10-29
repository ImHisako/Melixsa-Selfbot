import { useState } from 'react';
import { CheckCircle2, CircleAlert, LoaderCircle, LogOut, RefreshCw, X } from 'lucide-react';
import { Layout } from './components/Layout';
import { LoginDialog } from './components/LoginDialog';
import { Button } from './components/ui';
import { useMelixsa } from './hooks/useMelixsa';
import { desktop } from './lib/bridge';
import { Activity } from './pages/Activity';
import { Home } from './pages/Home';
import { Modules } from './pages/Modules';
import { Settings } from './pages/Settings';
import { Surveillance } from './pages/Surveillance';
import type { Page } from './types';

export default function App() {
  const [page, setPage] = useState<Page>('home');
  const { data, busy, loading, notice, dismiss, act, save } = useMelixsa();
  const disabled = busy || loading || !desktop;
  const connect = () => void act('connect');
  const login = data.connection.startsWith('login_');
  return <Layout page={page} navigate={setPage} data={data} busy={busy} onConnect={connect}>
    {loading ? <div className="loading-state"><LoaderCircle size={29} className="spin" /><h2>Prepariamo il tuo spazio.</h2><p>Connessione al motore locale di Melixsa…</p></div> : <>
      {data.last_error && <div className="error-banner" role="alert"><CircleAlert size={18} /><p>{data.last_error}</p><Button variant="ghost" disabled={disabled} onClick={connect}>Riprova</Button></div>}
      {page === 'home' && <Home data={data} disabled={disabled} busy={busy} navigate={setPage} save={save} connect={connect} refresh={() => void act('refresh_profile', {}, 'Profilo aggiornato.')} />}
      {page === 'modules' && <Modules data={data} disabled={disabled} busy={busy} save={save} />}
      {page === 'surveillance' && <Surveillance connection={data.connection} disabled={disabled} />}
      {page === 'settings' && <Settings data={data} disabled={disabled} busy={busy} save={save} />}
      {page === 'activity' && <Activity data={data} />}
      {desktop && <div className="session-control"><span><span className={`status-dot ${data.connection === 'connected' ? '' : 'offline'}`} />{data.connection === 'connected' ? 'Melixsa sta lavorando per te.' : data.connection === 'connecting' ? 'Collegamento a Telegram…' : 'Le preferenze salvate saranno pronte al prossimo collegamento.'}</span><Button variant="ghost" disabled={disabled} onClick={data.connection === 'connected' || data.connection === 'connecting' || login ? () => void act('disconnect') : connect}>{data.connection === 'connected' ? <><LogOut size={14} /> Arresta Melixsa</> : <><RefreshCw size={14} />{data.connection === 'connecting' ? 'Annulla' : 'Collega Telegram'}</>}</Button></div>}
    </>}
    {notice && <div className={`toast ${notice.error ? 'toast-error' : ''}`} role={notice.error ? 'alert' : 'status'}>{notice.error ? <CircleAlert size={19} /> : <CheckCircle2 size={19} />}<span>{notice.text}</span><button className="icon-button" aria-label="Chiudi notifica" onClick={dismiss}><X size={16} /></button></div>}
    {login && <LoginDialog connection={data.connection} busy={busy} submit={act} cancel={() => void act('disconnect')} />}
  </Layout>;
}
