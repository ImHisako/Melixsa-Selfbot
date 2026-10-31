import { useI18n } from '../i18n';
import { useState } from 'react';
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { ArrowUpRight, Check, LoaderCircle, Moon, Sparkles } from 'lucide-react';
import type { Profile } from '../types';

export function Brand({ compact = false }: { compact?: boolean }) {
  return <div className="brand"><div className="brand-mark"><Moon size={23} fill="currentColor" /><Sparkles size={13} className="brand-star" /></div>{!compact && <span>melixsa<span className="brand-period">.</span></span>}</div>;
}

export function Avatar({ profile, size = 'normal' }: { profile: Pick<Profile, 'name' | 'photo'> | null; size?: 'small' | 'normal' | 'large' }) {
  const { t } = useI18n();
  const [failedPhoto, setFailedPhoto] = useState<string | null>(null);
  const initials = profile?.name.split(' ').filter(Boolean).slice(0, 2).map(part => part[0]).join('') || 'M';
  return <div className={`avatar avatar-${size}`}>{profile?.photo && profile.photo !== failedPhoto ? <img src={profile.photo} alt={t("Foto profilo di {name}", { name: profile.name })} onError={() => setFailedPhoto(profile.photo)} /> : <span>{initials}</span>}</div>;
}

export function Toggle({ checked, onChange, label, disabled = false }: { checked: boolean; onChange: (value: boolean) => void; label: string; disabled?: boolean }) {
  return <button type="button" role="switch" aria-checked={checked} aria-label={label} className={`toggle ${checked ? 'is-on' : ''}`} disabled={disabled} onClick={() => onChange(!checked)}><span>{checked && <Check size={10} strokeWidth={3} />}</span></button>;
}

export function Button({ children, variant = 'primary', loading = false, className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { children: ReactNode; variant?: 'primary' | 'secondary' | 'ghost'; loading?: boolean }) {
  return <button className={`button button-${variant} ${className}`} {...props} disabled={props.disabled || loading}>{loading && <LoaderCircle size={15} className="spin" />}{children}</button>;
}

export function PageIntro({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: ReactNode }) {
  return <div className="page-intro"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{action}</div>;
}

export function SectionTitle({ title, aside }: { title: string; aside?: ReactNode }) {
  return <div className="section-title"><h2>{title}</h2>{aside}</div>;
}

export function SettingRow({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return <div className="setting-row"><div><h3>{title}</h3><p>{description}</p></div>{children}</div>;
}

export function TextLink({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return <button type="button" className="text-link" onClick={onClick}>{children}<ArrowUpRight size={15} /></button>;
}
