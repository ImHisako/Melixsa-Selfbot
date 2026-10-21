"""Diagnostica locale e impostazioni di affidabilità."""
from __future__ import annotations

import asyncio
import os
import re
import time

from .. import config_tools, console_tools, persistence_tools


def configuration_status(root):
    try:
        path = root / ".env"
        saved = config_tools.read_values(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
        values = {key: os.environ.get(key) or saved.get(key, "") for key in config_tools.CONFIG_KEYS}
        api_id = values.get("TELEGRAM_API_ID", "").strip()
        api_hash = values.get("TELEGRAM_API_HASH", "").strip()
        telegram = bool(re.fullmatch(r"[0-9]{1,10}", api_id) and 0 < int(api_id) <= 2147483647
                        and re.fullmatch(r"[0-9a-fA-F]{32}", api_hash))
        return (f"Credenziali Telegram » {'formato valido' if telegram else 'mancanti o non valide'}\n"
                f"GeoSeeer » {'chiave configurata' if values.get('GEOSEEER_API_KEY') else 'chiave assente (opzionale)'}\n"
                f"LRCLIB » {'contatto configurato' if values.get('LRCLIB_CLIENT_CONTACT') else 'contatto predefinito'}")
    except (OSError, ValueError):
        return "Configurazione » impossibile leggere .env; verifica formato e permessi."


async def handle_diagnostics_command(client, message, command, argument):
    from .. import runtime

    if command == "errornotify":
        if argument.lower() not in {"", "on", "off"}:
            raise ValueError(f"Uso: {runtime.state.prefix}errornotify on|off")
        if argument:
            async with runtime.state_transaction():
                runtime.state.error_notify = argument.lower() == "on"
        await runtime.respond(message, f"Avvisi nei Messaggi salvati » {'on' if runtime.state.error_notify else 'off'}\nMassimo un avviso al minuto; dettagli con doctor.", title="MELIXSA / ERRORNOTIFY")
        return
    if command == "logconfig":
        if argument:
            parts = argument.split()
            limits = {"size": ("log_max_bytes", 65_536, 1_000_000_000), "backups": ("log_backups", 1, 100), "days": ("log_retention_days", 0, 3650)}
            if len(parts) != 2 or parts[0].lower() not in limits or not parts[1].isascii() or not parts[1].isdigit():
                raise ValueError(f"Uso: {runtime.state.prefix}logconfig size|backups|days <valore>")
            field, low, high = limits[parts[0].lower()]
            value = int(parts[1])
            if not low <= value <= high:
                raise ValueError(f"Scegli un valore da {low} a {high}.")
            async with runtime.state_transaction():
                setattr(runtime.state, field, value)
            await runtime.writer.cleanup()
        await runtime.respond(message, f"Dimensione per file » {runtime.state.log_max_bytes} byte\nArchivi per file » {runtime.state.log_backups}\nScadenza archivi » {runtime.state.log_retention_days} giorni (0 = off)\nPendenti di recupero » esclusi dalla pulizia", title="MELIXSA / LOGCONFIG")
        return
    if argument:
        raise ValueError(f"Uso: {runtime.state.prefix}doctor")
    logs = runtime.writer
    worker = logs.task is not None and not logs.task.done()
    active = sum(job.status in runtime.jobs_tools.ACTIVE for job in runtime.osint_jobs.jobs.values())
    config = await asyncio.to_thread(configuration_status, runtime.ROOT)
    lines = [f"Uptime » {int(time.monotonic() - runtime.luna_tools.STARTED)} s",
             f"Telegram » {'connesso' if getattr(client, 'is_connected', False) else 'non connesso'}",
             config,
             f"Backup stato » {'presente' if persistence_tools.backup_path(runtime.STATE_FILE).exists() else 'creato al prossimo salvataggio'}",
             f"Recupero stato » {runtime.state.load_warning or 'nessun problema rilevato'}",
             f"Worker log » {'attivo' if worker else 'fermo'} | coda {logs.pending_count} | scritti {logs.written} | errori {logs.failures}",
             f"Ultimo problema log » {console_tools.clean(logs.last_error)[:250] or 'nessuno'}",
             f"Limiti log » {runtime.state.log_max_bytes} byte | {runtime.state.log_backups} archivi | {runtime.state.log_retention_days} giorni",
             f"Ricerche OSINT » {active}/{runtime.osint_jobs.limit} attive",
             f"SoundCloud » {'in ascolto' if runtime.soundcloud.server is not None else 'fermo'} | player {len(runtime.soundcloud.players)}",
             f"Lyrics » {'attive' if runtime.lyrics.task is not None and not runtime.lyrics.task.done() else 'off'}",
             f"AFK » {'on' if runtime.afk.active else 'off'}",
             f"Anti-login » {'on' if runtime.state.anti_login_enabled else 'off'} | sessioni {'pronte' if runtime.anti_login.trusted is not None else 'non inizializzate'}",
             f"Avvisi errori » {'on' if runtime.state.error_notify else 'off'}"]
    if runtime.error_notifier is not None and runtime.error_notifier.last_error:
        lines.append(f"Ultimo problema avvisi » {runtime.error_notifier.last_error}")
    for label, detail in (("SoundCloud", runtime.soundcloud.error), ("AFK", runtime.afk.last_error), ("Anti-login", runtime.anti_login.last_error)):
        if detail:
            lines.append(f"Problema {label} » {console_tools.clean(detail)[:200]}")
    lines.append("Ultimi errori (questa esecuzione)")
    errors = list(console_tools.recent_errors)[-5:]
    lines.extend(f"{stamp} | {console_tools.clean(detail)[:250]}" for stamp, detail in errors)
    if not errors:
        lines.append("Nessuno.")
    for part in runtime.osint_features.chunks("\n".join(lines)):
        await runtime.respond(message, part, title="MELIXSA / DOCTOR")
