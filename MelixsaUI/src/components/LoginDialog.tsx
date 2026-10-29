import { useI18n } from '../i18n';
import { useEffect, useRef, useState } from 'react';
import { KeyRound, Send, X } from 'lucide-react';
import type { Connection } from '../types';
import { Button } from './ui';

export function LoginDialog({ connection, busy, submit, cancel }: { connection: Connection; busy: boolean; submit: (method: string, params: object) => Promise<boolean>; cancel: () => void }) {
  const { t } = useI18n();
  const [value, setValue] = useState('');
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { setValue(''); input.current?.focus(); }, [connection]);
  const stage = connection === 'login_phone' ? 'phone' : connection === 'login_code' ? 'code' : 'password';
  const title = { phone: t("Il tuo Telegram, qui."), code: t("Controlla Telegram."), password: t("Un ultimo passaggio.") }[stage];
  const description = { phone: t("Inserisci il tuo numero con il prefisso internazionale."), code: t("Inserisci il codice di accesso ricevuto da Telegram."), password: t("Il tuo account usa la verifica in due passaggi. Inserisci la password.") }[stage];
  return <div className="modal-backdrop"><section className="modal login-modal" role="dialog" aria-modal="true" aria-labelledby="login-title" onKeyDown={event => { if (event.key === 'Escape' && !busy) cancel(); }}><button className="icon-button modal-close" aria-label={t("Annulla accesso")} disabled={busy} onClick={cancel}><X size={18} /></button><div className="module-icon purple">{stage === 'password' ? <KeyRound size={25} /> : <Send size={25} />}</div><h2 id="login-title">{title}</h2><p>{description}</p><form onSubmit={async event => { event.preventDefault(); await submit(`login_${stage}`, { [stage]: value }); setValue(''); }}><label className="field"><span>{stage === 'phone' ? t("Numero di telefono") : stage === 'code' ? t("Codice di accesso") : 'Password'}</span><input ref={input} type={stage === 'password' ? 'password' : 'text'} inputMode={stage === 'code' ? 'numeric' : stage === 'phone' ? 'tel' : 'text'} autoComplete={stage === 'code' ? 'one-time-code' : stage === 'password' ? 'current-password' : 'tel'} placeholder={stage === 'phone' ? '+39 000 000 0000' : stage === 'code' ? '12345' : t("La tua password")} value={value} onChange={event => setValue(event.target.value.replace(stage === 'phone' ? /\s/g : /$^/, ''))} required /></label><Button type="submit" loading={busy} className="full-width">{stage === 'phone' ? t("Invia il codice") : t("Continua")}</Button></form><p className="login-note">{t("I dati di accesso restano sul tuo dispositivo.")}</p></section></div>;
}
