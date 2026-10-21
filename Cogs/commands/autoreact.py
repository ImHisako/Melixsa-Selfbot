"""Gestori dei comandi autoreact di Melixsa."""

from __future__ import annotations

from pyrogram import Client
from pyrogram.types import Message


async def handle_autoreact_command(client: Client, message: Message, argument: str) -> None:
    from .. import runtime

    parts = argument.split(maxsplit=1)
    action = parts[0].lower() if parts else ""
    value = parts[1] if len(parts) == 2 else ""
    if action not in {"", "status", "on", "off", "emoji", "count"} or (value and action not in {"emoji", "count"}):
        await runtime.respond(message, f"Uso » {runtime.state.prefix}autoreact on|off\nEmoji » {runtime.state.prefix}autoreact emoji 👍 ❤️ 🔥\nQuantità » {runtime.state.prefix}autoreact count 1|2|3", title="MELIXSA / AUTOREACT")
        return
    if action in {"on", "off", "emoji", "count"}:
        async with runtime.state_transaction():
            enabled, emojis, count = runtime.state.autoreact, runtime.state.autoreact_emojis, runtime.state.autoreact_count
            if action == "emoji":
                emojis = runtime.autoreact_tools.parse_emojis(value)
                count = min(count, len(emojis))
                # Risolvi la nuova lista prima di salvarla, anche se autoreact è spento.
                await runtime.auto_reactor.prepare(client, refresh=True, emojis=emojis)
            elif action == "count":
                if value not in {"1", "2", "3"} or int(value) > len(emojis):
                    raise ValueError(f"Scegli una quantità da 1 a {len(emojis)}. Per usarne di più, aggiungi prima le emoji alla lista.")
                count = int(value)
                if enabled:
                    await runtime.auto_reactor.prepare(client, refresh=True, emojis=emojis[:count])
            else:
                enabled = action == "on"
                if enabled:
                    await runtime.auto_reactor.prepare(client, refresh=True, emojis=emojis[:count])
            runtime.state.autoreact, runtime.state.autoreact_emojis, runtime.state.autoreact_count = enabled, emojis, count
        runtime.auto_reactor.chat_retry_after.clear()
        runtime.auto_reactor.last_error = ""
    text = (
        f"Stato » {'attivo' if runtime.state.autoreact else 'off'}\n"
        f"Lista emoji » {' '.join(runtime.state.autoreact_emojis)}\n"
        f"Quantità » {runtime.state.autoreact_count}\n"
        f"Reazioni per messaggio » {' '.join(runtime.state.autoreact_emojis[:runtime.state.autoreact_count])}\n"
        f"Scegli emoji » {runtime.state.prefix}autoreact emoji 👍 ❤️ 🔥\n"
        f"Scegli quantità » {runtime.state.prefix}autoreact count 1|2|3\n"
        f"Attiva / ferma » {runtime.state.prefix}autoreact on|off\n"
        "Limiti » Telegram decide quali reazioni e quante consente nella chat."
    )
    if runtime.auto_reactor.last_error:
        text += f"\nUltimo problema » {runtime.auto_reactor.last_error}"
    await runtime.respond(message, text, title="MELIXSA / AUTOREACT")

