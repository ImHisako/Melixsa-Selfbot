"""Configurazione e stato della protezione anti-login."""
from __future__ import annotations

from datetime import datetime

from pyrogram import Client
from pyrogram.types import Message


async def handle_anti_login_command(client: Client, message: Message, argument: str) -> None:
    from .. import runtime

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
