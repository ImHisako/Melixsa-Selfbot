"""Comandi AFK, back e stato per Melixsa."""
from __future__ import annotations

from pyrogram import Client
from pyrogram.types import Message


async def handle_afk_command(client: Client, message: Message, command: str, argument: str) -> None:
    from .. import runtime

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
