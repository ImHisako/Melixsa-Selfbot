"""Profilo Telegram, AFK e informazioni sul client."""
from __future__ import annotations

from pyrogram import Client
from pyrogram.types import Message
from secrets import randbits
from pyrogram import raw

async def handle_afk_command(client: Client, message: Message, command: str, argument: str) -> None:
    from .core import runtime

    if command == "afk":
        runtime.afk.enable(argument)
        await runtime.respond(message, f"AFK attivo\nMessaggio » {runtime.afk.message}", title="MELIXSA / AFK")
    elif command == "back":
        if argument:
            raise ValueError(f"Uso: {runtime.state.prefix}back")
        if runtime.afk.active:
            duration = runtime.afk.disable()
            await runtime.respond(message, f"AFK disattivato\nAssenza » {duration}", title="MELIXSA / AFK")
        else:
            await runtime.respond(message, "AFK non era attivo.", title="MELIXSA / AFK")
    else:
        if argument:
            raise ValueError(f"Uso: {runtime.state.prefix}afkstatus")
        text = f"Stato » {'attivo' if runtime.afk.active else 'off'}\nAssenza » {runtime.afk.duration()}\nMessaggio » {runtime.afk.message}"
        if runtime.afk.last_error:
            text += f"\nUltimo problema » {runtime.afk.last_error}"
        await runtime.respond(message, text, title="MELIXSA / AFK")

async def handle_command(client: Client, message: Message, command: str, argument: str) -> None:
    from .core import runtime

    title = f"MELIXSA / {command.upper()}"
    thread_id = getattr(message, "message_thread_id", None)
    if command in {"afk", "back", "afkstatus"}:
        await runtime.handle_afk_command(client, message, command, argument)
    elif command in {'name', 'bio'}:
        if not argument:
            raise ValueError("Indica il nuovo valore del profilo.")
        if command == "name":
            parts = argument.split("|", 1)
            first, last = parts[0].strip(), parts[1].strip() if len(parts) == 2 else ""
            if not first or len(first) > 64 or len(last) > 64:
                raise ValueError("Nome obbligatorio, massimo 64 caratteri per nome e cognome.")
            await client.update_profile(first_name=first, last_name=last)
        else:
            if len(argument) > 70:
                raise ValueError("Biografia: massimo 70 caratteri.")
            await client.update_profile(bio=argument)
        await runtime.respond(message, "Profilo aggiornato.", title=title)
    elif command == 'avatar':
        if argument or getattr(message, "reply_to_message", None):
            user = await runtime.resolve_user(client, message, argument)
        else:
            user = await client.get_me()
        async for photo in client.get_chat_photos(user.id, limit=1):
            sent = await client.send_photo(message.chat.id, photo.file_id, message_thread_id=thread_id)
            if sent is not None:
                runtime.schedule_delete(sent)
            runtime.console_tools.event("Message", f"Avatar inviato | chat={runtime.chat_name(message)} | user={user.id}")
            return
        await runtime.respond(message, "Nessuna foto profilo accessibile.", title=title)
    elif command == 'uptime':
        seconds = int(runtime.time.monotonic() - runtime.luna_tools.STARTED)
        await runtime.respond(message, f"Attività » {seconds // 3600}h {(seconds % 3600) // 60}m {seconds % 60}s", title=title)
    elif command == 'ping':
        start = runtime.time.perf_counter()
        await client.invoke(raw.functions.Ping(ping_id=randbits(63)), retries=1, timeout=5, sleep_threshold=0)
        elapsed_ms = (runtime.time.perf_counter() - start) * 1000
        await runtime.respond(message, f"Pong!\nTelegram » {elapsed_ms:.2f} ms\nTempo di andata e ritorno al server.", title=title)
    elif command == 'about':
        await runtime.respond(message, f"Melixsa Telegram Selfbot\nStile e comandi ispirati a Luna / Nas\nComandi e alias » {len(runtime.COMMANDS - runtime.CATEGORY_COMMANDS)}\nMenu » {runtime.state.prefix}help", title=title)
    else:
        raise ValueError(f"Comando non previsto nella sezione: {command}")
