import { useEffect, useId, useRef, useState } from 'react';
import { CircleAlert, Trash2 } from 'lucide-react';
import { useI18n } from '../i18n';
import { Button } from './ui';

export function RemoveMonitoringButton({ name, kind, disabled, pending, error, onRemove }: {
  name: string;
  kind: 'stalk' | 'surveillance';
  disabled: boolean;
  pending: boolean;
  error: string;
  onRemove: () => Promise<boolean>;
}) {
  const { t, localize } = useI18n();
  const [open, setOpen] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  const label = kind === 'stalk' ? t('Rimuovi {name} da Stalk', { name }) : t('Rimuovi {name} da Surveillance', { name });

  useEffect(() => {
    const element = dialog.current;
    if (open) element?.showModal();
    return () => element?.close();
  }, [open]);

  return <>
    <button type="button" className="icon-button surveillance-remove" aria-label={label} title={label} disabled={disabled} onClick={() => { setAttempted(false); setOpen(true); }}><Trash2 size={15} /></button>
    {open && <dialog ref={dialog} className="modal surveillance-remove-dialog" role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={descriptionId} onClose={() => setOpen(false)} onCancel={event => { if (pending) event.preventDefault(); }}>
      <div className="module-icon purple"><Trash2 size={23} /></div>
      <h2 id={titleId}>{label}</h2>
      <p id={descriptionId}>{t('Il monitoraggio verrà fermato e tutti i registri locali di questa voce saranno eliminati, inclusi gli archivi. Questa operazione non può essere annullata.')}</p>
      {attempted && error && <div className="error-banner" role="alert"><CircleAlert size={17} /><p>{localize(error)}</p></div>}
      <div className="modal-actions">
        <Button variant="secondary" autoFocus disabled={pending} onClick={() => dialog.current?.close()}>{t('Annulla')}</Button>
        <Button variant="secondary" className="surveillance-remove-confirm" disabled={disabled} loading={pending} onClick={async () => { setAttempted(true); if (await onRemove()) dialog.current?.close(); }}><Trash2 size={15} />{t('Rimuovi ed elimina i registri')}</Button>
      </div>
    </dialog>}
  </>;
}
