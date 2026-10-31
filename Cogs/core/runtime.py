"""Runtime Melixsa: sessione Telegram, stato condiviso, risposte e monitoraggio."""

from __future__ import annotations

import asyncio
import json
import os
import time
from copy import deepcopy
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

from pyrogram import Client, enums, filters
from pyrogram.errors import PeerIdInvalid
from pyrogram.types import Message, MessageEntity, ChatPermissions

from . import (
    afk_tools, anti_login_tools, autoreact_tools, config_tools, console_tools, geosint_tools,
    luna_tools, lyrics_tools, osint_features, osint_tools, soundcloud_tools,
    persistence_tools, log_tools, jobs_tools, error_tools, backup_tools, ghost_tools, stalk_tools,
)
from .catalog import (
    HELP_CATEGORIES, HELP_CATEGORY_ALIASES, HELP_DETAILS, CATEGORY_COMMANDS,
    OSINT_COMMANDS, SOUNDCLOUD_COMMANDS, COMMANDS, MAX_DELETE_AFTER,
)
from .router import handle_command
from ..soundcloud import handle_soundcloud_command, handle_lyrics_command
from ..fun import handle_autoreact_command
from ..osint import handle_geosint_command, handle_osint_command
from ..misc import handle_afk_command
from ..settings import (
    help_text, send_help, handle_anti_login_command, default_shared_commands, permitted_command,
)
from ..abuse import is_spam_message


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
LOG_DIR = DATA_DIR / "logs"
STATE_FILE = DATA_DIR / "state.json"


def valid_prefix(value: object) -> bool:
    return isinstance(value, str) and len(value) == 1 and value.isprintable() and not value.isspace() and not value.isalnum()


@dataclass
class MonitorState:
    surveillance: set[int] = field(default_factory=set)
    stalk: set[int] = field(default_factory=set)
    prefix: str = "/"
    delete_after: int = 40
    autoreact: bool = False
    autoreact_emojis: tuple[str, ...] = autoreact_tools.EMOJIS
    autoreact_count: int = len(autoreact_tools.EMOJIS)
    minimal_mode: bool = False
    command_users: set[int] = field(default_factory=set)
    shared_commands: set[str] = field(default_factory=default_shared_commands)
    anti_login_enabled: bool = True
    anti_login_last_reset: float = 0.0
    log_max_bytes: int = 10_000_000
    log_backups: int = 5
    log_retention_days: int = 0
    error_notify: bool = False
    load_warning: str = field(default="", init=False, repr=False)
    console: dict[str, bool] = field(default_factory=lambda: console_tools.CONSOLE_DEFAULTS.copy())

    @classmethod
    def load(cls) -> "MonitorState":
        problems = []
        for path in (STATE_FILE, persistence_tools.backup_path(STATE_FILE)):
            try:
                restored = cls.from_raw(json.loads(path.read_text(encoding="utf-8")))
            except FileNotFoundError:
                continue
            except (OSError, ValueError, TypeError, KeyError):
                problems.append(path.name)
                continue
            if path != STATE_FILE:
                restored.load_warning = "Stato recuperato dal backup; sarà ripristinato al prossimo salvataggio."
            return restored
        restored = cls()
        if problems:
            restored.load_warning = "Stato e backup non utilizzabili: impostazioni predefinite e accessi revocati."
        return restored

    @classmethod
    def from_raw(cls, raw: object) -> "MonitorState":
        if not isinstance(raw, dict):
            raise ValueError("Lo stato deve essere un oggetto JSON.")
        def ids(values):
            if not isinstance(values, (list, set)):
                raise ValueError("Elenco ID non valido.")
            if any(type(item) not in (int, str) or not str(item).lstrip("-").isdigit() for item in values):
                raise ValueError("ID non valido.")
            return {int(item) for item in values}
        saved_stalk = raw.get("stalk", [])
        # Versioni precedenti salvavano gli ID separatamente per gruppo.
        if isinstance(saved_stalk, dict):
            saved_stalk = set().union(*(ids(items) for items in saved_stalk.values()))
        saved_delay = raw.get("delete_after", 40)
        try:
            saved_emojis = raw.get("autoreact_emojis", list(autoreact_tools.EMOJIS))
            if not isinstance(saved_emojis, list) or not all(isinstance(item, str) for item in saved_emojis):
                raise ValueError("Invalid emoji list")
            saved_emojis = autoreact_tools.parse_emojis(" ".join(saved_emojis))
        except ValueError:
            saved_emojis = autoreact_tools.EMOJIS
        saved_count = raw.get("autoreact_count", len(saved_emojis))
        if type(saved_count) is not int or not 1 <= saved_count <= len(saved_emojis):
            saved_count = len(saved_emojis)
        return cls(
            surveillance=ids(raw.get("surveillance", [])),
            stalk=ids(saved_stalk),
            prefix=raw.get("prefix") if valid_prefix(raw.get("prefix")) else "/",
            delete_after=saved_delay if type(saved_delay) is int and 0 <= saved_delay <= MAX_DELETE_AFTER else 40,
            autoreact=raw.get("autoreact") is True,
            autoreact_emojis=saved_emojis,
            autoreact_count=saved_count,
            minimal_mode=raw.get("minimal_mode") is True,
            command_users={item for item in raw.get("command_users", []) if type(item) is int and item > 0}
            if isinstance(raw.get("command_users", []), list) else set(),
            shared_commands={item for item in raw.get("shared_commands", default_shared_commands()) if isinstance(item, str)}
            if "shared_commands" not in raw or isinstance(raw["shared_commands"], list) else default_shared_commands(),
            anti_login_enabled=raw.get("anti_login_enabled", True) is True,
            anti_login_last_reset=raw.get("anti_login_last_reset", 0.0)
            if type(raw.get("anti_login_last_reset")) in (int, float) and 0 <= raw["anti_login_last_reset"] <= time.time() else 0.0,
            log_max_bytes=raw.get("log_max_bytes", 10_000_000)
            if type(raw.get("log_max_bytes")) is int and 65_536 <= raw["log_max_bytes"] <= 1_000_000_000 else 10_000_000,
            log_backups=raw.get("log_backups", 5)
            if type(raw.get("log_backups")) is int and 1 <= raw["log_backups"] <= 100 else 5,
            log_retention_days=raw.get("log_retention_days", 0)
            if type(raw.get("log_retention_days")) is int and 0 <= raw["log_retention_days"] <= 3650 else 0,
            error_notify=raw.get("error_notify") is True,
            console={key: raw.get("console", {}).get(key, default)
                     if type(raw.get("console", {}).get(key, default)) is bool else default
                     for key, default in console_tools.CONSOLE_DEFAULTS.items()}
            if isinstance(raw.get("console", {}), dict) else console_tools.CONSOLE_DEFAULTS.copy(),
        )

    def save(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "surveillance": sorted(self.surveillance),
            "stalk": sorted(self.stalk),
            "prefix": self.prefix,
            "delete_after": self.delete_after,
            "autoreact": self.autoreact,
            "autoreact_emojis": list(self.autoreact_emojis),
            "autoreact_count": self.autoreact_count,
            "minimal_mode": self.minimal_mode,
            "command_users": sorted(self.command_users),
            "shared_commands": sorted(self.shared_commands),
            "anti_login_enabled": self.anti_login_enabled,
            "anti_login_last_reset": self.anti_login_last_reset,
            "log_max_bytes": self.log_max_bytes,
            "log_backups": self.log_backups,
            "log_retention_days": self.log_retention_days,
            "error_notify": self.error_notify,
            "console": self.console,
        }
        persistence_tools.save_json(STATE_FILE, payload, self.from_raw)


# Alias pubblico mantenuto per gli utilizzatori del runtime.
LogWriter = log_tools.LogWriter


def message_record(message: Message, event: str) -> dict[str, Any]:
    user = message.from_user
    sender_chat = message.sender_chat
    media = message.media
    return {
        "event": event,
        "date": message.date.isoformat() if message.date else None,
        "edit_date": message.edit_date.isoformat() if message.edit_date else None,
        "chat_id": message.chat.id,
        "chat_title": message.chat.title,
        "chat_name": chat_name(message),
        "message_id": message.id,
        "reply_to_message_id": message.reply_to_message_id,
        "user_id": user.id if user else None,
        "username": user.username if user else None,
        "name": " ".join(filter(None, (user.first_name, user.last_name))) if user else None,
        "sender_chat_id": sender_chat.id if sender_chat else None,
        "sender_chat_title": getattr(sender_chat, "title", None),
        "text": message.text or message.caption or "",
        "media": media.name.lower() if media else None,
    }


def command_parts(text: str | None, prefix: str = "/") -> tuple[str, str] | None:
    if not text or not text.startswith(prefix):
        return None
    parts = text[len(prefix):].split(maxsplit=1)
    if not parts:
        return None
    head = parts[0]
    argument = parts[1] if len(parts) > 1 else ""
    command = head.split("@", 1)[0].lower()
    if not command:
        return None
    return command, argument.strip()


async def log_settings():
    # La pulizia non deve leggere limiti ancora in attesa di salvataggio.
    async with state_lock:
        return dict(max_bytes=state.log_max_bytes, backups=state.log_backups, retention_days=state.log_retention_days)


state = MonitorState.load()
writer = LogWriter(LOG_DIR, settings=log_settings)


async def submit_stalk_event(target, record):
    await writer.submit(LOG_DIR / f"stalk_{target}.txt", record)


stalk_monitor = stalk_tools.StalkMonitor(lambda: set(state.stalk), submit_stalk_event)
osint_jobs = jobs_tools.JobManager()
error_notifier = None
soundcloud = soundcloud_tools.SoundCloudAdapter()
lyrics = lyrics_tools.LyricsController(soundcloud)
auto_reactor = autoreact_tools.AutoReactor()
afk = afk_tools.AFKController()
notes = luna_tools.Notes(DATA_DIR / "notes.json")
notes_lock = asyncio.Lock()
backups = backup_tools.BackupStore(DATA_DIR / "backups", MonitorState.from_raw)
backups_lock = asyncio.Lock()
command_history = ghost_tools.CommandHistory()
animation_chats: set[int] = set()
state_lock = asyncio.Lock()
delete_tasks: set[asyncio.Task[None]] = set()
command_context: ContextVar[tuple[str, int, str] | None] = ContextVar("command_context", default=None)
shared_command_context: ContextVar[bool] = ContextVar("shared_command_context", default=False)


@asynccontextmanager
async def state_transaction():
    """Salva sotto lock; ripristina tutti i campi se l'operazione fallisce."""
    async with state_lock:
        previous = {item.name: deepcopy(getattr(state, item.name)) for item in fields(state)}
        try:
            yield state
        except BaseException:
            for name, value in previous.items():
                setattr(state, name, value)
            raise
        save_task = asyncio.create_task(asyncio.to_thread(state.save))
        try:
            await asyncio.shield(save_task)
        except asyncio.CancelledError:
            # Il thread non può essere annullato: attendi l'esito prima di liberare il lock.
            try:
                await save_task
            except BaseException:
                for name, value in previous.items():
                    setattr(state, name, value)
            raise
        except Exception:
            for name, value in previous.items():
                setattr(state, name, value)
            raise


async def save_login_reset(timestamp: float) -> None:
    async with state_transaction():
        state.anti_login_last_reset = timestamp


anti_login = anti_login_tools.AntiLoginController(lambda: state.anti_login_enabled, save_reset=save_login_reset)


def chat_name(message: Message, own_id: int | None = None) -> str:
    chat = getattr(message, "chat", None)
    context = command_context.get()
    if context and (chat is None or getattr(chat, "id", None) == context[1]):
        return context[2]
    if own_id is not None and getattr(chat, "id", None) == own_id:
        return "Messaggi salvati"
    title = getattr(chat, "title", None)
    if title:
        return title
    name = " ".join(part for part in (getattr(chat, "first_name", None), getattr(chat, "last_name", None)) if part)
    if name:
        return name
    username = getattr(chat, "username", None)
    return f"@{username}" if username else "Chat senza nome"


def log_command_error(message: Message, text: object, *, title: str = "MELIXSA") -> None:
    console_tools.event("Error", f"chat={chat_name(message)} | {title} | {text}", error=True)


async def respond(message: Message, text: str, *, title: str = "MELIXSA", auto_delete: bool = True, error: bool = False, mention_user: Any = None) -> None:
    if error:
        log_command_error(message, text, title=title)
        return
    panel = f"[ {title} ]\n{text}"
    entities = [pre_entity(panel)]
    if mention_user is not None:
        label = user_label(mention_user)
        entities[0].offset = len(f"{label}\n".encode("utf-16-le")) // 2
        entities.append(MessageEntity(type=enums.MessageEntityType.TEXT_MENTION, offset=0,
                                      length=len(label.encode("utf-16-le")) // 2, user=mention_user))
        panel = f"{label}\n{panel}"
    if len(panel.encode("utf-16-le")) // 2 > 4096:
        raise ValueError("Risposta troppo lunga per Telegram: riduci il testo.")
    # Il comando originale è già cancellato: invia nella stessa chat/topic senza citarlo.
    try:
        sent = await message.answer(panel, parse_mode=enums.ParseMode.DISABLED, entities=entities)
    except PeerIdInvalid:
        if mention_user is None:
            raise
        # Un utente ricevuto in risposta può non essere nella cache dei peer.
        # La menzione richiede resolve_peer; conserva nome e PRE senza menzione.
        sent = await message.answer(panel, parse_mode=enums.ParseMode.DISABLED, entities=entities[:1])
    if sent is not None and auto_delete:
        schedule_delete(sent)
    chat_label = chat_name(message)
    console_tools.event("Message", f"Risposta | chat={chat_label} | {title}")


def user_label(user: Any) -> str:
    username = getattr(user, "username", None)
    if username:
        return f"@{username}"
    return " ".join(part for part in (getattr(user, "first_name", None), getattr(user, "last_name", None)) if part) or str(user.id)


def pre_entity(text: str) -> MessageEntity:
    return MessageEntity(
        type=enums.MessageEntityType.PRE,
        offset=0,
        length=len(text.encode("utf-16-le")) // 2,
        language="ini",
    )


async def delete_message_later(message: Message, delay: float) -> None:
    await asyncio.sleep(delay)
    context = command_context.get()
    label = f"Comando {context[0]}" if context else "Messaggio"
    chat_label = chat_name(message)
    try:
        await message.delete()
    except Exception as exc:
        console_tools.event("Error", f"{label} non cancellato | chat={chat_label} | {exc}", error=True)
    else:
        console_tools.event("Event", f"{label} cancellato | chat={chat_label}")


def schedule_delete(message: Message) -> None:
    if state.delete_after == 0:
        return
    task = asyncio.create_task(delete_message_later(message, state.delete_after))
    delete_tasks.add(task)
    task.add_done_callback(delete_tasks.discard)


async def resolve_user(client: Client, message: Message, argument: str) -> Any:
    if argument:
        identifier: int | str = int(argument) if argument.lstrip("-").isdigit() else argument
        return await client.get_users(identifier)
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user
    raise ValueError("Rispondi a un messaggio oppure indica @username o ID numerico.")


async def process_message(client: Client, message: Message, own_id: int) -> None:
    chat_type = message.chat.type
    own_message = bool(message.from_user and message.from_user.id == own_id)
    if chat_type == enums.ChatType.PRIVATE and message.chat.id == own_id:
        own_message = True  # Messaggi salvati può essere marcato come incoming.
    if own_message and is_spam_message(message):
        return
    authorized_user = bool(message.from_user and message.from_user.id in state.command_users)
    if own_message or authorized_user:
        parsed = command_parts(message.text, state.prefix)
        used_prefix = state.prefix
        if own_message and parsed is None and state.prefix != "/":
            fallback = command_parts(message.text, "/")
            if fallback is not None and fallback[0] == "prefix":
                parsed = fallback
                used_prefix = "/"
        if parsed is not None and parsed[0] in COMMANDS and (own_message or permitted_command(*parsed)):
            command, argument = parsed
            started = time.monotonic()
            chat_label = chat_name(message, own_id)
            console_tools.event("Command", f"{used_prefix}{command} | chat={chat_label} | ricevuto")
            if own_message:
                try:
                    await message.delete()
                except Exception as exc:
                    console_tools.event("Error", f"Cancellazione comando {used_prefix}{command} | chat={chat_label} | {exc}", error=True)
            context_token = command_context.set((command, message.chat.id, chat_label))
            shared_token = shared_command_context.set(not own_message)
            success = False
            try:
                await handle_command(client, message, command, argument)
                success = True
            except Exception as exc:
                console_tools.event("Error", f"{used_prefix}{command} | chat={chat_label} | {exc}", error=True)
            finally:
                canonical = luna_tools.ALIASES.get(command, command)
                if not (canonical == "commandhistory" and argument.lower() == "clear"):
                    command_history.add(canonical, success, time.monotonic() - started)
                shared_command_context.reset(shared_token)
                command_context.reset(context_token)
                console_tools.event("Command", f"{used_prefix}{command} | chat={chat_label} | terminato in {time.monotonic() - started:.2f}s")
            return  # Non aggiungere reazioni a un comando già cancellato.
        if own_message and state.autoreact:
            selected = state.autoreact_emojis[:state.autoreact_count]
            await auto_reactor.react(
                client, message, emojis=selected,
                chat_label=chat_name(message, own_id),
                enabled=lambda: state.autoreact and state.autoreact_emojis[:state.autoreact_count] == selected,
            )
        if own_message:
            return
    if chat_type == enums.ChatType.PRIVATE:
        if message.chat.id == 777000:
            await anti_login.handle_message(client, message)
            return
        await afk.reply(client, message, chat_name(message))
    elif chat_type in {enums.ChatType.GROUP, enums.ChatType.SUPERGROUP}:
        await handle_event(message, "new")


async def handle_event(message: Message, event: str) -> None:
    user = message.from_user
    if user and user.is_self:
        return
    if message.service or (not message.text and not message.caption and not message.media):
        return
    chat_id = message.chat.id
    surveilled = chat_id in state.surveillance
    stalked = bool(user and user.id in state.stalk)
    if not surveilled and not stalked:
        return
    record = message_record(message, event)
    if surveilled:
        await writer.submit(LOG_DIR / f"group_{chat_id}.txt", record)
    if stalked:
        await writer.submit(LOG_DIR / f"stalk_{user.id}.txt", record, echo=not surveilled)


async def connect_soundcloud_on_startup(client: Client) -> None:
    try:
        result = await soundcloud.execute("scconnect", "", state.prefix)
    except Exception as exc:
        console_tools.event("Error", f"Avvio SoundCloud: {exc}", error=True)
        return
    panel = f"[ MELIXSA / SOUNDCLOUD ]\nAvvio automatico » {state.prefix}scconnect\n{result}"
    console_tools.event("Selfbot", panel, debug=True)
    try:
        sent = await client.send_message(
            "me", panel,
            parse_mode=enums.ParseMode.DISABLED,
            entities=[pre_entity(panel)],
        )
        if sent is not None:
            schedule_delete(sent)
    except Exception as exc:
        console_tools.event("Error", f"Stato SoundCloud nei Messaggi salvati: {exc}", error=True)


async def main(*, control=None) -> None:
    from .instance_tools import InstanceLock

    with InstanceLock(DATA_DIR / "runtime.lock"):
        await _main(control=control)


async def _main(*, control=None) -> None:
    global error_notifier
    global osint_jobs
    if osint_jobs.closing:
        osint_jobs = jobs_tools.JobManager()
    try:
        api_id, api_hash = config_tools.load_credentials(ROOT / ".env")
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    except OSError as exc:
        raise SystemExit("Impossibile leggere o salvare .env. Verifica i permessi della cartella del selfbot.") from exc
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    console_tools.setup(LOG_DIR, secrets=(api_hash,))
    console_tools.configure(state.console)
    console_tools.banner(state.prefix, len(COMMANDS - CATEGORY_COMMANDS), state.delete_after)
    if state.load_warning:
        console_tools.event("Error", state.load_warning, error=True)
    try:
        # Protegge anche una configurazione precedente all'introduzione dei backup.
        await asyncio.to_thread(state.save)
    except OSError:
        console_tools.event("Error", "Backup stato non aggiornato: verifica spazio e permessi di data/.", error=True)
    else:
        if state.load_warning:
            state.load_warning = "Recupero effettuato; stato valido salvato su disco."
    asyncio.get_running_loop().set_exception_handler(
        lambda _loop, context: console_tools.event("Error", f"Task: {context.get('message')} | {context.get('exception', '')}", error=True))
    await writer.start()
    app = Client("melixsa", api_id=api_id, api_hash=api_hash, workdir=str(DATA_DIR))
    own_id: int | None = None

    @app.on_message(filters.group | filters.private)
    async def on_message(client: Client, message: Message) -> None:
        if own_id is not None:
            await process_message(client, message, own_id)

    @app.on_edited_message(filters.group)
    async def on_edited_message(_client: Client, message: Message) -> None:
        await handle_event(message, "edited")

    @app.on_raw_update(group=-1)
    async def on_stalk_update(_client, update, users, _chats):
        if own_id is not None:
            await stalk_monitor.handle_update(update, users)

    try:
        async with app:
            error_notifier = error_tools.ErrorNotifier(app, lambda: state.error_notify)
            console_tools.error_callback = error_notifier.signal
            try:
                me = await app.get_me()
                own_id = me.id
                stalk_monitor.start(app, own_id=own_id)
                await anti_login.start(app)
                console_tools.event("Selfbot", f"Telegram connesso | account={own_id}", debug=True)
                if control is None:
                    await connect_soundcloud_on_startup(app)
                    await asyncio.Event().wait()
                else:
                    await control.on_ready(app, me)
                    await control.stop_event.wait()
            finally:
                own_id = None
                await stalk_monitor.close()
                console_tools.error_callback = None
                await error_notifier.close()
                await osint_jobs.close()
    except Exception as exc:
        console_tools.event("Error", f"Sessione Telegram interrotta: {exc}", error=True)
        raise
    finally:
        console_tools.event("Selfbot", "Arresto in corso")
        from ..abuse import close_spam

        await close_spam()
        await osint_jobs.close()
        await anti_login.close()
        for task in list(delete_tasks):
            task.cancel()
        if delete_tasks:
            await asyncio.gather(*list(delete_tasks), return_exceptions=True)
        await lyrics.stop()
        await soundcloud.close()
        await writer.close()
        console_tools.event("Selfbot", "Arresto completato")

