"""Monitoraggio di gruppi e utenti e relativi elenchi."""
from __future__ import annotations

from pyrogram import Client
from pyrogram.types import Message


async def send_monitor_list(client, message, command: str, argument: str) -> None:
    from .core import runtime

    if argument:
        raise ValueError(f"Uso: {runtime.state.prefix}{command}")
    async with runtime.state_lock:
        users = sorted(runtime.state.stalk)
        groups = sorted(runtime.state.surveillance)
    lines = []
    if command in {"monitorlist", "stalklist"}:
        lines.append(f"Persone seguite con stalk » {len(users)}")
        if not users:
            lines.append("Nessuna persona osservata.")
        for user_id in users:
            try:
                user = await client.get_users(user_id)
                name = " ".join(filter(None, (user.first_name, user.last_name))) or "Senza nome"
                username = f" | @{user.username}" if user.username else ""
                lines.append(f"{name}{username} | ID » {user_id}")
            except Exception:
                lines.append(f"Utente non disponibile | ID » {user_id}")
    if command in {"monitorlist", "sulist"}:
        if lines:
            lines.append("")
        lines.append(f"Gruppi con surveillance » {len(groups)}")
        if not groups:
            lines.append("Nessun gruppo monitorato.")
        for chat_id in groups:
            try:
                chat = await client.get_chat(chat_id)
                username = f" | @{chat.username}" if chat.username else ""
                lines.append(f"{chat.title or 'Senza titolo'}{username} | ID » {chat_id}")
            except Exception:
                lines.append(f"Gruppo non disponibile | ID » {chat_id}")
    # Suddivide elenchi lunghi rispettando il limite Telegram anche con emoji.
    panel = ""
    for line in lines:
        candidate = f"{panel}\n{line}" if panel else line
        if len(candidate.encode("utf-16-le")) // 2 > 3500:
            await runtime.respond(message, panel, title=f"MELIXSA / {command.upper()}")
            panel = line
        else:
            panel = candidate
    if panel:
        await runtime.respond(message, panel, title=f"MELIXSA / {command.upper()}")

async def handle_command(client: Client, message: Message, command: str, argument: str) -> None:
    from .core import runtime

    chat_id = message.chat.id
    is_group = message.chat.type in {runtime.enums.ChatType.GROUP, runtime.enums.ChatType.SUPERGROUP}
    if command in {'monitorlist', 'stalklist', 'sulist'}:
        await send_monitor_list(client, message, command, argument)
    elif command == 'surveillance':
        if not is_group:
            await runtime.respond(message, f"Usa {runtime.state.prefix}surveillance in un gruppo.")
            return
        async with runtime.state_transaction():
            runtime.state.surveillance.add(chat_id)
        await runtime.respond(message, "Monitoraggio del gruppo attivo. Log in data/logs/.")
    elif command == 'sustop':
        if not is_group:
            await runtime.respond(message, f"Usa {runtime.state.prefix}sustop in un gruppo.")
            return
        async with runtime.state_transaction():
            runtime.state.surveillance.discard(chat_id)
        await runtime.respond(message, "Monitoraggio del gruppo fermato.")
    elif command in {"stalk", "unstalk"}:
        user = await runtime.resolve_user(client, message, argument)
        async with runtime.state_transaction():
            if command == "stalk":
                runtime.state.stalk.add(user.id)
            else:
                runtime.state.stalk.discard(user.id)
        action = "attivo" if command == "stalk" else "fermato"
        await runtime.respond(message, f"Monitoraggio di {user.id} {action} in tutti i gruppi visibili.")
    else:
        raise ValueError(f"Comando non previsto nella sezione: {command}")
