"""Informazioni e amministrazione dei gruppi Telegram."""
from __future__ import annotations

from pyrogram import Client
from pyrogram.types import Message


async def handle_command(client: Client, message: Message, command: str, argument: str) -> None:
    from .core import runtime

    title = f"MELIXSA / {command.upper()}"
    chat_id = message.chat.id
    is_group = message.chat.type in {runtime.enums.ChatType.GROUP, runtime.enums.ChatType.SUPERGROUP}
    if command == "whois":
        user = await runtime.resolve_user(client, message, argument)
        name = " ".join(filter(None, (user.first_name, user.last_name)))
        username = f"@{user.username}" if user.username else "—"
        await runtime.respond(message, f"ID » {user.id}\nNome » {name or '—'}\nUsername » {username}\nBot » {'sì' if user.is_bot else 'no'}", title="MELIXSA / WHOIS")
    elif command == 'chatinfo':
        if not is_group:
            await runtime.respond(message, f"Usa {runtime.state.prefix}chatinfo in un gruppo.")
            return
        chat = await client.get_chat(chat_id)
        username = f"@{chat.username}" if chat.username else "—"
        members_count = chat.members_count if chat.members_count is not None else "—"
        await runtime.respond(message, f"Gruppo » {chat.title}\nID » {chat.id}\nUsername » {username}\nMembri » {members_count}", title="MELIXSA / CHATINFO")
    elif command in {entry[0] for entry in runtime.luna_tools.CATEGORIES['admin']}:
        if message.chat.type not in {runtime.enums.ChatType.GROUP, runtime.enums.ChatType.SUPERGROUP}:
            raise ValueError("Usa questo comando in un gruppo con i permessi amministratore necessari.")
        if command == "guildname":
            if not argument or len(argument) > 128:
                raise ValueError("Titolo: da 1 a 128 caratteri.")
            await client.set_chat_title(message.chat.id, argument)
        elif command in {"slowmode", "removeslowmode"}:
            seconds = 0 if command == "removeslowmode" else int(argument)
            if seconds not in {0, 10, 30, 60, 300, 900, 3600}:
                raise ValueError("Valori consentiti: 0, 10, 30, 60, 300, 900, 3600 secondi.")
            await client.set_slow_mode(message.chat.id, seconds)
        else:
            user = await runtime.resolve_user(client, message, argument)
            if command in {"ban", "kick"}:
                await client.ban_chat_member(message.chat.id, user.id)
                if command == "kick":
                    await client.unban_chat_member(message.chat.id, user.id)
            elif command == "unban":
                await client.unban_chat_member(message.chat.id, user.id)
            else:
                permissions = runtime.ChatPermissions() if command == "mute" else (await client.get_chat(message.chat.id)).permissions
                if permissions is None:
                    raise ValueError("Permessi predefiniti del gruppo non disponibili.")
                await client.restrict_chat_member(message.chat.id, user.id, permissions)
        await runtime.respond(message, "Operazione Telegram completata.", title=title)
    else:
        raise ValueError(f"Comando non previsto nella sezione: {command}")
