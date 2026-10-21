"""Invii ripetuti nella chat corrente, con arresto e task tracciati."""
from __future__ import annotations

import asyncio
import math
import secrets
import string
import time
from collections import OrderedDict
from hashlib import sha256

from pyrogram import raw
from pyrogram.errors import FloodWait

MAX_MESSAGES = 100
MAX_INTERVAL = 3600
jobs: dict[int, asyncio.Task[None]] = {}
_sent_texts: OrderedDict[tuple[int, bytes], float] = OrderedDict()


def remember_spam(chat_id: int, text: str) -> None:
    key = (chat_id, sha256(text.encode("utf-8")).digest())
    _sent_texts[key] = time.monotonic() + 600
    _sent_texts.move_to_end(key)
    while len(_sent_texts) > 10000:
        _sent_texts.popitem(last=False)


def is_spam_message(message) -> bool:
    now = time.monotonic()
    while _sent_texts and next(iter(_sent_texts.values())) <= now:
        _sent_texts.popitem(last=False)
    text = getattr(message, "text", None)
    if not text:
        return False
    key = (message.chat.id, sha256(text.encode("utf-8")).digest())
    return _sent_texts.get(key, 0) > now


def parse_spam(argument: str) -> tuple[str, int, float]:
    parts = argument.rsplit(maxsplit=2)
    if len(parts) != 3 or not parts[0].strip():
        raise ValueError("Usa: spam <testo con spazi> <numero> <secondi>.")
    text, count_text, interval_text = parts
    try:
        count = int(count_text)
        interval = float(interval_text)
    except ValueError as exc:
        raise ValueError("Numero messaggi intero; intervallo in secondi, anche decimali.") from exc
    if not 1 <= count <= MAX_MESSAGES:
        raise ValueError(f"Scegli da 1 a {MAX_MESSAGES} messaggi.")
    if not math.isfinite(interval) or not 0 <= interval <= MAX_INTERVAL:
        raise ValueError(f"Intervallo da 0 a {MAX_INTERVAL} secondi.")
    if len(text.encode("utf-16-le")) // 2 + 8 > 4096:
        raise ValueError("Testo troppo lungo: massimo 4088 unità UTF-16, escluso il suffisso.")
    return text, count, interval


async def stop_spam(chat_id: int) -> bool:
    task = jobs.get(chat_id)
    if task is None:
        return False
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    # Un task cancellato prima di partire non esegue il suo finally.
    if jobs.get(chat_id) is task:
        jobs.pop(chat_id, None)
    return True


async def close_spam() -> None:
    await asyncio.gather(*(stop_spam(chat_id) for chat_id in list(jobs)))


async def handle_abuse_command(client, message, command: str, argument: str) -> None:
    from .. import runtime

    chat_id = message.chat.id
    if command == "spamstop":
        if argument:
            raise ValueError(f"Uso: {runtime.state.prefix}spamstop")
        stopped = await stop_spam(chat_id)
        await runtime.respond(message, "Invio fermato." if stopped else "Nessun invio attivo in questa chat.", title="MELIXSA / SPAMSTOP")
        return
    text, count, interval = parse_spam(argument)
    if chat_id in jobs:
        raise ValueError(f"Un invio è già attivo in questa chat. Usa {runtime.state.prefix}spamstop.")
    chat_label = runtime.chat_name(message)
    thread_id = getattr(message, "message_thread_id", None)

    async def send_messages() -> None:
        sent_count = 0
        try:
            peer = await client.resolve_peer(chat_id)
            for index in range(count):
                if index and interval:
                    await asyncio.sleep(interval)
                suffix = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(5))
                outgoing_text = f"{text} | {suffix}"
                # Registra prima dell'invio: l'update può arrivare prima della risposta RPC.
                remember_spam(chat_id, outgoing_text)
                sent = await client.invoke(
                    raw.functions.messages.SendMessage(
                        peer=peer, message=outgoing_text, random_id=secrets.randbits(63),
                        reply_to=raw.types.InputReplyToMessage(reply_to_msg_id=thread_id) if thread_id else None,
                    ),
                    # Kurigram conta i tentativi totali: 0 non invia nulla.
                    sleep_threshold=0, retries=1, timeout=10,
                )
                if sent is None:
                    raise RuntimeError("Telegram non ha confermato l'invio.")
                sent_count += 1
            runtime.console_tools.event("Event", f"Spam | chat={chat_label} | inviati={sent_count}/{count} | completato")
        except asyncio.CancelledError:
            runtime.console_tools.event("Event", f"Spam | chat={chat_label} | inviati={sent_count}/{count} | fermato")
            raise
        except FloodWait as exc:
            runtime.console_tools.event("Error", f"Spam | chat={chat_label} | inviati={sent_count}/{count} | fermato: Telegram richiede {exc.value}s di pausa", error=True)
        except Exception as exc:
            runtime.console_tools.event("Error", f"Spam | chat={chat_label} | inviati={sent_count}/{count} | fermato: {exc}", error=True)
        finally:
            if jobs.get(chat_id) is asyncio.current_task():
                jobs.pop(chat_id, None)

    jobs[chat_id] = asyncio.create_task(send_messages())
    runtime.console_tools.event("Event", f"Spam | chat={chat_label} | messaggi={count} | intervallo={interval:g}s | avviato")
