"""Impostazioni, permessi, help, diagnostica e backup locali."""
from __future__ import annotations

from pyrogram import Client
from pyrogram.types import Message
import asyncio
import os
import re
import time
from datetime import datetime
from pyrogram.errors import RPCError
from .core import backup_tools, config_tools, console_tools, pagination, persistence_tools
from .core.io_tools import local_io

OWNER_CATEGORIES = {"settings", "abuse"}

def access_user_label(user) -> str:
    name = " ".join(filter(None, (getattr(user, "first_name", None), getattr(user, "last_name", None))))
    name = " ".join(name.split()) or "Nome non disponibile"
    return f"{user.id} ({name})"

def default_shared_commands() -> set[str]:
    from .core.catalog import HELP_CATEGORIES

    return {"help"} | {
        name for category, entries in HELP_CATEGORIES.items()
        if category not in OWNER_CATEGORIES | {"soundcloud", "misc"}
        for name, _, _ in entries
    }

def canonical_command(command: str) -> str:
    from .core import runtime

    command = command.lower().removeprefix(runtime.state.prefix)
    command = {"h": "help", "?": "help"}.get(command, command)
    return runtime.luna_tools.ALIASES.get(command, command)

def shareable_commands() -> set[str]:
    from .core import runtime

    reserved = {name for category in OWNER_CATEGORIES for name, _, _ in runtime.HELP_CATEGORIES[category]}
    return {canonical_command(name) for name in runtime.COMMANDS - runtime.CATEGORY_COMMANDS} - (reserved - {"help"})

def permitted_command(command: str, argument: str) -> bool:
    from .core import runtime

    command = canonical_command(command)
    if command == "help" and argument:
        try:
            topic, _ = pagination.split_help_argument(argument, runtime.state.prefix)
        except ValueError:
            return False
        return permitted_command(topic, "") if topic else permitted_command("help", "")
    category = runtime.HELP_CATEGORY_ALIASES.get(command, command)
    if category in OWNER_CATEGORIES:
        return False
    # I menu richiedono help e almeno un comando della categoria abilitato.
    if command == "osint" and argument and not pagination.is_page_argument(argument):
        head = argument.split(maxsplit=1)[0].lower()
        command = runtime.osint_features.SUBCOMMANDS.get(head, head)
    elif command in {"soundcloud", "sc"} and argument and not pagination.is_page_argument(argument):
        command = argument.split(maxsplit=1)[0].lower()
        if not command.startswith("sc"):
            command = f"sc{command}"
    elif command in runtime.CATEGORY_COMMANDS:
        return "help" in runtime.state.shared_commands and any(
            permitted_command(name, "") for name, _, _ in runtime.HELP_CATEGORIES[category]
        )
    return command in runtime.state.shared_commands and command in shareable_commands()

async def handle_access_command(client, message, argument: str) -> None:
    from .core import runtime

    parts = argument.split(maxsplit=1)
    action = parts[0].lower() if parts else ""
    value = parts[1] if len(parts) > 1 else ""
    prefix = runtime.state.prefix
    if action in {"", "list"} and not value:
        user_ids = sorted(runtime.state.command_users)
        labels = {user_id: f"{user_id} (Nome non disponibile)" for user_id in user_ids}
        for start in range(0, len(user_ids), 200):
            try:
                resolved = await client.get_users(user_ids[start:start + 200])
            except RPCError:
                break
            for user in resolved:
                if user.id in labels:
                    labels[user.id] = access_user_label(user)
        users = "\n".join(labels.values()) or "nessuno"
        command_count = len(runtime.state.shared_commands & shareable_commands())
        text = "\n".join((
            f"{prefix}access add <@utente|ID> » Autorizza una persona (anche in risposta)",
            f"{prefix}access remove <@utente|ID> » Revoca una persona (anche in risposta)",
            f"{prefix}access allow <comando|categoria> » Abilita comandi per le persone autorizzate",
            f"{prefix}access block <comando|categoria> » Disabilita comandi",
            f"{prefix}access list » Mostra permessi",
            f"Utenti » {users}", f"Comandi abilitati » {command_count}",
            "Menu disponibili solo per categorie abilitate. Settings e abuse riservati al proprietario.",
            "Base » Tutti i comandi tranne settings, abuse, soundcloud e misc (help incluso).",
        ))
        await runtime.respond(message, text, title="MELIXSA / ACCESS")
        return
    if action not in {"add", "remove", "allow", "block"}:
        raise ValueError(f"Uso: {prefix}access")
    if action in {"add", "remove"}:
        user = await runtime.resolve_user(client, message, value)
        if user.is_bot or user.id <= 0:
            raise ValueError("Scegli un utente Telegram, non un bot.")
        target = user.id
        targets = {target}
        field = "command_users"
    else:
        target = value.strip().lower().removeprefix(prefix)
        category = runtime.HELP_CATEGORY_ALIASES.get(target, target)
        if category in runtime.HELP_CATEGORIES:
            if category in OWNER_CATEGORIES:
                raise ValueError(f"La categoria {category} resta riservata al proprietario; puoi gestire help singolarmente.")
            targets = {canonical_command(name) for name, _, _ in runtime.HELP_CATEGORIES[category]} & shareable_commands()
        else:
            target = canonical_command(target)
            if not target or target not in shareable_commands():
                raise ValueError("Comando o categoria sconosciuti oppure riservati al proprietario.")
            targets = {target}
        field = "shared_commands"
    async with runtime.state_transaction():
        previous = getattr(runtime.state, field).copy()
        updated = previous.copy()
        if action in {"add", "allow"}:
            updated.update(targets)
        else:
            updated.difference_update(targets)
        setattr(runtime.state, field, updated)
    label = access_user_label(user) if action in {"add", "remove"} else target
    await runtime.respond(message, f"{'Abilitato' if action in {'add', 'allow'} else 'Revocato'} » {label}", title="MELIXSA / ACCESS")

def help_text(prefix: str, topic: str = "", *, page: int | None = None) -> str:
    """Crea una pagina di menu, filtrata per permessi e modalità minimale."""
    from .core import runtime

    minimal = runtime.state.minimal_mode
    def menu_line(syntax: str, description: str) -> str:
        return syntax if minimal else f"{syntax} » {description}"

    try:
        topic, selected = pagination.split_help_argument(topic, prefix)
        page = selected if page is None else page
        if type(page) is not int or page < 1:
            raise ValueError("Pagina non valida: usa un numero intero da 1 in poi.")
    except ValueError as exc:
        return f"[ MELIXSA / HELP ]\n{exc}\nMenu: {prefix}help"
    topic = topic.lower()
    topic = {"h": "help", "?": "help"}.get(topic, topic)
    topic = runtime.HELP_CATEGORY_ALIASES.get(topic, topic)
    topic = runtime.luna_tools.ALIASES.get(topic, topic)
    restricted = runtime.shared_command_context.get()
    categories = {
        category: tuple(entry for entry in entries if not restricted or runtime.permitted_command(entry[0], ""))
        for category, entries in runtime.HELP_CATEGORIES.items()
        if not restricted or runtime.permitted_command(category, "")
    }
    if restricted and topic and not runtime.permitted_command(topic, ""):
        return "[ MELIXSA / HELP ]\nVoce non disponibile."
    if not topic:
        navigation_command = f"{prefix}help"
        lines = ["[ MELIXSA ]"] + [menu_line(
            f"{prefix}{'mass' if category == 'mass surveillance' else category}",
            {"soundcloud": "SoundCloud", "osint": "OSINT"}.get(category, category.title()),
        ) for category in categories] + [menu_line(f"{prefix}help [voce] [pagina]", "Dettagli")]
    elif topic in runtime.HELP_CATEGORIES:
        navigation_command = f"{prefix}{'mass' if topic == 'mass surveillance' else topic}"
        lines = [f"[ MELIXSA / {topic.upper()} ]"]
        if not categories[topic]:
            lines.append("Nessun comando disponibile")
        else:
            for name, usage, description in categories[topic]:
                syntax = f"{prefix}{name} {usage}".rstrip()
                lines.append(menu_line(syntax, description))
    else:
        navigation_command = f"{prefix}help {topic}"
        entry = next(
            ((category, name, usage, description)
             for category, entries in categories.items()
             for name, usage, description in entries if name == topic),
            None,
        )
        if entry is None:
            return f"[ MELIXSA / HELP ]\nVoce sconosciuta: {topic}\n{menu_line(f'{prefix}help', 'Menu')}"
        _, name, usage, description = entry
        syntax = f"{prefix}{name} {usage}".rstrip()
        lines = [
            f"[ MELIXSA / {name.upper()} ]",
            menu_line(syntax, description),
        ]
        if not minimal:
            lines.append(runtime.HELP_DETAILS[name])
    pages = pagination.paginate_lines(lines[1:])
    if page > len(pages):
        return (f"{lines[0]}\nPagina non disponibile: scegli da 1 a {len(pages)}."
                f"\nPrima pagina: {navigation_command} 1")
    output = [lines[0], *pages[page - 1]]
    if len(pages) > 1:
        output += ["", f"Pagina {page}/{len(pages)}", *pagination.navigation(navigation_command, page, len(pages))]
    return "\n".join(output)

async def send_help(client: Client, message: Message, topic: str = "") -> None:
    from .core import runtime

    text = runtime.help_text(runtime.state.prefix, topic)
    header, _, commands = text.partition("\n")
    text = f"{header}\n{commands}"
    header_entity = runtime.pre_entity(header)
    header_entity.language = "lua"
    commands_entity = runtime.pre_entity(commands)
    commands_entity.offset = len(f"{header}\n".encode("utf-16-le")) // 2
    sent = await client.send_message(
        message.chat.id,
        text,
        parse_mode=runtime.enums.ParseMode.DISABLED,
        entities=[header_entity, commands_entity],
        message_thread_id=message.message_thread_id,
    )
    if sent is None:
        raise RuntimeError("Telegram non ha confermato l'invio del menu.")
    runtime.schedule_delete(sent)

async def handle_anti_login_command(client: Client, message: Message, argument: str) -> None:
    from .core import runtime

    action = {"enable": "on", "disable": "off"}.get(argument.lower(), argument.lower())
    if action not in {"", "status", "on", "off"}:
        raise ValueError(f"Uso: {runtime.state.prefix}anti-login on|off|status")
    if action in {"on", "off"}:
        async with runtime.state_transaction():
            runtime.state.anti_login_enabled = action == "on"
        if action == "on":
            await runtime.anti_login.initialize(client)
            runtime.anti_login.wakeup.set()
    last = runtime.state.anti_login_last_reset
    timestamp = datetime.fromtimestamp(last).astimezone().isoformat(timespec="seconds") if last else "mai"
    text = (f"Stato » {'on' if runtime.state.anti_login_enabled else 'off'}\n"
            f"Sessioni iniziali » {'pronte' if runtime.anti_login.trusted is not None else 'non disponibili: chiusura sessioni sospesa'}\n"
            f"Ultima sessione chiusa » {timestamp}")
    if runtime.anti_login.last_error:
        text += f"\nUltimo problema » {runtime.anti_login.last_error}"
    await runtime.respond(message, text, title="MELIXSA / ANTI-LOGIN")

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
    from .core import runtime

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

async def handle_backup_command(message, command: str, argument: str) -> None:
    from .core import runtime

    if runtime.shared_command_context.get():
        raise ValueError("Comando riservato al proprietario.")
    parts = argument.split()
    action = parts[0].lower() if parts else ""
    store = runtime.backups
    if command == "backups":
        if parts:
            raise ValueError(f"Uso: {runtime.state.prefix}backups")
        action = "list"
    async with runtime.backups_lock:
        if action == "list" and len(parts) <= 1:
            result = "Backup locali »\n" + ("\n".join(await local_io(store.names)) or "nessuno")
        elif action == "create" and len(parts) <= 2:
            async with runtime.state_lock, runtime.notes_lock:
                notes = await local_io(backup_tools.read_notes, runtime.notes.path)
                name = await local_io(store.create, backup_tools.settings_payload(runtime.state), notes,
                                      parts[1] if len(parts) == 2 else "")
            result = f"Backup salvato » {name}\nCartella » data/backups/"
        elif action == "view" and len(parts) == 2:
            payload = await local_io(store.load, parts[1])
            result = store.summary(parts[1], payload)
        elif action == "delete" and len(parts) == 2:
            await local_io(store.delete, parts[1])
            result = f"Backup eliminato » {parts[1]}"
        elif action == "restore" and len(parts) == 3 and parts[2].lower() in {"settings", "notes"}:
            payload = await local_io(store.load, parts[1])
            section = parts[2].lower()
            async def snapshot():
                current_notes = await local_io(backup_tools.read_notes, runtime.notes.path)
                return await local_io(store.create, backup_tools.settings_payload(runtime.state), current_notes)

            # Una sola risorsa per ripristino; la copia preventiva conserva entrambe.
            if section == "notes":
                async with runtime.state_lock, runtime.notes_lock:
                    previous = await snapshot()
                    await local_io(runtime.persistence_tools.save_json, runtime.notes.path,
                                   payload["notes"], backup_tools.validate_notes)
            else:
                async with runtime.state_transaction():
                    async with runtime.notes_lock:
                        previous = await snapshot()
                        restored = runtime.MonitorState.from_raw(payload["settings"])
                        for name in backup_tools.SETTINGS_FIELDS:
                            setattr(runtime.state, name, getattr(restored, name))
            runtime.console_tools.configure(runtime.state.console)
            result = (f"Ripristinato » {parts[1]} / {section}\nCopia precedente » {previous}"
                      f"\nPrefisso attuale » {runtime.state.prefix}")
        elif not action:
            prefix = runtime.state.prefix
            result = "\n".join((
                f"{prefix}backup create [nome] » Salva preferenze e note",
                f"{prefix}backups » Elenca copie locali",
                f"{prefix}backup view <nome> » Mostra riepilogo",
                f"{prefix}backup restore <nome> settings|notes » Ripristina una sezione",
                f"{prefix}backup delete <nome> » Elimina una copia",
                "Prima del ripristino viene creata una copia automatica. Massimo 30 backup.",
                "Credenziali, sessioni, permessi di accesso e monitoraggi sono esclusi.",
            ))
        else:
            raise ValueError(f"Uso: {runtime.state.prefix}backup")
    await runtime.respond(message, result, title="MELIXSA / BACKUP")

async def handle_command(client: Client, message: Message, command: str, argument: str) -> None:
    from .core import runtime

    title = f"MELIXSA / {command.upper()}"
    chat_id = message.chat.id
    is_group = message.chat.type in {runtime.enums.ChatType.GROUP, runtime.enums.ChatType.SUPERGROUP}
    if command in {"help", "h", "?"}:
        await runtime.send_help(client, message, argument)
    elif command in {"doctor", "errornotify", "logconfig"}:
        await handle_diagnostics_command(client, message, command, argument)
    elif command == "access":
        await handle_access_command(client, message, argument)
    elif command == "anti-login":
        await runtime.handle_anti_login_command(client, message, argument)
    elif command == 'commandhistory':
        if runtime.shared_command_context.get():
            raise ValueError("Comando riservato al proprietario.")
        if argument.lower() == "clear":
            runtime.command_history.records.clear()
            result = "Cronologia svuotata."
        else:
            result = runtime.command_history.render(int(argument or "10"))
        await runtime.respond(message, result, title=title)
    elif command in {'backup', 'backups'}:
        await handle_backup_command(message, command, argument)
        return
    elif command == 'minimal-mode':
        action = argument.lower()
        if action not in {"", "on", "off"}:
            raise ValueError(f"Uso: {runtime.state.prefix}minimal-mode on|off")
        if action:
            async with runtime.state_transaction():
                runtime.state.minimal_mode = action == "on"
        await runtime.respond(message, f"Minimal-mode {'on' if runtime.state.minimal_mode else 'off'}", title="MELIXSA / MINIMAL-MODE")
    elif command == 'debug-mode':
        action = argument.lower()
        if action not in {"", "on", "off"}:
            raise ValueError(f"Uso: {runtime.state.prefix}debug-mode on|off")
        if action:
            async with runtime.state_transaction():
                runtime.state.console["debug_mode"] = action == "on"
            runtime.console_tools.configure(runtime.state.console)
        enabled = runtime.state.console.get("debug_mode", False)
        await runtime.respond(message, f"Debug-mode » {'on' if enabled else 'off'}", title="MELIXSA / DEBUG-MODE")
    elif command == 'clear':
        if argument:
            raise ValueError(f"Uso: {runtime.state.prefix}clear")
        runtime.console_tools.clear()
        await runtime.respond(message, "Console pulita.", title="MELIXSA / CLEAR")
    elif command in {'console', 'timestamp', 'spacers', 'pgradient', 'lgradient'}:
        if command != "console":
            if argument.lower() not in {"on", "off"}:
                raise ValueError(f"Uso: {runtime.state.prefix}{command} on|off")
            async with runtime.state_transaction():
                runtime.state.console[command] = argument.lower() == "on"
            runtime.console_tools.configure(runtime.state.console)
        else:
            runtime.console_tools.banner(runtime.state.prefix, len(runtime.COMMANDS - runtime.CATEGORY_COMMANDS), runtime.state.delete_after)
        await runtime.respond(message, "\n".join(f"{key} » {'on' if value else 'off'}" for key, value in runtime.state.console.items()), title="MELIXSA / CONSOLE")
    elif command == 'prefix':
        if not argument:
            await runtime.respond(message, f"Attuale » {runtime.state.prefix}\nCambia » {runtime.state.prefix}prefix !", title="MELIXSA / PREFIX")
            return
        if not runtime.valid_prefix(argument):
            await runtime.respond(message, "Errore » Scegli un solo simbolo stampabile: !, . oppure /.", title="MELIXSA / PREFIX", error=True)
            return
        async with runtime.state_transaction():
            runtime.state.prefix = argument
        await runtime.respond(message, f"Attuale » {runtime.state.prefix}\nMenu » {runtime.state.prefix}help", title="MELIXSA / PREFIX")
    elif command == 'deleteafter':
        if not argument:
            await runtime.respond(message, f"Timer » {runtime.state.delete_after} s\nCambia » {runtime.state.prefix}deleteafter 40\nOff » {runtime.state.prefix}deleteafter 0", title="MELIXSA / DELETEAFTER")
            return
        try:
            delay = int(argument)
        except ValueError:
            delay = -1
        if not 0 <= delay <= runtime.MAX_DELETE_AFTER:
            await runtime.respond(message, f"Errore » Inserisci un intero da 0 a {runtime.MAX_DELETE_AFTER} secondi.", title="MELIXSA / DELETEAFTER", error=True)
            return
        async with runtime.state_transaction():
            runtime.state.delete_after = delay
        value = "off" if delay == 0 else f"{delay} s"
        await runtime.respond(message, f"Timer risposte » {value}\nComandi » cancellati subito", title="MELIXSA / DELETEAFTER")
    elif command == 'status':
        targets = ", ".join(str(user_id) for user_id in sorted(runtime.state.stalk)) or "nessuno"
        timing = "disattivata" if runtime.state.delete_after == 0 else f"{runtime.state.delete_after} secondi"
        if is_group:
            active = "attivo" if chat_id in runtime.state.surveillance else "fermo"
            await runtime.respond(message, f"Prefisso » {runtime.state.prefix}\nTimer » {timing}\nGruppo » {active}\nUtenti » {targets}\nAFK » {'attivo' if runtime.afk.active else 'off'}", title="MELIXSA / STATUS")
        else:
            await runtime.respond(message, f"Prefisso » {runtime.state.prefix}\nTimer » {timing}\nUtenti » {targets}\nAFK » {'attivo' if runtime.afk.active else 'off'}", title="MELIXSA / STATUS")
    else:
        raise ValueError(f"Comando non previsto nella sezione: {command}")
